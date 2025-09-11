import discord
from discord.ext import commands
from bot.ui.signup_button import EventRedirectView
from models.fixture import Fixture
from models.team_url import Teams
from services.promiedos_scraper import scrape_next_match
from config.settings import settings
from datetime import datetime, timedelta


class FixtureEventCreator(commands.Cog):

    def __init__(self,bot):
        self.bot = bot

    async def upsert_next_fixture_event(self, team: Teams) -> None:
        try:
            url, channel_name = team.value
            guild = self.bot.get_guild(settings.GUILD_ID)
            
            fixture: Fixture = scrape_next_match(url)
            
            if not fixture:
                await self.bot.messager.log(f"No encontré próximo partido para {team.name}")
                return
            
            local_tz = settings.TIMEZONE
            next_week = datetime.now(local_tz) + timedelta(days=7)
            
            if next_week < fixture.date_time:
                return
                        
            event_name = f"Watch Party - {fixture.local_team} vs {fixture.visiting_team}"
            
            start_time = fixture.date_time - timedelta(minutes=15)
            end_time = start_time + timedelta(hours=2)
            
            existing_events = await guild.fetch_scheduled_events()
            existing_event = None
            
            for event in existing_events:
                if event.name == event_name:
                    existing_event = event
                    break
            
            channel_obj = discord.utils.get(guild.voice_channels, name=channel_name)
            view = EventRedirectView(settings.GUILD_ID,event.id,start_time)
            
            if existing_event:
                existing_fixture = Fixture().from_description(existing_event.description)   
                if existing_fixture == fixture:
                    return
                
                await existing_event.edit(
                    start_time=start_time,
                    end_time=end_time,
                    channel=channel_obj,
                    description=fixture.to_description()
                )

                await self.bot.messager.announce_interactive(f"Cambios en **{event_name}**:\n{existing_fixture.get_changes(fixture)}", view)
                return
            
            event = await guild.create_scheduled_event(
                name=event_name,
                description=fixture.to_description(),
                start_time=start_time,
                end_time=end_time,
                channel=channel_obj,
                entity_type=discord.EntityType.voice,
                privacy_level=discord.PrivacyLevel.guild_only
            )

            await self.bot.messager.announce_interactive(f"** *¡Nuevo evento!* **\n\n{fixture.to_description()}", view)
            
        except Exception as e:
            await self.bot.messager.log(f"Error creando/actualizando evento del partido: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(FixtureEventCreator(bot))