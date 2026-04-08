import asyncio
import logging
import aiohttp
from datetime import datetime, timedelta
from discord.ext import commands, tasks
import discord
from config.settings import settings

logger = logging.getLogger(__name__)


class LiveMatchScheduler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_trackers = {}
        self._tracking_tasks: set = set()  # Mantener referencias a las tasks
        self.api_url = "https://api.promiedos.com.ar/gamecenter/"
        self.headers = {'User-Agent': settings.USER_AGENT}

    def cog_unload(self):
        self.check_upcoming_matches.cancel()

    def start_scheduled_job(self):
        if not self.check_upcoming_matches.is_running():
            self.check_upcoming_matches.start()

    @tasks.loop(minutes=1)
    async def check_upcoming_matches(self):
        """Busca partidos que comiencen pronto o estén en curso para iniciar el tracking"""
        next_match = self.bot.fixture_dao.get_next_match()
        if not next_match or not next_match.id:
            return

        now = datetime.now(settings.TIMEZONE)
        time_to_match = next_match.match_date - now

        if timedelta(minutes=-180) <= time_to_match <= timedelta(minutes=15):
            if next_match.id not in self.active_trackers:
                task = asyncio.create_task(self.track_match_live(next_match.id))
                self._tracking_tasks.add(task)
                task.add_done_callback(self._tracking_tasks.discard)

    async def track_match_live(self, match_id: str):
        """Polling cada 30 segundos para un partido específico"""
        self.active_trackers[match_id] = {"seen_events": set(), "lineups_sent": False}
        logger.info(f"Relator: Iniciando seguimiento en vivo para el partido {match_id}")
        
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
                        
                        if not self.active_trackers[match_id]["lineups_sent"]:
                            await self._send_lineups(game)
                            self.active_trackers[match_id]["lineups_sent"] = True

                        await self._process_events(match_id, game)

                        # Solución 3: Validar que el partido realmente terminó y no está en penales
                        if status_enum == 3 and "penales" not in status_name:
                            final_score = f"{game['teams'][0]['name']} {int(game['scores'][0])} - {int(game['scores'][1])} {game['teams'][1]['name']}"
                            await self.bot.messager.commentator_update(f"Final del partido. Resultado: {final_score}")
                            logger.info(f"Relator: Partido {match_id} finalizado. {final_score}")
                            del self.active_trackers[match_id]
                            break

                except Exception as e:
                    logger.error(f"Error en el relato en vivo ({match_id}): {e}", exc_info=True)
                
                await asyncio.sleep(30)

    async def _send_lineups(self, game):
        """Formatea y envía las formaciones iniciales"""
        embed = discord.Embed(title="Formaciones confirmadas", color=discord.Color.blue())
        for team in game.get("players", {}).get("lineups", {}).get("teams", []):
            team_name = game["teams"][team["team_num"]-1]["name"]
            players = [f"**{p['jersey_num']}** {p['player_short_name']}" for p in team.get("starting", [])]
            embed.add_field(name=f"{team_name} ({team['formation']})", value="\n".join(players), inline=True)
        
        venue = game.get('game_info', [{}])[0].get('value', 'Estadio no especificado')
        await self.bot.messager.commentator_update(f"Inicio del encuentro en: {venue}", embed=embed)

    async def _process_events(self, match_id, game):
        """Analiza la lista de eventos y notifica los nuevos"""
        teams = game.get("teams", [])
        # Las etapas son "Entretiempo", "Fin de los 90", etc.
        for stage in game.get("events", []):
            stage_name = stage.get("name")
            
            # Notificar inicio/fin de etapas
            stage_key = f"stage_{stage_name}"
            if stage_key not in self.active_trackers[match_id]["seen_events"]:
                await self.bot.messager.commentator_update(f"{stage_name}. Marcador: {int(stage['scores'][0])} - {int(stage['scores'][1])}")
                self.active_trackers[match_id]["seen_events"].add(stage_key)

            for row in stage.get("rows", []):
                time = row.get("time")
                for event in row.get("events", []):
                    # Crear un ID único para el evento para no repetir
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
        """Traduce los tipos de eventos de Promiedos a texto amigable"""
        player = texts[0] if len(texts) > 0 else "Alguien"
        assist = f" (Asistencia: {texts[1]})" if len(texts) > 1 else ""
        
        if e_type == 1: # GOL
            return f"Gol de {team_name}: {player}{assist} ({time}')."
        elif e_type == 4: # AMARILLA
            return f"Tarjeta amarilla: {player} ({team_name}) - {time}'."
        elif e_type == 5: # ROJA
            return f"Tarjeta roja: {player} ({team_name}) - {time}'."
        elif e_type == 15: # CAMBIO
            out_player = texts[1] if len(texts) > 1 else "N/A"
            return f"Cambio en {team_name}: Entra {player}, sale {out_player} ({time}')."
        elif e_type == 2: # GOL EN CONTRA
            return f"Gol en contra ({team_name}): {player} ({time}')."
        elif e_type == 7: # PENAL GOL
            return f"Gol de penal ({team_name}): {player} ({time}')."
        elif e_type == 8: # PENAL ERRADO
            return f"Penal fallado ({team_name}): {player} ({time}')."
        
        return None

async def setup(bot):
    await bot.add_cog(LiveMatchScheduler(bot))