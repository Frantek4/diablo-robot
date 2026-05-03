import asyncio
import time
from pathlib import Path

import aiohttp
import discord
from discord.ext import commands, tasks

from config.settings import settings
from integrations.web_search import search as web_search

_REF_PATH = Path(__file__).parent.parent.parent / "config" / "docs" / "jockie_commands.md"
_COMMANDS_REF = _REF_PATH.read_text(encoding="utf-8") if _REF_PATH.exists() else ""

SYSTEM_PROMPT = (
    "Sos el DJ de un servidor de Discord. Traducís pedidos en lenguaje natural a comandos de Jockie Music.\n"
    "Todo mensaje en este canal es un pedido musical o de control.\n\n"
    "Podés operar en tres modos dentro de una misma solicitud:\n"
    "- BUSCAR: si necesitás identificar una canción por letra, buscar discografía reciente o "
    "cualquier información de actualidad, respondé con una sola línea: WEBSEARCH: <términos de búsqueda>. "
    "Recibirás los resultados y podrás actuar. Preferí buscar antes de inventar o adivinar. "
    "Para identificar una canción por fragmento de letra, buscá el fragmento directamente sin añadir 'letra' como prefijo "
    "(eso buscaría la letra de una canción con ese nombre, no la canción que contiene esa frase). "
    "Solo añadí site:open.spotify.com cuando ya sabés el nombre de la canción y necesitás la URL de Spotify. "
    "Si no encontrás la URL de Spotify en 1 búsqueda, usá {prefix}album <artista> <álbum> directamente y no sigas buscando.\n"
    "- INFO: si el pedido requiere conocer el estado de la cola o la canción actual, respondé SOLO "
    "con los comandos de información necesarios ({prefix}queue, {prefix}now playing, etc.). Recibirás los resultados.\n"
    "- ACCIÓN: cuando tenés suficiente contexto, respondé con los comandos a ejecutar.\n"
    "Nunca mezcles modos en la misma respuesta.\n\n"
    "Reglas no negociables:\n"
    "- Artista o género sin canción específica → 5 canciones representativas con {prefix}p, una por línea.\n"
    "- Letra de canción → usá WEBSEARCH para identificarla si no estás seguro.\n"
    "- Solo comandos, uno por línea, sin texto adicional.\n"
    "- Cuando recibís un listado numerado de {prefix}album o {prefix}playlist, respondé únicamente con el número de la opción correcta (sin prefijo ni texto).\n"
    "- Si hay ambigüedad genuina, preguntá en castellano rioplatense con voseo. Solo en ese caso.\n"
    "- Nunca respondas con texto si podés generar comandos."
)


INFO_COMMANDS = frozenset({
    "queue",
    "now playing",
    "next up",
    "upcoming",
    "recently played",
    "session information",
    "session statistics",
    "album",
    "playlist",
})

HISTORY_TTL = 120
MAX_HISTORY_MESSAGES = 20
MAX_AGENT_ITERATIONS = 5


class MusicAgent(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._histories: dict[int, list[dict]] = {}
        self._last_activity: dict[int, float] = {}
        self._session: aiohttp.ClientSession | None = None
        self._cleanup_expired.start()

    async def cog_load(self):
        self._session = aiohttp.ClientSession()

    async def cog_unload(self):
        self._cleanup_expired.cancel()
        if self._session:
            await self._session.close()

    @tasks.loop(seconds=30)
    async def _cleanup_expired(self):
        now = time.monotonic()
        expired = [uid for uid, t in self._last_activity.items() if now - t > HISTORY_TTL]
        for uid in expired:
            self._histories.pop(uid, None)
            self._last_activity.pop(uid, None)

    def _push_to_history(self, user_id: int, message: dict):
        if user_id not in self._histories:
            self._histories[user_id] = []
        self._histories[user_id].append(message)
        if len(self._histories[user_id]) > MAX_HISTORY_MESSAGES:
            self._histories[user_id] = self._histories[user_id][-MAX_HISTORY_MESSAGES:]
        self._last_activity[user_id] = time.monotonic()

    def _add_to_history(self, user_id: int, role: str, content: str):
        self._push_to_history(user_id, {"role": role, "content": content})

    def _clear_history(self, user_id: int):
        self._histories.pop(user_id, None)
        self._last_activity.pop(user_id, None)

    def _is_info_command(self, line: str) -> bool:
        prefix = settings.DJ_COMMAND_PREFIX
        if not line.startswith(prefix):
            return False
        cmd = line[len(prefix):].strip().lower()
        return any(cmd == ic or cmd.startswith(ic + " ") for ic in INFO_COMMANDS)

    async def _send_as_user(self, channel_id: int, content: str):
        resp = await self._session.post(
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

    async def _execute_info_command(self, channel: discord.TextChannel, cmd: str) -> str | None:
        try:
            await self._send_as_user(channel.id, cmd)
        except Exception:
            return None
        try:
            response = await self.bot.wait_for(
                "message",
                check=lambda m: m.channel.id == channel.id
                    and m.author.bot
                    and m.author.id != self.bot.user.id
                    and bool(m.embeds or m.content),
                timeout=10.0,
            )
        except asyncio.TimeoutError:
            return None
        if response.embeds:
            embed = response.embeds[0]
            parts = [p for p in [embed.title, embed.description] if p]
            parts += [f"{f.name}: {f.value}" for f in embed.fields]
            return "\n".join(parts) or None
        return response.content or None

    async def _call_ai(self, user_id: int, chat_history: str | None) -> dict:
        messages = [{"role": "system", "content": SYSTEM_PROMPT.format(prefix=settings.DJ_COMMAND_PREFIX)}]
        if _COMMANDS_REF:
            messages.append({"role": "user", "content": f"[Referencia de comandos]\n{_COMMANDS_REF.replace('{prefix}', settings.DJ_COMMAND_PREFIX)}"})
            messages.append({"role": "assistant", "content": "Entendido."})
        if chat_history:
            messages.append({"role": "user", "content": (
                f"[Historial del canal]\n{chat_history}\n\n"
                "Solo es contexto. El pedido a procesar es el último mensaje del historial del usuario."
            )})
            messages.append({"role": "assistant", "content": "Entendido."})
        messages.extend(self._histories.get(user_id, []))

        async with self._session.post(
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

    async def _agent_loop(
        self,
        user_id: int,
        channel: discord.TextChannel,
        chat_history: str | None,
    ) -> tuple[list[str], str | None]:
        prefix = settings.DJ_COMMAND_PREFIX
        did_info = False

        for i in range(MAX_AGENT_ITERATIONS):
            response = await self._call_ai(user_id, chat_history if i == 0 else None)

            # BUSCAR phase
            if response.startswith("WEBSEARCH:"):
                query = response[len("WEBSEARCH:"):].strip()
                result = await web_search(query)
                self._add_to_history(user_id, "assistant", response)
                self._add_to_history(user_id, "user", f"[Resultados de búsqueda]\n{result}")
                continue

            # Empty after INFO phase = implicit success (album/playlist queued via selection, etc.)
            if not response:
                return ([], "") if did_info else ([], None)

            lines = [line.strip() for line in response.splitlines() if line.strip()]
            if not lines:
                return ([], "") if did_info else ([], None)

            if all(line.startswith(prefix) for line in lines):
                info_lines = [l for l in lines if self._is_info_command(l)]
                action_lines = [l for l in lines if not self._is_info_command(l)]

                # INFO phase
                if info_lines and not action_lines:
                    did_info = True
                    results = []
                    for cmd in info_lines:
                        result = await self._execute_info_command(channel, cmd)
                        if result:
                            results.append(f"[{cmd}]\n{result}")
                    self._add_to_history(user_id, "assistant", "\n".join(info_lines))
                    self._add_to_history(
                        user_id, "user",
                        "\n\n".join(results) if results else "Sin respuesta de Jockie.",
                    )
                    continue

                # ACCIÓN phase
                return action_lines or lines, None

            # Selection response: single number for album/playlist menu
            if response.strip().isdigit():
                return [response.strip()], None

            # Text response: question or IGNORAR
            if response == "IGNORAR":
                return [], None
            return [], response

        return [], None

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

        proxy = message.guild.get_member(settings.NOT_ROBOT_DEVIL_USER_ID)
        idle_channel = message.guild.get_channel(settings.IDLE_VOICE_CHANNEL_ID)

        async def return_to_idle():
            try:
                await asyncio.sleep(2)
                await proxy.edit(voice_channel=idle_channel)
            except Exception as e:
                await self.bot.messager.log(f"No pude devolver al proxy a Durmiendo en el agente DJ: {e}", level="WARNING", exc=e)

        try:
            await proxy.edit(voice_channel=member.voice.channel)
            await asyncio.sleep(1)
        except Exception as e:
            await self.bot.messager.log(f"No pude mover al proxy al canal de voz en el agente DJ: {e}", level="WARNING", exc=e)

        async with message.channel.typing():
            chat_history = await self._fetch_channel_history(message.channel, message)
            try:
                action_commands, reply = await self._agent_loop(
                    message.author.id, message.channel, chat_history
                )
            except aiohttp.ClientResponseError as e:
                if e.status == 402:
                    await message.reply("Vas a tener que usar comandos porque el admin le debe plata a los chinos.")
                else:
                    await self.bot.messager.log(f"No pude llamar a DeepSeek en el agente DJ: {e}", level="ERROR", exc=e)
                    await message.add_reaction("❌")
                await return_to_idle()
                return
            except Exception as e:
                await self.bot.messager.log(f"No pude llamar a DeepSeek en el agente DJ: {e}", level="ERROR", exc=e)
                await message.add_reaction("❌")
                await return_to_idle()
                return

        if not action_commands and reply is None:
            await message.add_reaction("❓")
            self._clear_history(message.author.id)
            await return_to_idle()
            return

        if action_commands:
            try:
                for cmd in action_commands:
                    await self._send_as_user(message.channel.id, cmd)
                    await asyncio.sleep(0.5)
            except Exception as e:
                await self.bot.messager.log(f"No pude enviar comandos con el usuario proxy en el agente DJ: {e}", level="WARNING", exc=e)
                await message.reply(
                    "No pude ejecutar los comandos automáticamente. Copiá y pegá esto:\n"
                    + "\n".join(f"`{cmd}`" for cmd in action_commands)
                )
                self._clear_history(message.author.id)
                await return_to_idle()
                return

            await message.add_reaction("✅")
            self._clear_history(message.author.id)
        elif reply == "":
            # Implicit success: album/playlist queued or tool used with no further commands needed
            await message.add_reaction("✅")
            self._clear_history(message.author.id)
        else:
            self._add_to_history(message.author.id, "assistant", reply)
            await message.reply(reply)

        await return_to_idle()


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicAgent(bot))
