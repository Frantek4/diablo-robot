import discord
from discord.ext import commands
from config.settings import settings

class GameRoleHandler(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _validate_reaction_payload(self, payload: discord.RawReactionActionEvent) -> bool:
        if payload.user_id == self.bot.user.id:
            return False
        if payload.channel_id != settings.GAMES_TEXT_CHANNEL_ID:
            return False

        if str(payload.emoji) != "🎮":
            return False

        return True

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not self._validate_reaction_payload(payload):
            return

        guild = self.bot.get_guild(payload.guild_id)

        try:
            member = payload.member
            if not member or member.bot:
                return

            game = self.bot.games_dao.get_game_by_message_id(payload.message_id)
            if not game:
                await self.bot.messager.log(f"No encontré ningún juego para el mensaje {payload.message_id}.", level="WARNING")
                return

            role = discord.utils.get(guild.roles, name=game.name)
            if not role:
                await self.bot.messager.log(f"No encontré el rol '{game.name}' para asignarlo.", level="WARNING")
                return

            await member.add_roles(role, reason="Reacción a mensaje de juego")
            await self.bot.messager.log(f"Le di el rol '{role.name}' a {member}.")

        except discord.Forbidden:
            await self.bot.messager.log(f"No tengo permisos para asignar el rol a {payload.user_id}.", level="ERROR")
        except discord.NotFound:
            await self.bot.messager.log(f"No encontré el miembro, rol o mensaje para la reacción en {payload.message_id}.", level="WARNING")
        except Exception as e:
            await self.bot.messager.log(f"Algo raro pasó al añadir la reacción: {e}", level="ERROR", exc=e)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if not self._validate_reaction_payload(payload):
            return

        guild = self.bot.get_guild(payload.guild_id)

        try:
            game = self.bot.games_dao.get_game_by_message_id(payload.message_id)
            if not game:
                await self.bot.messager.log(f"No encontré ningún juego para el mensaje {payload.message_id}.", level="WARNING")
                return

            role = discord.utils.get(guild.roles, name=game.name)
            if not role:
                await self.bot.messager.log(f"No encontré el rol '{game.name}' para funarlo.", level="WARNING")
                return

            member = await guild.fetch_member(payload.user_id)
            if member.bot:
                return

            await member.remove_roles(role, reason="Reacción a mensaje de juego eliminada")
            await self.bot.messager.log(f"Le saqué el rol '{role.name}' a {member}.")

        except discord.Forbidden:
            await self.bot.messager.log(f"No tengo permisos para sacar el rol a {payload.user_id}.", level="ERROR")
        except discord.NotFound:
            await self.bot.messager.log(f"No encontré el miembro, rol o mensaje para la reacción eliminada en {payload.message_id}.", level="WARNING")
        except Exception as e:
            await self.bot.messager.log(f"Algo raro pasó al sacar la reacción: {e}", level="ERROR", exc=e)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GameRoleHandler(bot))
