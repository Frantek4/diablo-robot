import asyncio
import aiohttp
import json
import logging
import discord
from discord.ext import commands
from config.settings import settings
from models.fixture_status import FixtureStatus
from bot.ui.formation_pitch import render_lineups, lineup_confirmed

logger = logging.getLogger(__name__)

MAX_EMPTY_RESPONSES = 5
POLL_INTERVAL_SECONDS = 30
STATUS_FINISHED = 3
CAI_RED = discord.Color.from_str("#E3131E")

EVENTS = {
    "GOAL": 1,
    "OWN_GOAL": 2,
    "PENALTY_GOAL": 3,
    "YELLOW_CARD": 4,
    "RED_CARD": 5,
    "SECOND_YELLOW_RED": 6,
    "PENALTY_MISSED": 7,
    "DISALLOWED_GOAL": 9,
    "POST": 10,
    "SUBSTITUTION": 15,
}


def _safe_score(value) -> int:
    return int(value) if value is not None and float(value) >= 0 else 0


def _fmt_time(time) -> str:
    return f"{str(time).rstrip(chr(39))}'" if time is not None else "?'"


def _bold_player(name: str, jersey_num) -> str:
    return f"{name} **[{jersey_num}]**" if jersey_num is not None else name


def _player_display(name: str, roster: dict, jersey_num=None) -> str:
    return _bold_player(name, jersey_num if jersey_num is not None else roster.get(name))


def _team_names(teams: list) -> tuple[str, str]:
    home_name = teams[0].get("name", "Local") if teams else "Local"
    away_name = teams[1].get("name", "Visitante") if len(teams) > 1 else "Visitante"
    return home_name, away_name


def _team_short_name(team: dict) -> str:
    return team.get("short_name") or team.get("name", "Desconocido")


def _stay_suffix(team_name: str, players_on_field: int | None) -> str:
    return f" ({team_name} queda con {players_on_field})" if players_on_field is not None else ""


def _score_line(game: dict, teams: list) -> str:
    scores = game.get("scores", [0, 0])
    score_home = _safe_score(scores[0])
    score_away = _safe_score(scores[1])
    home_name, away_name = _team_names(teams)
    return f"{home_name} {score_home}-{score_away} {away_name}"


class LiveMatchCommentator(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_trackers: dict = {}
        self._tracking_tasks: set = set()
        self.api_url = "https://api.promiedos.com.ar/gamecenter/"
        self.headers = {
            'User-Agent': settings.USER_AGENT,
            'Referer': 'https://www.promiedos.com.ar/',
            'X-VER': '1.11.7.5',
        }

    def cog_unload(self):
        for task in list(self._tracking_tasks):
            task.cancel()
        self._tracking_tasks.clear()

    async def start_tracking(self, match_id: str, fixture_id: str, resume: bool = False):
        if match_id in self.active_trackers:
            logger.info(f"start_tracking: {match_id} ya está en active_trackers, ignorando")
            return
        logger.info(f"start_tracking: match_id={match_id} fixture_id={fixture_id} resume={resume}")
        task = asyncio.create_task(self._track_match(match_id, fixture_id, resume))
        self._tracking_tasks.add(task)
        task.add_done_callback(self._tracking_tasks.discard)

    def _new_tracker_state(self) -> dict:
        return {
            "seen_events": set(),
            "start_sent": False,
            "empty_responses": 0,
            "roster": {},
        }

    async def _track_match(self, match_id: str, fixture_id: str, resume: bool = False):
        self.active_trackers[match_id] = self._new_tracker_state()
        if self.bot.messager:
            if resume:
                await self.bot.messager.log(f"Retomo el seguimiento del partido {match_id} tras un reinicio.")
            else:
                await self.bot.messager.log(f"Comenzando el seguimiento del partido {match_id} en vivo.")
        try:
            async with aiohttp.ClientSession() as session:
                if resume:
                    primer = await self._fetch_game(session, match_id)
                    if primer:
                        self._prime_seen_state(match_id, primer)

                while True:
                    try:
                        finished = await self._track_cycle(session, match_id, fixture_id)
                        if finished:
                            break
                    except asyncio.CancelledError:
                        logger.info(f"_track_match: tarea cancelada para {match_id}")
                        raise
                    except Exception as e:
                        logger.exception(f"_track_match: excepción en ciclo para {match_id}: {e}")
                        if self.bot.messager:
                            await self.bot.messager.log(f"El relator se escabió en {match_id}: {e}", level="ERROR", exc=e)

                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
        finally:
            logger.info(f"_track_match: finalizando, removiendo {match_id} de active_trackers")
            self.active_trackers.pop(match_id, None)

    async def _track_cycle(self, session: aiohttp.ClientSession, match_id: str, fixture_id: str) -> bool:
        """Hace un ciclo de fetch + procesamiento. Devuelve True si el partido terminó
        (o si hay que abandonar el tracking) y hay que cortar el loop."""
        tracker = self.active_trackers[match_id]

        game = await self._fetch_game(session, match_id)
        if game is None:
            return await self._handle_empty_response(match_id, fixture_id)
        tracker["empty_responses"] = 0

        status_enum = game.get("status", {}).get("enum", 0)
        scores = game.get("scores", [0, 0])

        await self._announce_start(match_id, game, fixture_id, status_enum)
        await self._process_events(match_id, game, status_enum)

        if status_enum == STATUS_FINISHED:
            await self._announce_final(match_id, fixture_id, game, scores)
            return True

        return False

    async def _handle_empty_response(self, match_id: str, fixture_id: str) -> bool:
        tracker = self.active_trackers[match_id]
        tracker["empty_responses"] += 1
        count = tracker["empty_responses"]
        logger.warning(f"_track_match: _fetch_game devolvió None para {match_id} ({count}/{MAX_EMPTY_RESPONSES})")
        if count < MAX_EMPTY_RESPONSES:
            return False

        logger.error(f"_track_match: {MAX_EMPTY_RESPONSES} respuestas vacías consecutivas para {match_id}, abandonando tracking")
        if self.bot.messager:
            await self.bot.messager.log(
                f"Abandoné el tracking de {match_id} tras {MAX_EMPTY_RESPONSES} respuestas vacías de la API. "
                f"El partido puede haber terminado sin que lo detectara.", level="WARNING"
            )
        self.bot.fixture_dao.update_status(fixture_id, FixtureStatus.FINISHED)
        return True

    async def _announce_start(self, match_id: str, game: dict, fixture_id: str, status_enum: int):
        """Anuncia el arranque del partido la primera vez que hay estado en vivo. Si en ese
        momento ya están las formaciones, las manda también (aparte); si no llegaron a tiempo,
        no importan más."""
        tracker = self.active_trackers[match_id]
        if tracker["start_sent"] or status_enum not in (1, 2):
            return

        lineups_data = game.get("players", {}).get("lineups", {})
        if lineups_data:
            tracker["roster"] = self._build_roster(game)
            await self._send_lineups(game)
            logger.info(f"_track_match: formaciones enviadas para {match_id}")

        home_name, away_name = _team_names(game.get("teams", [{}, {}]))
        fixture = self.bot.fixture_dao.get_fixture_by_id(fixture_id)
        venue = fixture.venue if fixture and fixture.venue else "estadio no especificado"
        await self.bot.messager.commentator_update(f"⚽ {home_name} vs {away_name} 🏟️ {venue}")
        tracker["start_sent"] = True
        logger.info(f"_track_match: arranque anunciado para {match_id}")

    async def _announce_final(self, match_id: str, fixture_id: str, game: dict, scores: list):
        logger.info(f"_track_match: partido {match_id} finalizado, cerrando loop")
        teams = game.get("teams", [{}, {}])
        score_home = _safe_score(scores[0])
        score_away = _safe_score(scores[1])
        home_name, away_name = _team_names(teams)
        if self.bot.messager:
            await self.bot.messager.commentator_update(
                f"🏁 Final: {home_name} {score_home}-{score_away} {away_name}"
            )
        self.bot.fixture_dao.update_score(fixture_id, score_home, score_away, FixtureStatus.FINISHED)

    async def _fetch_game(self, session: aiohttp.ClientSession, match_id: str) -> dict | None:
        url = f"{self.api_url}{match_id}"
        try:
            async with session.get(url, headers=self.headers) as resp:
                if resp.status != 200:
                    if self.bot.messager:
                        await self.bot.messager.log(
                            f"La API de Promiedos devolvió {resp.status} para {match_id}.", level="WARNING"
                        )
                    return None
                raw = await resp.text()
                try:
                    data = json.loads(raw)
                except Exception as json_err:
                    logger.error(f"_fetch_game: no pude parsear JSON para {match_id}: {json_err}")
                    return None
                return data.get("game")
        except Exception as e:
            logger.exception(f"_fetch_game: excepción para {match_id}: {e}")
            if self.bot.messager:
                await self.bot.messager.log(f"Falló la llamada a la API para {match_id}: {e}", level="ERROR", exc=e)
            return None

    def _prime_seen_state(self, match_id: str, game: dict):
        """Al retomar el tracking tras un reinicio, marca como ya vistos los eventos y
        formaciones que la API ya reporta, para no reanunciar todo el partido de nuevo."""
        tracker = self.active_trackers[match_id]
        if game.get("players", {}).get("lineups", {}):
            tracker["start_sent"] = True
            tracker["roster"] = self._build_roster(game)
        elif game.get("status", {}).get("enum", 0) in (1, 2):
            tracker["start_sent"] = True
        for stage in game.get("events", []):
            scores = stage.get("scores", [0, 0])
            if stage.get("show_stage_title", False) and scores[0] is not None and float(scores[0]) >= 0:
                tracker["seen_events"].add(f"stage_{stage.get('name')}")
            for row in stage.get("rows", []):
                time = row.get("time")
                for event in row.get("events", []):
                    texts = "-".join(event.get("texts", []))
                    tracker["seen_events"].add(f"{time}_{event.get('type')}_{texts}")
        logger.info(
            f"_prime_seen_state: {match_id} retomado con {len(tracker['seen_events'])} eventos ya vistos, "
            f"start_sent={tracker['start_sent']}"
        )

    def _build_roster(self, game: dict) -> dict:
        """Mapea nombre completo de jugador -> dorsal, para poder mostrar el número
        en eventos (como los cambios) que no lo traen incluido."""
        roster = {}
        for team in game.get("players", {}).get("lineups", {}).get("teams", []):
            for player in team.get("starting", []) + team.get("bench", []):
                if player.get("name") and player.get("jersey_num") is not None:
                    roster[player["name"]] = player["jersey_num"]
        return roster

    async def _send_lineups(self, game: dict):
        embed = discord.Embed(title="Formaciones", color=CAI_RED)
        for team in game.get("players", {}).get("lineups", {}).get("teams", []):
            team_data = game["teams"][team["team_num"] - 1]
            team_name = team_data["name"]
            short_name = _team_short_name(team_data)
            players = [f"**{p['jersey_num']}** {p['player_short_name']}" for p in team.get("starting", [])]
            confirmed_tag = "" if lineup_confirmed(team) else " [Formación sin confirmar]"
            embed.add_field(
                name=f"{team_name} ({short_name}) [{team['formation']}]{confirmed_tag}", value="\n".join(players), inline=True
            )

        file = None
        pitch_image = render_lineups(game)
        if pitch_image:
            file = discord.File(pitch_image, filename="formacion.png")
            embed.set_image(url="attachment://formacion.png")

        await self.bot.messager.commentator_update("", embed=embed, file=file)

    async def _process_events(self, match_id: str, game: dict, status_enum: int):
        teams = game.get("teams", [])
        for stage in game.get("events", []):
            await self._announce_stage_title(match_id, stage, teams, status_enum)
            await self._process_row_events(match_id, game, teams, stage.get("rows", []))

    async def _announce_stage_title(self, match_id: str, stage: dict, teams: list, status_enum: int):
        stage_name = stage.get("name")
        stage_key = f"stage_{stage_name}"
        scores = stage.get("scores", [0, 0])
        tracker = self.active_trackers[match_id]

        already_seen = stage_key in tracker["seen_events"]
        has_score = scores[0] is not None and float(scores[0]) >= 0
        if already_seen or not stage.get("show_stage_title", False) or not has_score:
            return

        if status_enum == STATUS_FINISHED:
            # El partido ya terminó: solo avisamos "Final", no la etapa de cierre (ej. "Fin de los 90 minutos").
            tracker["seen_events"].add(stage_key)
            return

        score_home = _safe_score(scores[0])
        score_away = _safe_score(scores[1])
        home_name, away_name = _team_names(teams)
        await self.bot.messager.commentator_update(
            f"⏱️ {stage_name}: {home_name} {score_home}-{score_away} {away_name}"
        )
        tracker["seen_events"].add(stage_key)

    async def _process_row_events(self, match_id: str, game: dict, teams: list, rows: list):
        tracker = self.active_trackers[match_id]
        for row in rows:
            time = row.get("time")
            for event in row.get("events", []):
                event_type = event.get("type")
                texts = "-".join(event.get("texts", []))
                event_id = f"{time}_{event_type}_{texts}"

                if event_id in tracker["seen_events"]:
                    continue

                team_idx = event.get("team", 1) - 1
                team_name = _team_short_name(teams[team_idx]) if team_idx < len(teams) else "Desconocido"

                msg = await self._format_event(time, event, team_name, teams, team_idx, game, tracker["roster"])
                if msg:
                    logger.info(f"_process_events: {match_id} evento nuevo: {msg}")
                    await self.bot.messager.commentator_update(msg)

                tracker["seen_events"].add(event_id)

    async def _format_event(
        self, time: str, event: dict, team_name: str, teams: list, team_idx: int, game: dict, roster: dict
    ) -> str | None:
        e_type = event.get("type")
        texts = event.get("texts", [])
        player = texts[0] if texts else "Alguien"
        player_str = _player_display(player, roster, jersey_num=event.get("player_jersey_num"))
        t = _fmt_time(time)

        players_on_field = None
        if e_type in (EVENTS["YELLOW_CARD"], EVENTS["RED_CARD"], EVENTS["SECOND_YELLOW_RED"]) and 0 <= team_idx < len(teams):
            red_cards = teams[team_idx].get("red_cards")
            if red_cards is not None:
                players_on_field = max(0, 11 - int(red_cards))

        if e_type == EVENTS["GOAL"]:
            assist = f" (asiste {_player_display(texts[1], roster)})" if len(texts) > 1 else ""
            return f"⚽ Gol de {player_str} {assist}. {_score_line(game, teams)} {{{t}}}"
        if e_type == EVENTS["OWN_GOAL"]:
            return f"⚽ Gol en contra de {player_str}. {_score_line(game, teams)} {{{t}}}"
        if e_type == EVENTS["PENALTY_GOAL"]:
            return f"🎯 Gol de penal de {player_str}. {_score_line(game, teams)} {{{t}}}"
        if e_type == EVENTS["DISALLOWED_GOAL"]:
            scorer = texts[1] if len(texts) > 1 else "Alguien"
            scorer_str = _player_display(scorer, roster, jersey_num=event.get("player_jersey_num"))
            return f"🚫 Gol anulado de {scorer_str} ({team_name}) {{{t}}}"
        if e_type == EVENTS["YELLOW_CARD"]:
            return f"🟨 Amarilla para {player_str} ({team_name}) {{{t}}}"
        if e_type == EVENTS["SECOND_YELLOW_RED"]:
            return f"🟨🟥 Segunda amarilla para {player_str}.{_stay_suffix(team_name, players_on_field)} {{{t}}}"
        if e_type == EVENTS["RED_CARD"]:
            return f"🟥 Roja directa para {player_str}.{_stay_suffix(team_name, players_on_field)} {{{t}}}"
        if e_type == EVENTS["PENALTY_MISSED"]:
            return f"❌ Penal errado de {player_str} ({team_name}) {{{t}}}"
        if e_type == EVENTS["POST"]:
            return f"🥅💥 ¡PALO! {player_str} ({team_name}) {{{t}}}"
        if e_type == EVENTS["SUBSTITUTION"]:
            out_player = texts[1] if len(texts) > 1 else "N/A"
            in_str = _player_display(player, roster)
            out_str = _player_display(out_player, roster)
            return f"🔀 Cambio ({team_name}): 🔼 {in_str} 🔽 {out_str} {{{t}}}"

        if self.bot.messager:
            await self.bot.messager.log(f"No reconozco este evento del partido: {event}", level="ERROR")
        return None


async def setup(bot):
    await bot.add_cog(LiveMatchCommentator(bot))
