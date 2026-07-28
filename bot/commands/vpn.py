import asyncio
import io

import discord
from discord.ext import commands

from config.settings import settings
from integrations import wireguard
from utils.duration_format import humanize_duration, parse_duration


class VpnCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="vpn")
    async def vpn(self, ctx):
        username = ctx.author.name
        loop = asyncio.get_running_loop()

        await ctx.send(f"Dale {ctx.author.mention}, dame un segundo que te armo la config de WireGuard.")

        try:
            accounts = await loop.run_in_executor(None, wireguard.list_accounts)
            server_config = await loop.run_in_executor(None, wireguard.get_server_config)
        except Exception as e:
            await ctx.send(f"{ctx.author.mention} no pude conectarme al router, avisale a un admin.")
            await self.bot.messager.log(f"No pude conectarme al router para armar la VPN de {username}: {e}", level="ERROR", exc=e)
            return

        existing = next((a for a in accounts if a.get("username") == username), None)
        if existing:
            try:
                await loop.run_in_executor(None, wireguard.delete_account, existing["key"])
            except Exception as e:
                await ctx.send(f"{ctx.author.mention} no pude renovar tu config, avisale a un admin.")
                await self.bot.messager.log(f"No pude borrar la config vieja de WireGuard de {username}: {e}", level="ERROR", exc=e)
                return
            accounts.remove(existing)

        try:
            client_ip = wireguard.next_free_client_ip(accounts, server_config)
            credentials = await loop.run_in_executor(None, wireguard.create_account, username, client_ip)
        except Exception as e:
            await ctx.send(f"{ctx.author.mention} no pude generar tu config, avisale a un admin.")
            await self.bot.messager.log(f"No pude crear la cuenta de WireGuard para {username}: {e}", level="ERROR", exc=e)
            return

        config_text = wireguard.build_client_config(credentials, server_config)
        config_file = discord.File(io.BytesIO(config_text.encode()), filename="wg-ecai.conf")

        ttl_seconds = parse_duration(settings.SECRET_MESSAGE_TTL)
        ttl_human = humanize_duration(settings.SECRET_MESSAGE_TTL)

        try:
            dm_message = await ctx.author.send(
                "Acá está tu configuración de WireGuard. Importala en la app oficial de WireGuard "
                "(botón '+' → 'Import from file or archive'). "
                f"No kuelgues que en {ttl_human} borro el mensaje.",
                file=config_file,
            )
        except discord.Forbidden:
            await ctx.send(f"{ctx.author.mention} no puedo mandarte DMs, habilitalos en tu privacidad del server y probá de nuevo.")
            return

        await ctx.send(f"Listo {ctx.author.mention}, te mandé tu config de WireGuard por privado.")
        await self.bot.messager.log(f"Generé una config de WireGuard para {username} ({client_ip}).")

        asyncio.create_task(self._delete_after_delay(dm_message, ttl_seconds))

    async def _delete_after_delay(self, message: discord.Message, delay: float):
        await asyncio.sleep(delay)
        try:
            await message.delete()
        except discord.HTTPException:
            pass


async def setup(bot):
    await bot.add_cog(VpnCommand(bot))
