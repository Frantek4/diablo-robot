from discord.ui import View, Button
from discord import ButtonStyle

class VoiceJoinView(View):
    def __init__(self, invite_url: str, *, timeout: float = 5400.0):
        super().__init__(timeout=timeout)
        self.add_item(Button(
            label="🔊 Entrar al canal de voz",
            style=ButtonStyle.green,
            url=invite_url
        ))