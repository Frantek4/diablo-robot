import json

import aiohttp
from discord.ext import commands

from integrations import nitter


def _health_line(health) -> str:
    """Lo acumulado desde que arrancó el contenedor, según `/.health`."""
    if not isinstance(health, dict):
        return "No pude leer `/.health`."
    sessions, requests = health.get("sessions"), health.get("requests")
    parts = []
    if isinstance(sessions, dict):
        parts.append(f"{sessions.get('total', '?')} sesión/es cargadas, {sessions.get('limited', '?')} limitada(s)")
    if isinstance(requests, dict):
        parts.append(f"{requests.get('total', '?')} pedidos desde que arrancó el contenedor")
    return "; ".join(parts) if parts else f"`/.health` contestó algo que no entiendo:\n```json\n{json.dumps(health)[:500]}```"


class NitterCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="nitter")
    async def nitter(self, ctx):
        """Muestra cuánto rate limit le queda a mi instancia de Nitter y cuándo vuelvo a leer Twitter"""
        base_url = nitter.instance_url()
        if not base_url:
            await ctx.send("No tengo `NITTER_HOST_URL` configurada, así que ni leo Twitter.")
            return

        async with aiohttp.ClientSession() as session:
            pool = await nitter.fetch_pool(session, base_url)
            health = await nitter.fetch_health(session, base_url)

        lines = [f"**Nitter** — `{base_url}`", _health_line(health)]

        if pool:
            for index, nitter_session in enumerate(pool.sessions, start=1):
                mark = " ⚠️ marcada como limitada" if nitter_session.limited else ""
                lines.append(f"**Sesión {index}** ({nitter_session.kind}){mark}")
                if nitter_session.limits:
                    lines.extend(f"· {limit}" for limit in nitter_session.limits)
                else:
                    lines.append("· todavía sin estrenar, X no le puso número a nada")
            lines.append(f"**Presupuesto ahora**: {pool.feeds} cuenta(s) por vuelta")
        else:
            lines.append("No pude leer `/.sessions`. ¿Está `enableDebug = true` en `nitter.conf`?")

        scheduler = self.bot.get_cog("TwitterCheckScheduler")
        if scheduler:
            lines.extend(scheduler.status_lines())

        failures = await nitter.recent_failures(seconds=3600, lines=5)
        if failures:
            lines.append("**Lo último que escupió en la última hora**")
            lines.extend(f"· `{line}`" for line in failures)
        elif failures is None:
            lines.append("No pude leerle los logs al contenedor (¿tengo `docker` a mano?).")
        else:
            lines.append("En la última hora no escupió ningún error.")

        await ctx.send("\n".join(lines)[:1990])


async def setup(bot):
    await bot.add_cog(NitterCommand(bot))
