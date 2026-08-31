import discord
from discord.ext import commands

from bot.config.command_access import ANY_CHANNEL
from bot.ui.calendar_subscribe_view import CalendarSubscribeView
from integrations import google_calendar

THUMBNAIL_PATH = "assets/thumbnail/banda.png"


class CalendarioCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="calendario", extras={"channels": ANY_CHANNEL})
    @commands.has_permissions(manage_messages=True)
    async def calendario(self, ctx):
        """Postea acá el mensaje para suscribirse al calendario de partidos, para que lo fijes."""
        if not google_calendar.is_enabled():
            await ctx.send("Todavía no tengo configurado el Google Calendar, así que no hay nada a lo que suscribirse.")
            return

        embed = discord.Embed(
            title="📅 Calendario de Independiente",
            description=(
                "Todos los partidos del Rojo en el calendario de tu celular: "
                "Profesional, Reserva, Femenino y las Selecciones Nacionales.\n\n"
                "Se actualiza solo."
            ),
            color=discord.Color.red(),
        )
        embed.set_footer(text="Diablo Robot")

        try:
            with open(THUMBNAIL_PATH, "rb") as thumbnail_file:
                thumbnail = discord.File(thumbnail_file, filename="banda.png")
        except FileNotFoundError:
            await self.bot.messager.log(f"No encontré {THUMBNAIL_PATH} para el mensaje del calendario.", level="WARNING")
            thumbnail = None

        if thumbnail:
            embed.set_thumbnail(url="attachment://banda.png")
            message = await ctx.send(embed=embed, file=thumbnail, view=CalendarSubscribeView())
        else:
            message = await ctx.send(embed=embed, view=CalendarSubscribeView())

        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        await self.bot.messager.log(f"Posteé el mensaje del calendario en {ctx.channel.mention}, fijalo: {message.jump_url}")


async def setup(bot):
    if google_calendar.is_enabled():
        # El mensaje queda fijado para siempre, así que el botón tiene que sobrevivir los reinicios.
        bot.add_view(CalendarSubscribeView())
    await bot.add_cog(CalendarioCommand(bot))
