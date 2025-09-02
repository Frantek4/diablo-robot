import discord
from discord.ext import commands, tasks
from models.team_urls import Teams
from services.promiedos_scraper import scrape_next_match
from config.settings import settings
from datetime import timedelta

class FixtureEventCreator(commands.Cog):



    def __init__(self, bot):
        self.bot: commands.Bot = bot
    


    def cog_unload(self):
        self.fixture_scheduled_job.cancel()



    def start_scheduled_job(self):
        if not self.fixture_scheduled_job.is_running():
            self.fixture_scheduled_job.start()



    @tasks.loop(hours=24)
    async def fixture_scheduled_job(self):
        print("Executing scheduled fixture check")
        for team in Teams:
            print(team.name.replace("_"," "))
            await self.upsert_next_fixture_event(team)

        print("Fixture check finished")
    
    

    async def upsert_next_fixture_event(self, team: Teams) -> str:
        """Check for next fixture and create/update event"""
        try:
            url, channel_name = team.value
            guild = self.bot.get_guild(int(settings.GUILD_ID))
            
            fixture = scrape_next_match(url)
            
            if not fixture:
                message = "No encontré próximo partido"
                print(message)
                return message
                        
            event_name = f"Watch Party - {fixture['local_team']} vs {fixture['visiting_team']}"
            description = f"¡Vamos a ver el partido juntos!\n\n"
            description += f"⚽ {fixture['local_team']} vs {fixture['visiting_team']}\n"
            description += f"🏆 {fixture['competition']}\n"
            description += f"🏟️ {fixture['stadium'] or "No anunciado"}\n"
            description += f"📅 {fixture['date_time'].strftime('%d/%m/%Y %H:%M')}\n"
            description += f"⚖️ {fixture['referee'] or "No anunciado"}\n"
            description += f"📺 {fixture['tv_channels'] or "No anunciado"}\n"
        
            
            start_time = fixture['date_time'] - timedelta(minutes=15)
            end_time = start_time + timedelta(hours=2)
            
            existing_events = await guild.fetch_scheduled_events()
            existing_event = None
            
            for event in existing_events:
                if event.name == event_name:
                    existing_event = event
                    break
            
            channel = discord.utils.get(guild.voice_channels, name=channel_name)
            
            if existing_event:
                if existing_event.description.strip() == description.strip() and existing_event.start_time == start_time:
                    message = "Sin cambios"
                    print(message)
                    return message
                
                await existing_event.edit(
                    start_time=start_time,
                    end_time=end_time,
                    channel=channel,
                    description=description
                )
                message = "Información actualizada"
                print(message)
                return message
            
            event = await guild.create_scheduled_event(
                name=event_name,
                description=description,
                start_time=start_time,
                end_time=end_time,
                channel=channel,
                entity_type=discord.EntityType.voice,
                privacy_level=discord.PrivacyLevel.guild_only
            )
            
            message = f"Evento creado: {event.name}"
            print(message)
            return message
            
        except Exception as e:
            print(f"Error creando/actualizando evento del partido: {e}")



async def setup(bot: commands.Bot):
    await bot.add_cog(FixtureEventCreator(bot))