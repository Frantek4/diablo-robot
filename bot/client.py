import discord
from discord.ext import commands
from bot.scheduled.fixture_event_creator import FixtureEventCreator
from config.settings import settings

class DiabloRobot(commands.Bot):


    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        intents.reactions = True
        intents.message_content = True
        intents.guild_scheduled_events = True
        
        super().__init__(
            command_prefix=settings.PREFIX,
            intents=intents
        )
    


    async def setup_hook(self):

        # Commands
        await self.load_extension('bot.commands.fijate')
        await self.load_extension('bot.commands.ping')
        
        # Jobs
        await self.load_extension('bot.scheduled.fixture_event_creator')
        
        print("The bot is ON")
    


    async def on_ready(self):
        
        fixture_creator: FixtureEventCreator = self.get_cog('FixtureEventCreator')
        if fixture_creator:
            fixture_creator.start_scheduled_job()

        print(f'{self.user} connected to the guild')
        
        await self.change_presence(
            activity=discord.CustomActivity(
                name="Atendiendo boludos"
            )
        )
        

    
    async def on_message(self, message):
        # Ignore messages sent by the bot itself
        if message.author == self.user:
            return
        
        # Ignore incoming messages outside of #diablo-robot
        if message.channel.id != settings.ROBOT_DEVIL_TEXT_CHANNEL_ID:
            return
        
        await self.process_commands(message)



    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            await ctx.send("Flashaste")
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("No toqués")
        else:
            print(f"Error de comando: {error}")
            await ctx.send("Que rompimooo")


    
    # When the guild updates their emojis
    # TODO Announce added emojis
    async def on_guild_emojis_update(self, guild, before, after):
        return
    


    # When the guild updates their stickers
    # TODO Announce added stickers
    async def on_guild_stickers_update(self, guild, before, after):
        return
    


    # When a user becomes a member of the guild
    # TODO Greet new user and give instructive
    async def on_member_join(self, member):
        return
    


    # When a member reacts on a message
    # TODO Add game interest role based on reactions to game message on the interests showcase text channel (add LoL role by reacting to LoL showcase message)
    async def on_raw_reaction_add(self, payload):
        return
    


    # When a member removes the reaction on a message
    # TODO Remove game interest role based on the removed reaction to game message on the interests showcase text channel (remove LoL role by un-reacting to LoL showcase message)
    async def on_raw_reaction_add(self, payload):
        return