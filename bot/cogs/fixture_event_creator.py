import discord
from discord.ext import commands
from bot.cogs.event_lifecycle_manager import EventLifecycleManager
from bot.ui.event_detail_button import EventRedirectView
from models.fixture import Fixture
from models.team_url import Teams
from integrations.promiedos import scrape_next_match
from config.settings import settings
from datetime import datetime, timedelta

class FixtureEventCreator(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.event_lifecycle_manager = EventLifecycleManager(bot)

    async def upsert_next_fixture_event(self, team: Teams) -> None:
        try:
            url, image_url, channel_id = team.value
            guild = self.bot.get_guild(settings.GUILD_ID)
            
            fixture: Fixture = await scrape_next_match(url)
            
            if not fixture:
                return
            
            next_week = datetime.now(settings.TIMEZONE) + timedelta(days=7)
            
            if next_week < fixture.match_date:
                return
            
            event_name = f"{fixture.home_team} vs {fixture.away_team}"
            start_time = fixture.match_date - timedelta(minutes=15)
            end_time = start_time + timedelta(hours=2, minutes=15)
            channel_obj = discord.utils.get(guild.voice_channels, id=channel_id)

            existing_data = self.bot.fixture_dao.collection.find_one({"match_id": fixture.match_id})
            existing_fixture = None
            
            if existing_data:
                existing_fixture = Fixture.from_dict(existing_data, doc_id=str(existing_data['_id']))
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
                        return
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
                        return
            
            fixture_id = self.bot.fixture_dao.upsert(fixture)
            fixture.id = fixture_id

            if existing_event:
                await existing_event.edit(
                    start_time=start_time,
                    end_time=end_time,
                    channel=channel_obj,
                    description=fixture.to_description()
                )
                return
            
            try:
                with open(image_url, "rb") as image_file:
                    image = image_file.read()
            except FileNotFoundError:
                await self.bot.messager.log(f"Imagen no encontrada en: {image_url}")
                image = None
            
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

            self.event_lifecycle_manager.schedule_event_lifecycle(event)

            view = EventRedirectView(settings.GUILD_ID, event.id, start_time)
            await self.bot.messager.announce_interactive(f"** *¡Nuevo evento!* **\n\n{fixture.to_description()}", view)
            
        except Exception as e:
            await self.bot.messager.log(f"Error creando/actualizando evento del partido: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(FixtureEventCreator(bot))