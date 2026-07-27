import asyncio
import os
import sys

from discord.ext import commands


class ReiniciarCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _run(self, *args):
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode, stdout.decode().strip(), stderr.decode().strip()

    @commands.command(name="reiniciar")
    async def reiniciar(self, ctx):
        """Hace git pull y reinicia el bot"""
        await self.bot.messager.log("Bajando a actualizar el código, ya vuelvo.")

        _, before, _ = await self._run("git", "rev-parse", "HEAD")

        code, _, stderr = await self._run("git", "pull")
        if code != 0:
            await self.bot.messager.log(f"No pude hacer git pull: {stderr}", level="ERROR")
            return

        _, after, _ = await self._run("git", "rev-parse", "HEAD")

        if before == after:
            await self.bot.messager.log("No había nada nuevo para bajar. Reinicio igual.")
        else:
            _, log, _ = await self._run("git", "log", "--pretty=format:- %s", f"{before}..{after}")
            await self.bot.messager.log(f"Actualicé el código, esto traje:\n{log}")

        await self.bot.close()
        os.execv(sys.executable, [sys.executable] + sys.argv)


async def setup(bot):
    await bot.add_cog(ReiniciarCommand(bot))
