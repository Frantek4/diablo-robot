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
    "Contexto de cola:\n"
    "Antes de cada pedido vas a recibir el estado actual de la cola de reproducción. Usalo para interpretar pedidos relativos "
    "(\"sacá esa\", \"poné algo parecido\", \"saltá todo hasta el rock\") y para evitar duplicar canciones que ya están en cola.\n\n"
    "Formato de respuesta:\n"
    "- Solo comandos, uno por línea, sin explicaciones ni texto adicional.\n"
    "- Si hay ambigüedad genuina que cambia el resultado (dos canciones distintas con el mismo nombre), preguntá con opciones concretas en castellano rioplatense, usando voseo (hablás, querés, podés, etc.). Solo en ese caso.\n"
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

    async def _send_as_user(self, channel_id: int, content: str):
        async with aiohttp.ClientSession() as session:
            resp = await session.post(
                f"https://discord.com/api/v10/channels/{channel_id}/messages",
                headers={"Authorization": settings.NOT_ROBOT_DEVIL_USER_TOKEN},
                json={"content": content},
            )
            resp.raise_for_status()

    async def _fetch_channel_history(self, channel: discord.TextChannel, before: discord.Message) -> str | None:
        msgs = [m async for m in channel.history(limit=20, before=before) if m.content]
        msgs.reverse()
        if not msgs:
            return None
        return "\n".join(f"{m.author.display_name}: {m.content}" for m in msgs)

    async def _fetch_queue(self, channel: discord.TextChannel) -> str | None:
        await self._send_as_user(channel.id, f"{settings.DJ_COMMAND_PREFIX}queue")
        try:
            response = await self.bot.wait_for(
                "message",
                check=lambda m: m.channel.id == channel.id and m.author.bot and m.author.id != self.bot.user.id,
                timeout=5.0,
            )
        except asyncio.TimeoutError:
            return None

        if response.embeds:
            embed = response.embeds[0]
            parts = [p for p in [embed.title, embed.description] if p]
            parts += [f"{f.name}: {f.value}" for f in embed.fields]
            return "\n".join(parts) or None

        return response.content or None

    async def _call_deepseek(self, user_id: int, queue_context: str | None, chat_history: str | None) -> str:
        messages = [{"role": "system", "content": SYSTEM_PROMPT.format(prefix=settings.DJ_COMMAND_PREFIX)}]
        if queue_context:
            messages.append({"role": "user", "content": f"[Cola actual]\n{queue_context}"})
            messages.append({"role": "assistant", "content": "Entendido, tengo el estado de la cola."})
        if chat_history:
            messages.append({"role": "user", "content": (
                f"[Historial del canal - últimos mensajes]\n{chat_history}\n\n"
                "Este historial es solo contexto. El pedido a procesar es el último mensaje; "
                "el historial solo es relevante si hay una referencia tácita a algo anterior."
            )})
            messages.append({"role": "assistant", "content": "Entendido."})
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
            queue_context, chat_history = await asyncio.gather(
                self._fetch_queue(message.channel),
                self._fetch_channel_history(message.channel, message),
            )
            try:
                response = await self._call_deepseek(message.author.id, queue_context, chat_history)
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
            try:
                proxy = message.guild.get_member(settings.NOT_ROBOT_DEVIL_USER_ID)
                await proxy.edit(voice_channel=member.voice.channel)
                await asyncio.sleep(1)

                for cmd in lines:
                    await self._send_as_user(message.channel.id, cmd)
                    await asyncio.sleep(0.5)

                await asyncio.sleep(2)
                await proxy.edit(voice_channel=None)
            except Exception as e:
                await self.bot.messager.log(f"No pude ejecutar comandos con el usuario proxy en el agente DJ: {e}", level="WARNING", exc=e)
                await message.reply(
                    "No pude ejecutar los comandos automáticamente. Copiá y pegá esto:\n"
                    + "\n".join(f"`{cmd}`" for cmd in lines)
                )
                self._clear_history(message.author.id)
                return

            await message.add_reaction("✅")
            self._clear_history(message.author.id)
        else:
            self._add_to_history(message.author.id, "assistant", response)
            await message.reply(response)


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicAgent(bot))
