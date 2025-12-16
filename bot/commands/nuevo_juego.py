import discord
from discord.ext import commands
from config.settings import settings
from models.videogame import GameChannel
from utils.string_format import to_kebab_case



class NuevoJuegoCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot



    @commands.command(name="nuevo_juego")
    @commands.has_permissions(manage_roles=True, manage_channels=True)
    @commands.guild_only()
    async def nuevo_juego(self, ctx, *, game_name: str):
        
        channel_name = to_kebab_case(game_name)
        guild: discord.Guild = ctx.guild 

        await self.bot.messager.log(f"Creando {game_name} como nuevo juego")

        existing_game = self.bot.game_dao.get_game_by_name(game_name)
        if existing_game is not None:
            await self.bot.messager.log(f"Ya existe un mensaje para el juego {game_name}: {existing_game.message_id}")
            return
        
        if not ctx.message.attachments:
            await self.bot.messager.log("Por favor adjuntá una imagen")
            return

        attachment = ctx.message.attachments[0]
        if not attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
            await self.bot.messager.log("Por favor adjunta una imagen válida (PNG, JPG, JPEG, GIF)")
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
                await self.bot.messager.log(f"Rol '{game_name}' creado exitosamente.")
            except discord.Forbidden:
                 await self.bot.messager.log("Error: No tengo permiso para crear roles.")
                 return
            except discord.HTTPException as e:
                await self.bot.messager.log(f"Error al crear el rol '{game_name}': {e}")
                return
        else:
             await self.bot.messager.log(f"El rol '{game_name}' ya existe.")

        games_category: discord.CategoryChannel = guild.get_channel(settings.GAMES_CATEGORY_ID)

        existing_channel = discord.utils.get(guild.text_channels, name=channel_name)
        game_channel = None
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
                await self.bot.messager.log(f"Canal de texto '#{channel_name}' creado exitosamente en la categoría '{games_category.name}'.")
            except discord.Forbidden:
                await self.bot.messager.log("Error: No tengo permiso para crear canales o establecer permisos.")
                return 
            except discord.HTTPException as e:
                await self.bot.messager.log(f"Error al crear el canal '#{channel_name}': {e}")
                return
        else:
            await self.bot.messager.log(f"El canal '#{channel_name}' ya existe.")
            game_channel = existing_channel

        file = await attachment.to_file()
        message = await self.bot.messager.add_to_catalogue(game_name, file)
    
        game = GameChannel(
            name=game_name,
            message_id=message.id,
            text_channel_id=game_channel.id
        )

        success = self.bot.game_dao.create_game(game)

        if not success:
             await self.bot.messager.log(f"Error al crear el juego {game_name} en la base de datos.")
             return

        try:
            await message.add_reaction("🎮")
        except (discord.Forbidden, discord.HTTPException) as e:
            await self.bot.messager.log(f"Advertencia: Fallo al añadir reacción al mensaje de catálogo: {e}")
        

        announcement_msg = f"Nuevo juego disponible: **{game_name}**\n\n"
        if game_channel:
             announcement_msg += f"Canal: {game_channel.mention}\n"
        announcement_msg += f"Reaccioná con 🎮 en <#{settings.GAMES_TEXT_CHANNEL_ID}> para obtener el rol."
        
        await self.bot.messager.announce(announcement_msg)
        await self.bot.messager.log(f"{game_name} creado en #juegos y anunciado. Rol: {game_name}, Canal: #{channel_name}")



async def setup(bot):
    await bot.add_cog(NuevoJuegoCommand(bot))