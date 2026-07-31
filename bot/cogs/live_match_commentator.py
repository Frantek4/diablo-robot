import asyncio
import aiohttp
import json
import logging
import discord
from discord.ext import commands
from config.settings import settings
from models.fixture_status import FixtureStatus

logger = logging.getLogger(__name__)


def _safe_score(value) -> int:
    return int(value) if value is not None and float(value) >= 0 else 0


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

    async def _track_match(self, match_id: str, fixture_id: str, resume: bool = False):
        self.active_trackers[match_id] = {
            "seen_events": set(),
            "lineups_sent": False,
            "low_coverage_warned": False,
            "empty_responses": 0,
        }
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
                        game = await self._fetch_game(session, match_id)
                        if game is None:
                            self.active_trackers[match_id]["empty_responses"] += 1
                            count = self.active_trackers[match_id]["empty_responses"]
                            logger.warning(f"_track_match: _fetch_game devolvió None para {match_id} ({count}/5)")
                            if count >= 5:
                                logger.error(f"_track_match: 5 respuestas vacías consecutivas para {match_id}, abandonando tracking")
                                if self.bot.messager:
                                    await self.bot.messager.log(
                                        f"Abandoné el tracking de {match_id} tras 5 respuestas vacías de la API. "
                                        f"El partido puede haber terminado sin que lo detectara.", level="WARNING"
                                    )
                                self.bot.fixture_dao.update_status(fixture_id, FixtureStatus.FINISHED)
                                break
                            await asyncio.sleep(30)
                            continue

                        self.active_trackers[match_id]["empty_responses"] = 0

                        status_enum = game.get("status", {}).get("enum", 0)
                        status_name = game.get("status", {}).get("name", "")
                        scores = game.get("scores", [0, 0])

                        if not self.active_trackers[match_id]["lineups_sent"]:
                            lineups_data = game.get("players", {}).get("lineups", {})
                            if lineups_data:
                                await self._send_lineups(game, fixture_id)
                                self.active_trackers[match_id]["lineups_sent"] = True
                                logger.info(f"_track_match: formaciones enviadas para {match_id}")

                        await self._process_events(match_id, game)

                        has_real_events = any(
                            row for stage in game.get("events", [])
                            for row in stage.get("rows", [])
                            if row.get("events")
                        )

                        if (status_enum in (1, 2)
                                and "entretiempo" not in status_name.lower()
                                and not has_real_events
                                and not self.active_trackers[match_id]["low_coverage_warned"]):
                            logger.warning(f"_track_match: baja cobertura detectada para {match_id}")
                            if self.bot.messager:
                                await self.bot.messager.log(
                                    f"Estoy siguiendo el partido {match_id} pero Promiedos no reporta eventos "
                                    f"(baja cobertura). Marcador: {_safe_score(scores[0])}-{_safe_score(scores[1])}.",
                                    level="WARNING"
                                )
                            self.active_trackers[match_id]["low_coverage_warned"] = True

                        if status_enum == 3:
                            logger.info(f"_track_match: partido {match_id} finalizado, cerrando loop")
                            teams = game.get("teams", [{}, {}])
                            score_home = _safe_score(scores[0])
                            score_away = _safe_score(scores[1])
                            home_name = teams[0].get('name', 'Local')
                            away_name = teams[1].get('name', 'Visitante')
                            if self.bot.messager:
                                await self.bot.messager.commentator_update(
                                    f"Final del partido. {home_name} {score_home} - {score_away} {away_name}"
                                )
                            self.bot.fixture_dao.update_score(fixture_id, score_home, score_away, FixtureStatus.FINISHED)
                            break

                    except asyncio.CancelledError:
                        logger.info(f"_track_match: tarea cancelada para {match_id}")
                        raise
                    except Exception as e:
                        logger.exception(f"_track_match: excepción en ciclo para {match_id}: {e}")
                        if self.bot.messager:
                            await self.bot.messager.log(f"El relator se escabió en {match_id}: {e}", level="ERROR", exc=e)

                    await asyncio.sleep(30)
        finally:
            logger.info(f"_track_match: finalizando, removiendo {match_id} de active_trackers")
            self.active_trackers.pop(match_id, None)

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
            tracker["lineups_sent"] = True
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
            f"lineups_sent={tracker['lineups_sent']}"
        )

    async def _send_lineups(self, game: dict, fixture_id: str):
        embed = discord.Embed(title="Formaciones confirmadas", color=discord.Color.red())
        for team in game.get("players", {}).get("lineups", {}).get("teams", []):
            team_name = game["teams"][team["team_num"] - 1]["name"]
            players = [f"**{p['jersey_num']}** {p['player_short_name']}" for p in team.get("starting", [])]
            embed.add_field(name=f"{team_name} ({team['formation']})", value="\n".join(players), inline=True)

        teams = game.get("teams", [{}, {}])
        home_name = teams[0].get("name", "Local")
        away_name = teams[1].get("name", "Visitante") if len(teams) > 1 else "Visitante"

        fixture = self.bot.fixture_dao.get_fixture_by_id(fixture_id)
        venue = fixture.venue if fixture and fixture.venue else "estadio no especificado"

        await self.bot.messager.commentator_update(f"{home_name} vs {away_name} en {venue}", embed=embed)

    async def _process_events(self, match_id: str, game: dict):
        teams = game.get("teams", [])
        stages = game.get("events", [])
        for stage in stages:
            stage_name = stage.get("name")
            stage_key = f"stage_{stage_name}"
            scores = stage.get('scores', [0, 0])
            rows = stage.get("rows", [])

            if (stage_key not in self.active_trackers[match_id]["seen_events"]
                    and stage.get("show_stage_title", False)
                    and scores[0] is not None and float(scores[0]) >= 0):
                score_home = _safe_score(scores[0])
                score_away = _safe_score(scores[1])
                home_name = teams[0].get("name", "Local") if teams else "Local"
                away_name = teams[1].get("name", "Visitante") if len(teams) > 1 else "Visitante"
                await self.bot.messager.commentator_update(
                    f"{stage_name}. {home_name} {score_home} - {score_away} {away_name}"
                )
                self.active_trackers[match_id]["seen_events"].add(stage_key)

            for row in rows:
                time = row.get("time")
                for event in row.get("events", []):
                    event_type = event.get("type")
                    texts = "-".join(event.get("texts", []))
                    event_id = f"{time}_{event_type}_{texts}"

                    if event_id in self.active_trackers[match_id]["seen_events"]:
                        continue

                    team_idx = event.get("team", 1) - 1
                    team_name = teams[team_idx]["name"] if team_idx < len(teams) else "Desconocido"
                    msg = self._format_event(time, event_type, event.get("texts", []), team_name)
                    if msg:
                        logger.info(f"_process_events: {match_id} evento nuevo: {msg}")
                        await self.bot.messager.commentator_update(msg)

                    self.active_trackers[match_id]["seen_events"].add(event_id)

    def _format_event(self, time: str, e_type: int, texts: list, team_name: str) -> str | None:
        player = texts[0] if texts else "Alguien"

        if e_type == 1:
            assist = f" (Asistencia: {texts[1]})" if len(texts) > 1 else ""
            return f"Gol de {team_name}: {player}{assist} ({time}')."
        if e_type == 2:
            return f"Gol en contra de {team_name}: {player} ({time}')."
        if e_type == 4:
            return f"Tarjeta amarilla: {player} ({team_name}) - {time}'."
        if e_type == 5:
            return f"Tarjeta roja: {player} ({team_name}) - {time}'."
        if e_type == 7:
            return f"Gol de penal ({team_name}): {player} ({time}')."
        if e_type == 8:
            return f"Penal fallado ({team_name}): {player} ({time}')."
        if e_type == 10:
            return f"¡PALO! {player} ({team_name}) golpeó en el poste ({time}')."
        if e_type == 15:
            out_player = texts[1] if len(texts) > 1 else "N/A"
            return f"Cambio en {team_name}: Entra {player}, sale {out_player} ({time}')."

        return None


async def setup(bot):
    await bot.add_cog(LiveMatchCommentator(bot))
