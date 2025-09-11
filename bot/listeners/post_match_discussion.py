from discord.ext import commands

class EventEndForumPoster(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_scheduled_event_end(self, event):

        title = f"Discusión post-partido {event.name}"
        if len(title) > 100:  # Forum post titles max 100 chars
            title = f"Discusión post-partido {event.name[:74]}..."

        try:
            thread = await self.bot.messager.post_thread(title,"")
            await self.bot.messager.log(f"Created forum post: {thread.jump_url}")
        except Exception as e:
            await self.bot.messager.log(f"Failed to create forum post: {e}")


async def setup(bot):
    await bot.add_cog(EventEndForumPoster(bot))