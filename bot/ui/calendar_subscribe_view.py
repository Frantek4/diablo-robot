import discord
from discord import ButtonStyle, Interaction
from discord.ui import Button, View

from integrations import google_calendar


def _other_apps_help() -> str:
    ical = google_calendar.ical_url()
    return (
        "Copiá esta dirección:\n"
        f"```{ical}```\n"
        "**iPhone / iPad** — Ajustes → Apps → Calendario → Cuentas → Añadir cuenta → "
        "Otra → Añadir suscripción a calendario.\n\n"
        "**Outlook** — Calendario → Agregar calendario → Suscribirse desde la Web.\n\n"
        "**Android** — Usá el botón de Google Calendar desde el navegador."
    )


class OtherAppsButton(Button):
    """Le paso la dirección del .ics por privado al que no usa Google."""

    def __init__(self):
        super().__init__(
            label="iPhone, Outlook y otros",
            emoji="📱",
            style=ButtonStyle.secondary,
            custom_id="calendario:otros",
        )

    async def callback(self, interaction: Interaction):
        await interaction.response.send_message(_other_apps_help(), ephemeral=True)


class CalendarSubscribeView(View):
    """La vista del mensaje fijado del calendario. Como el mensaje queda para siempre, no tiene
    timeout y el botón que maneja el bot lleva custom_id fijo, así sigue andando entre reinicios
    (se registra con bot.add_view en el setup del comando)."""

    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Button(
            label="Agregar a mi Google Calendar",
            emoji="📅",
            style=ButtonStyle.link,
            url=google_calendar.subscribe_url(),
        ))
        self.add_item(OtherAppsButton())
