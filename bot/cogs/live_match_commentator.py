import asyncio
import aiohttp
import json
import discord
from discord.ext import commands
from config.settings import settings
from models.fixture_status import FixtureStatus


def _safe_score(value) -> int:
    """Returns the score as int, or 0 if None/negative (placeholder value)."""
    return int(value) if value is not None and float(value) >= 0 else 0


class LiveMatchCommentator(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_trackers: dict = {}
        self._tracking_tasks: set = set()
        self.api_url = "https://api.promiedos.com.ar/gamecenter/"
        self.headers = {'User-Agent': settings.USER_AGENT}

    def cog_unload(self):
        for task in list(self._tracking_tasks):
            task.cancel()
        self._tracking_tasks.clear()

    async def start_tracking(self, match_id: str, fixture_id: str):
        if match_id in self.active_trackers:
            return
        task = asyncio.create_task(self._track_match(match_id, fixture_id))
        self._tracking_tasks.add(task)
        task.add_done_callback(self._tracking_tasks.discard)

    async def _track_match(self, match_id: str, fixture_id: str):
        self.active_trackers[match_id] = {
            "seen_events": set(),
            "lineups_sent": False,
            "low_coverage_warned": False,
        }
        await self.bot.messager.log(f"Comenzando el seguimiento del partido {match_id} en vivo.")
        try:
            async with aiohttp.ClientSession() as session:
                while True:
                    try:
                        game = await self._fetch_game(session, match_id)
                        if game is None:
                            await asyncio.sleep(30)
                            continue

                        if not self.active_trackers[match_id]["lineups_sent"]:
                            lineups_data = game.get("players", {}).get("lineups", {})
                            if lineups_data:
                                await self._send_lineups(game)
                                self.active_trackers[match_id]["lineups_sent"] = True

                        status_enum = game.get("status", {}).get("enum", 0)
                        status_name = game.get("status", {}).get("name", "")
                        game_time = game.get("game_time_status_to_display", "?")
                        scores = game.get("scores", [0, 0])
                        seen_count = len(self.active_trackers[match_id]["seen_events"])
                        await self.bot.messager.log(
                            f"[relator] {match_id} | {status_name} {game_time} | "
                            f"{_safe_score(scores[0])}-{_safe_score(scores[1])} | "
                            f"eventos vistos: {seen_count}"
                        )

                        await self._process_events(match_id, game)

                        has_real_events = any(
                            row for stage in game.get("events", [])
                            for row in stage.get("rows", [])
                            if row.get("events")
                        )
                        if (status_enum in (1, 2)
                                and "entretiempo" not in status_name
                                and not has_real_events
                                and not self.active_trackers[match_id]["low_coverage_warned"]):
                            scores = game.get('scores', [0, 0])
                            await self.bot.messager.log(
                                f"Estoy siguiendo el partido {match_id} pero Promiedos no reporta eventos "
                                f"(baja cobertura). Marcador: {_safe_score(scores[0])}-{_safe_score(scores[1])}.",
                                level="WARNING"
                            )
                            self.active_trackers[match_id]["low_coverage_warned"] = True

                        if status_enum == 3:
                            teams = game.get("teams", [{}, {}])
                            scores = game.get('scores', [0, 0])
                            score_home = _safe_score(scores[0])
                            score_away = _safe_score(scores[1])
                            home_name = teams[0].get('name', 'Local')
                            away_name = teams[1].get('name', 'Visitante')
                            await self.bot.messager.commentator_update(
                                f"Final del partido. {home_name} {score_home} - {score_away} {away_name}"
                            )
                            self.bot.fixture_dao.update_score(fixture_id, score_home, score_away, FixtureStatus.FINISHED)
                            break

                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        await self.bot.messager.log(f"El relator se escabió en {match_id}: {e}", level="ERROR", exc=e)

                    await asyncio.sleep(30)
        finally:
            self.active_trackers.pop(match_id, None)

    async def _fetch_game(self, session: aiohttp.ClientSession, match_id: str) -> dict | None:
        try:
            async with session.get(f"{self.api_url}{match_id}", headers=self.headers) as resp:
                if resp.status != 200:
                    await self.bot.messager.log(
                        f"La API de Promiedos devolvió {resp.status} para {match_id}.", level="WARNING"
                    )
                    return None
                data = await resp.json(content_type=None)
                return data.get("game")
        except Exception as e:
            await self.bot.messager.log(f"Falló la llamada a la API para {match_id}: {e}", level="ERROR", exc=e)
            return None

    async def _send_lineups(self, game: dict):
        embed = discord.Embed(title="Formaciones confirmadas", color=discord.Color.blue())
        for team in game.get("players", {}).get("lineups", {}).get("teams", []):
            team_name = game["teams"][team["team_num"] - 1]["name"]
            players = [f"**{p['jersey_num']}** {p['player_short_name']}" for p in team.get("starting", [])]
            embed.add_field(name=f"{team_name} ({team['formation']})", value="\n".join(players), inline=True)
        venue = game.get('game_info', [{}])[0].get('value', 'Estadio no especificado')
        await self.bot.messager.commentator_update(f"Inicio del encuentro en: {venue}", embed=embed)

    async def _process_events(self, match_id: str, game: dict):
        teams = game.get("teams", [])
        for stage in game.get("events", []):
            stage_name = stage.get("name")
            stage_key = f"stage_{stage_name}"
            scores = stage.get('scores', [0, 0])

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

            for row in stage.get("rows", []):
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
