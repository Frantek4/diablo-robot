import asyncio
import logging
import aiohttp
from datetime import datetime, timedelta
from discord.ext import commands, tasks
import discord
from config.settings import settings
from models.fixture_status import FixtureStatus

logger = logging.getLogger(__name__)

class LiveMatchScheduler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_trackers = {}
        self._tracking_tasks: set = set()
        self.api_url = "https://api.promiedos.com.ar/gamecenter/"
        self.headers = {'User-Agent': settings.USER_AGENT}

    def cog_unload(self):
        self.check_upcoming_matches.cancel()
        for task in list(self._tracking_tasks):
            task.cancel()
        self._tracking_tasks.clear()

    def start_scheduled_job(self):
        if not self.check_upcoming_matches.is_running():
            self.check_upcoming_matches.start()

    @tasks.loop(minutes=1)
    async def check_upcoming_matches(self):
        next_match = self.bot.fixture_dao.get_next_match()
        if not next_match or not next_match.match_id or not next_match.id:
            return

        now = datetime.now(settings.TIMEZONE)
        time_to_match = next_match.match_date - now

        if time_to_match <= timedelta(minutes=30) and next_match.match_id not in self.active_trackers:
            if next_match.status == FixtureStatus.SCHEDULED:
                self.bot.fixture_dao.update_status(next_match.id, FixtureStatus.LIVE)
            task = asyncio.create_task(self.track_match_live(next_match.match_id, next_match.id))
            self._tracking_tasks.add(task)
            task.add_done_callback(self._tracking_tasks.discard)

    async def track_match_live(self, match_id: str, fixture_id: str):
        self.active_trackers[match_id] = {"seen_events": set(), "lineups_sent": False}
        await self.bot.messager.log(f"Relator: iniciando seguimiento del partido {match_id}")
        logger.info(f"Relator: Iniciando seguimiento en vivo para el partido {match_id}")
        try:
            async with aiohttp.ClientSession() as session:
                while True:
                    try:
                        async with session.get(f"{self.api_url}{match_id}", headers=self.headers) as resp:
                            if resp.status != 200:
                                await asyncio.sleep(30)
                                continue

                            data = await resp.json()
                            game = data.get("game", {})
                            status_enum = game.get("status", {}).get("enum", 0)
                            status_name = game.get("status", {}).get("name", "").lower()

                            lineups_data = game.get("players", {}).get("lineups", {})
                            if not self.active_trackers[match_id]["lineups_sent"] and lineups_data:
                                await self._send_lineups(game)
                                self.active_trackers[match_id]["lineups_sent"] = True

                            await self._process_events(match_id, game)

                            if status_enum == 3 and "penales" not in status_name:
                                score_home = int(game.get('scores', [0, 0])[0] or 0)
                                score_away = int(game.get('scores', [0, 0])[1] or 0)
                                final_score = f"{game['teams'][0]['name']} {score_home} - {score_away} {game['teams'][1]['name']}"

                                await self.bot.messager.commentator_update(f"Final del partido. Resultado: {final_score}")
                                self.bot.fixture_dao.update_score(fixture_id, score_home, score_away, FixtureStatus.FINISHED)
                                break

                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        logger.error(f"Error en el relato en vivo ({match_id}): {e}", exc_info=True)

                    await asyncio.sleep(30)
        finally:
            self.active_trackers.pop(match_id, None)

    async def _send_lineups(self, game):
        embed = discord.Embed(title="Formaciones confirmadas", color=discord.Color.blue())
        for team in game.get("players", {}).get("lineups", {}).get("teams", []):
            team_name = game["teams"][team["team_num"]-1]["name"]
            players = [f"**{p['jersey_num']}** {p['player_short_name']}" for p in team.get("starting", [])]
            embed.add_field(name=f"{team_name} ({team['formation']})", value="\n".join(players), inline=True)
        
        venue = game.get('game_info', [{}])[0].get('value', 'Estadio no especificado')
        await self.bot.messager.commentator_update(f"Inicio del encuentro en: {venue}", embed=embed)

    async def _process_events(self, match_id, game):
        teams = game.get("teams", [])
        for stage in game.get("events", []):
            stage_name = stage.get("name")
            
            stage_key = f"stage_{stage_name}"
            if stage_key not in self.active_trackers[match_id]["seen_events"]:
                stage_score_home = int(stage.get('scores', [0, 0])[0] or 0)
                stage_score_away = int(stage.get('scores', [0, 0])[1] or 0)
                await self.bot.messager.commentator_update(f"{stage_name}. Marcador: {stage_score_home} - {stage_score_away}")
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
                    team_name = teams[team_idx]["name"]
                    msg = self._format_event(time, event_type, event.get("texts", []), team_name)
                    
                    if msg:
                        await self.bot.messager.commentator_update(msg)
                    
                    self.active_trackers[match_id]["seen_events"].add(event_id)

    def _format_event(self, time, e_type, texts, team_name):
        player = texts[0] if len(texts) > 0 else "Alguien"
        assist = f" (Asistencia: {texts[1]})" if len(texts) > 1 else ""
        
        if e_type == 1:
            return f"Gol de {team_name}: {player}{assist} ({time}')."
        elif e_type == 4:
            return f"Tarjeta amarilla: {player} ({team_name}) - {time}'."
        elif e_type == 5:
            return f"Tarjeta roja: {player} ({team_name}) - {time}'."
        elif e_type == 15:
            out_player = texts[1] if len(texts) > 1 else "N/A"
            return f"Cambio en {team_name}: Entra {player}, sale {out_player} ({time}')."
        elif e_type == 2:
            return f"Gol en contra ({team_name}): {player} ({time}')."
        elif e_type == 7:
            return f"Gol de penal ({team_name}): {player} ({time}')."
        elif e_type == 8:
            return f"Penal fallado ({team_name}): {player} ({time}')."
        
        return None

async def setup(bot):
    await bot.add_cog(LiveMatchScheduler(bot))