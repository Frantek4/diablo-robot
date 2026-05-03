import asyncio
import time
import aiohttp
import discord
from discord.ext import commands, tasks
from config.settings import settings

SYSTEM_PROMPT = (
    "Sos el DJ de un servidor de Discord. Tu única función es traducir mensajes de usuarios a comandos del bot de música Jockie Music.\n"
    "Este canal es exclusivo para pedidos musicales, así que todo mensaje que recibas es un pedido de música. Nunca ignores un mensaje.\n\n"
    "El prefijo de Jockie es \"{prefix}\". El comando para reproducir es {prefix}p seguido del nombre de la canción.\n\n"
    "Reglas de traducción:\n"
    "- Canción específica → un solo comando: {prefix}p Artista - Título\n"
    "- Álbum → un comando por canción del álbum, en orden de tracklist\n"
    "- Artista → 5 canciones más populares del artista, una por línea\n"
    "- Género o estado de ánimo → 5 canciones representativas y conocidas del género, una por línea\n"
    "- Descripción indirecta (\"la música de los montajes de Gokú\", \"algo para entrenar\", \"esa canción triste de piano\") → identificá la canción o canciones más asociadas a esa descripción y generá los comandos\n"
    "- Acción de control (saltear, pausar, parar, subir volumen, etc.) → el comando de control correspondiente\n\n"
    "Formato de respuesta:\n"
    "- Solo comandos, uno por línea, sin explicaciones ni texto adicional.\n"
    "- Si hay ambigüedad genuina que cambia el resultado (dos canciones distintas con el mismo nombre), preguntá con opciones concretas en español. Solo en ese caso.\n"
    "- Nunca respondas con texto si podés generar comandos."
)

HISTORY_TTL = 120
MAX_HISTORY_MESSAGES = 20


class MusicAgent(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._histories: dict[int, list[dict]] = {}
        self._last_activity: dict[int, float] = {}
        self._cleanup_expired.start()

    def cog_unload(self):
        self._cleanup_expired.cancel()

    @tasks.loop(seconds=30)
    async def _cleanup_expired(self):
        now = time.monotonic()
        expired = [uid for uid, t in self._last_activity.items() if now - t > HISTORY_TTL]
        for uid in expired:
            self._histories.pop(uid, None)
            self._last_activity.pop(uid, None)

    def _add_to_history(self, user_id: int, role: str, content: str):
        if user_id not in self._histories:
            self._histories[user_id] = []
        self._histories[user_id].append({"role": role, "content": content})
        if len(self._histories[user_id]) > MAX_HISTORY_MESSAGES:
            self._histories[user_id] = self._histories[user_id][-MAX_HISTORY_MESSAGES:]
        self._last_activity[user_id] = time.monotonic()

    def _clear_history(self, user_id: int):
        self._histories.pop(user_id, None)
        self._last_activity.pop(user_id, None)

    async def _call_deepseek(self, user_id: int) -> str:
        messages = [{"role": "system", "content": SYSTEM_PROMPT.format(prefix=settings.DJ_COMMAND_PREFIX)}]
        messages.extend(self._histories.get(user_id, []))

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.deepseek.com/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-v4-flash",
                    "messages": messages,
                    "max_tokens": 600,
                    "temperature": 0.0,
                },
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data["choices"][0]["message"]["content"].strip()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not settings.MUSIC_TEXT_CHANNEL_ID or message.channel.id != settings.MUSIC_TEXT_CHANNEL_ID:
            return

        if message.content.startswith(settings.DJ_COMMAND_PREFIX):
            return

        member = message.guild.get_member(message.author.id)
        if not member or not member.voice or not member.voice.channel:
            await message.add_reaction("💤")
            return

        self._add_to_history(message.author.id, "user", message.content)

        async with message.channel.typing():
            try:
                response = await self._call_deepseek(message.author.id)
            except aiohttp.ClientResponseError as e:
                if e.status == 402:
                    await message.reply("Vas a tener que usar comandos porque el admin le debe plata a los chinos.")
                    return
                await self.bot.messager.log(f"No pude llamar a DeepSeek en el agente DJ: {e}", level="ERROR", exc=e)
                await message.add_reaction("❌")
                return
            except Exception as e:
                await self.bot.messager.log(f"No pude llamar a DeepSeek en el agente DJ: {e}", level="ERROR", exc=e)
                await message.add_reaction("❌")
                return

        if not response or response == "IGNORAR":
            await message.add_reaction("❓")
            self._clear_history(message.author.id)
            return

        prefix = settings.DJ_COMMAND_PREFIX
        lines = [line.strip() for line in response.splitlines() if line.strip()]
        is_commands = bool(lines) and all(line.startswith(prefix) for line in lines)

        if is_commands:
            for cmd in lines:
                await message.channel.send(cmd)
                await asyncio.sleep(0.5)
            await message.add_reaction("✅")
            self._clear_history(message.author.id)
        else:
            self._add_to_history(message.author.id, "assistant", response)
            await message.reply(response)


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicAgent(bot))
