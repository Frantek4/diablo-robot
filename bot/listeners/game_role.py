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
            role = discord.utils.get(guild.roles, name=game.name)
            if not role:
                await self.bot.messager.log(f"Rol '{game.name}' no encontrado")
                return

            await member.add_roles(role, reason="Reacción a mensaje de juego")
            await self.bot.messager.log(f"Rol '{role.name}' añadido a {member}")

        except discord.Forbidden:
            await self.bot.messager.log(f"Error: No tengo permiso para asignar el rol '{role.name}' a {payload.user_id}.")
        except discord.NotFound:
            await self.bot.messager.log(f"Error: No se encontró el miembro, rol o mensaje para la reacción en {payload.message_id}.")
        except Exception as e:
            await self.bot.messager.log(f"Error inesperado al añadir reacción: {e}")



    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):

        if not self._validate_reaction_payload(payload):
            return

        guild = self.bot.get_guild(payload.guild_id)
        
        try:
            game = self.bot.games_dao.get_game_by_message_id(payload.message_id)
            if not game:
                return

            role = discord.utils.get(guild.roles, name=game.name)
            member = await guild.fetch_member(payload.user_id)

            if member.bot:
                 return

            await member.remove_roles(role, reason="Reacción a mensaje de juego eliminada")
            await self.bot.messager.log(f"Rol '{role.name}' removido de {member}")

        except discord.Forbidden:
            await self.bot.messager.log(f"Error: No tengo permiso para remover el rol '{role.name}' de {payload.user_id}.")
        except discord.NotFound:
             await self.bot.messager.log(f"Error: No se encontró el miembro, rol o mensaje para la reacción removida en {payload.message_id}.")
        except Exception as e:
            await self.bot.messager.log(f"Error inesperado al eliminar reacción: {e}")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GameRoleHandler(bot))
