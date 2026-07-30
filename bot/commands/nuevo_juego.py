import discord
from discord.ext import commands
from config.settings import settings
from models.videogame import GameChannel
from utils.string_format import to_kebab_case



class NuevoJuegoCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot



    @commands.command(name="nuevo_juego", extras={"admin": True})
    @commands.has_permissions(manage_roles=True, manage_channels=True)
    @commands.guild_only()
    async def nuevo_juego(self, ctx, *, game_name: str):
        """Crea el rol y el canal de un juego nuevo. Necesita una imagen adjunta para el catálogo."""

        channel_name = to_kebab_case(game_name)
        guild: discord.Guild = ctx.guild 

        await self.bot.messager.log(f"Registrando '{game_name}'.")

        existing_game = self.bot.games_dao.get_game_by_name(game_name)
        if existing_game is not None:
            await self.bot.messager.log(f"Ya tengo a '{game_name}' en el catálogo (mensaje {existing_game.message_id}).")
            return
        
        if not ctx.message.attachments:
            await self.bot.messager.log("Te falta una imagen adjunta.")
            return

        attachment = ctx.message.attachments[0]
        if not attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
            await self.bot.messager.log("Esa imagen no la acepto, necesito PNG, JPG, JPEG o GIF.")
            return
        
        role = discord.utils.get(guild.roles, name=game_name)
        if not role:
            try:
                role = await guild.create_role(
                    name=game_name,
                    reason=f"Rol creado con {settings.PREFIX}nuevo_juego '{game_name}'",
                    hoist=True,
                    mentionable=True
                )
                await self.bot.messager.log(f"Rol '{game_name}' creado.")
            except discord.Forbidden:
                await self.bot.messager.log(f"No tengo permisos para crear el rol '{game_name}'.", level="ERROR")
                return
            except discord.HTTPException as e:
                await self.bot.messager.log(f"No pude crear el rol '{game_name}': {e}", level="ERROR", exc=e)
                return
        else:
             await self.bot.messager.log(f"El rol '{game_name}' ya existía, lo uso.")

        games_category: discord.CategoryChannel = guild.get_channel(settings.GAMES_CATEGORY_ID)

        existing_channel = discord.utils.get(guild.text_channels, name=channel_name)
        if not existing_channel:
            try:
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    role: discord.PermissionOverwrite(
                        read_messages=True,
                        send_messages=True,
                        embed_links=True,
                        attach_files=True,
                        read_message_history=True
                    )
                }
                
                game_channel = await guild.create_text_channel(
                    channel_name,
                    category=games_category,
                    overwrites=overwrites,
                    reason=f"Canal creado con {settings.PREFIX}nuevo_juego para '{game_name}'",
                    topic=f"Canal dedicado a {game_name}"
                )
                await self.bot.messager.log(f"Creé el canal '#{channel_name}' en '{games_category.name}'.")
            except discord.Forbidden:
                await self.bot.messager.log(f"No tengo permisos para crear el canal '#{channel_name}'.", level="ERROR")
                return
            except discord.HTTPException as e:
                await self.bot.messager.log(f"No pude crear el canal '#{channel_name}': {e}", level="ERROR", exc=e)
                return
        else:
            await self.bot.messager.log(f"El canal '#{channel_name}' ya existía, lo uso.")
            game_channel = existing_channel

        file = await attachment.to_file()
        message = await self.bot.messager.add_to_catalogue(game_name, file)

        game = GameChannel(
            name=game_name,
            message_id=message.id,
            text_channel_id=game_channel.id
        )
        self.bot.games_dao.create_game(game)

        try:
            await message.add_reaction("🎮")
        except (discord.Forbidden, discord.HTTPException) as e:
            await self.bot.messager.log(f"No pude añadir la reacción al catálogo: {e}", level="WARNING", exc=e)

        announcement_msg = (
            f"Nuevo juego disponible: **{game_name}**\n\n"
            f"Canal: {game_channel.mention}\n"
            f"Reaccioná con 🎮 en <#{settings.GAMES_TEXT_CHANNEL_ID}> para obtener el rol."
        )
        await self.bot.messager.announce(announcement_msg)
        await self.bot.messager.log(f"'{game_name}' listo: rol '{game_name}', canal #{channel_name}, anunciado.")



async def setup(bot):
    await bot.add_cog(NuevoJuegoCommand(bot))