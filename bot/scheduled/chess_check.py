from datetime import datetime

import discord
from discord.ext import commands, tasks
from discord.ui import Button

from bot.ui.event_detail_button import EventRedirectView
from config.settings import settings
from integrations import lichess
from models.chess_tournament import ChessTournament


class ChessCheckScheduler(commands.Cog):
    """Espeja los torneos de los equipos de Lichess como eventos externos de Discord: el evento
    linkea al torneo, porque se juega allá y no en un canal de voz. Los abiertos y los que son sólo
    para el equipo del club se marcan distinto en todo (nombre, portada, anuncio), para que nadie
    se entusiasme con uno al que no puede entrar."""

    def __init__(self, bot):
        self.bot = bot

    def cog_unload(self):
        self.chess_scheduled_job.cancel()

    def start_scheduled_job(self):
        if self._team_ids() and not self.chess_scheduled_job.is_running():
            self.chess_scheduled_job.start()

    @tasks.loop(hours=1)
    async def chess_scheduled_job(self):
        try:
            upcoming = await lichess.fetch_upcoming(self._team_ids())
        except Exception as e:
            await self.bot.messager.log(f"No pude leer los torneos de ajedrez de Lichess: {e}", level="ERROR", exc=e)
            return

        guild = self.bot.get_guild(settings.GUILD_ID)
        now = datetime.now(settings.TIMEZONE)
        for tournament in upcoming:
            if tournament.starts_at <= now:
                continue
            try:
                await self._upsert_event(guild, tournament)
            except Exception as e:
                await self.bot.messager.log(f"No pude agendar el torneo de ajedrez '{tournament.name}': {e}", level="ERROR", exc=e)

        # Si algo que tenía agendado ya no figura como "por arrancar", o arrancó antes o lo cancelaron
        listed = {t.lichess_id for t in upcoming}
        for stored in self.bot.chess_tournament_dao.get_upcoming(now):
            if stored["_id"] in listed:
                continue
            try:
                if not await lichess.exists(stored["system"], stored["_id"]):
                    await self._cancel_event(guild, stored)
            except Exception as e:
                await self.bot.messager.log(f"No pude ver si se canceló el torneo de ajedrez '{stored['name']}': {e}", level="ERROR", exc=e)

    async def _upsert_event(self, guild: discord.Guild, tournament: ChessTournament):
        description = tournament.to_description()
        stored = self.bot.chess_tournament_dao.get(tournament.lichess_id)

        if stored:
            event = guild.get_scheduled_event(stored["discord_event_id"])
            # Si el evento ya no está, lo borró alguien a mano: no lo vuelvo a crear
            if event is None or (stored["description"] == description and stored["ends_at"] == tournament.ends_at):
                return
            await event.edit(
                name=tournament.event_name,
                description=description,
                start_time=tournament.starts_at,
                end_time=tournament.ends_at,
                location=tournament.url,
            )
            self.bot.chess_tournament_dao.upsert(tournament, event.id)
            await self.bot.messager.announce_interactive(
                f"{tournament.icon} **Cambios en el torneo de ajedrez**\n\n{description}",
                self._view(event, tournament),
            )
            return

        try:
            with open(tournament.banner, "rb") as image_file:
                image = image_file.read()
        except FileNotFoundError:
            await self.bot.messager.log(f"No encontré la imagen de ajedrez en {tournament.banner}, va sin portada.", level="WARNING")
            image = None

        event = await guild.create_scheduled_event(
            name=tournament.event_name,
            description=description,
            start_time=tournament.starts_at,
            end_time=tournament.ends_at,
            entity_type=discord.EntityType.external,
            location=tournament.url,
            privacy_level=discord.PrivacyLevel.guild_only,
            image=image,
        )
        self.bot.chess_tournament_dao.upsert(tournament, event.id)
        await self.bot.messager.announce_interactive(
            f"{tournament.icon} ** *¡Nuevo torneo {'de liga' if tournament.kind == 'Liga' else tournament.kind.lower()} de ajedrez!* **\n\n{description}",
            self._view(event, tournament),
        )

    async def _cancel_event(self, guild: discord.Guild, stored: dict):
        event = guild.get_scheduled_event(stored["discord_event_id"])
        if event:
            try:
                await event.delete()
            except discord.NotFound:
                pass
        self.bot.chess_tournament_dao.delete(stored["_id"])
        await self.bot.messager.announce(f"Se canceló el torneo de ajedrez **{stored['name']}**")

    @staticmethod
    def _team_ids() -> list[str]:
        return [team_id.strip() for team_id in settings.LICHESS_TEAM_IDS.split(",") if team_id.strip()]

    @staticmethod
    def _view(event: discord.ScheduledEvent, tournament: ChessTournament) -> EventRedirectView:
        view = EventRedirectView(settings.GUILD_ID, event.id, tournament.starts_at)
        view.add_item(Button(label="Ver en Lichess", url=tournament.url))
        return view


async def setup(bot):
    await bot.add_cog(ChessCheckScheduler(bot))
