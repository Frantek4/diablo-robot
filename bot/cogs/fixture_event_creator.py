from typing import Optional

import discord
from discord.ext import commands
from bot.ui.event_detail_button import EventRedirectView
from models.fixture import Fixture
from models.team_url import Teams
from integrations import google_calendar
from integrations.promiedos import scrape_next_match
from config.settings import settings
from datetime import datetime, timedelta

MATCH_DURATION = timedelta(hours=2)

class FixtureEventCreator(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    async def upsert_next_fixture_event(self, team: Teams) -> None:
        url, image_url, channel_id = team.value

        fixture: Fixture = await scrape_next_match(url)
        if not fixture:
            return

        if datetime.now(settings.TIMEZONE) + timedelta(days=7) < fixture.match_date:
            return

        start_time = fixture.match_date - timedelta(minutes=15)
        end_time = start_time + timedelta(hours=2, minutes=15)

        event, touched = await self._upsert_discord_event(fixture, image_url, channel_id, start_time, end_time)
        if touched:
            await self._sync_calendar(fixture, event)

    async def _upsert_discord_event(
        self,
        fixture: Fixture,
        image_url: str,
        channel_id: int,
        start_time: datetime,
        end_time: datetime,
    ) -> tuple[Optional[discord.ScheduledEvent], bool]:
        """Devuelve el evento y si lo toqué en esta vuelta (lo creé o lo edité por cambios en el fixture)."""
        guild = self.bot.get_guild(settings.GUILD_ID)
        event_name = f"{fixture.home_team} vs {fixture.away_team}"
        channel_obj = discord.utils.get(guild.voice_channels, id=channel_id)

        existing_fixture = self.bot.fixture_dao.get_by_match_id(fixture.match_id)
        if existing_fixture:
            fixture.id = existing_fixture.id
            fixture.status = existing_fixture.status
            fixture.home_score = existing_fixture.home_score
            fixture.away_score = existing_fixture.away_score

        existing_events = await guild.fetch_scheduled_events()
        existing_event = discord.utils.get(existing_events, name=event_name)

        if existing_fixture:
            changes = existing_fixture.get_changes(fixture)
            if not changes:
                if existing_event:
                    return existing_event, False
            else:
                self.bot.fixture_dao.upsert(fixture)
                if existing_event:
                    await existing_event.edit(
                        start_time=start_time,
                        end_time=end_time,
                        channel=channel_obj,
                        description=fixture.to_description()
                    )
                    view = EventRedirectView(settings.GUILD_ID, existing_event.id, start_time)
                    await self.bot.messager.announce_interactive(f"Cambios en **{event_name}**:\n{changes}", view)
                    return existing_event, True

        fixture_id = self.bot.fixture_dao.upsert(fixture)
        fixture.id = fixture_id

        if existing_event:
            await existing_event.edit(
                start_time=start_time,
                end_time=end_time,
                channel=channel_obj,
                description=fixture.to_description()
            )
            return existing_event, True

        try:
            with open(image_url, "rb") as image_file:
                image = image_file.read()
        except FileNotFoundError:
            await self.bot.messager.log(f"No encontré la imagen en {image_url}, la extraño socio.", level="WARNING")
            image = None

        try:
            event = await guild.create_scheduled_event(
                name=event_name,
                description=fixture.to_description(),
                start_time=start_time,
                end_time=end_time,
                channel=channel_obj,
                entity_type=discord.EntityType.voice,
                privacy_level=discord.PrivacyLevel.guild_only,
                image=image
            )
        except discord.HTTPException as e:
            await self.bot.messager.log(f"No pude crear el evento '{event_name}': {e}", level="ERROR", exc=e)
            return None, False

        view = EventRedirectView(settings.GUILD_ID, event.id, start_time)
        await self.bot.messager.announce_interactive(f"** *¡Nuevo evento!* **\n\n{fixture.to_description()}", view)
        return event, True

    async def _sync_calendar(self, fixture: Fixture, event: Optional[discord.ScheduledEvent]) -> None:
        """Espeja el partido en el Google Calendar. Se agenda el partido en sí, no el evento de
        Discord: arranca cuando arranca el partido, sin los 15 minutos de precalentamiento."""
        if not google_calendar.is_enabled():
            return

        event_name = f"{fixture.home_team} vs {fixture.away_team}"
        description = fixture.to_description()
        if event:
            description += f"\n\nEvento en Discord: https://discord.com/events/{settings.GUILD_ID}/{event.id}"

        try:
            await google_calendar.upsert_event(
                match_id=fixture.match_id,
                summary=event_name,
                description=description,
                start=fixture.match_date,
                end=fixture.match_date + MATCH_DURATION,
                location=fixture.venue,
            )
        except Exception as e:
            await self.bot.messager.log(f"No pude agendar '{event_name}' en el Google Calendar: {e}", level="ERROR", exc=e)

async def setup(bot: commands.Bot):
    await bot.add_cog(FixtureEventCreator(bot))
