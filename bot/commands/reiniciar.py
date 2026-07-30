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

    async def _restart(self):
        await self.bot.close()
        os.execv(sys.executable, [sys.executable] + sys.argv)

    @commands.command(name="reiniciar")
    async def reiniciar(self, ctx):
        """Hace git pull (si es seguro) y reinicia el bot"""
        await self.bot.messager.log("Bajando a actualizar el código, ya vuelvo.")

        code, _, stderr = await self._run("git", "fetch")
        if code != 0:
            await self.bot.messager.log(f"No pude hacer git fetch: {stderr}", level="ERROR")
            await self._restart()
            return

        _, before, _ = await self._run("git", "rev-parse", "HEAD")
        _, upstream, _ = await self._run("git", "rev-parse", "@{u}")

        if before == upstream:
            await self.bot.messager.log("No había nada nuevo para bajar. Reinicio igual.")
            await self._restart()
            return

        _, changed_files, _ = await self._run("git", "diff", "--name-only", f"{before}..{upstream}")
        changed = changed_files.splitlines()

        if "config/settings.py" in changed:
            await self.bot.messager.log(
                "Hay cambios en config/settings.py en el remoto, seguramente nuevas env vars. "
                "No hago el pull para no dejar el bot sin levantar: actualizá el .env y bajá los "
                "cambios a mano. Reinicio igual con el código actual.",
                level="WARNING",
            )
            await self._restart()
            return

        code, _, stderr = await self._run("git", "pull")
        if code != 0:
            await self.bot.messager.log(f"No pude hacer git pull: {stderr}", level="ERROR")
            await self._restart()
            return

        _, after, _ = await self._run("git", "rev-parse", "HEAD")
        _, log, _ = await self._run("git", "log", "--pretty=format:- %s", f"{before}..{after}")
        await self.bot.messager.log(f"Actualicé el código, esto traje:\n{log}")

        if "requirements.txt" in changed:
            await self.bot.messager.log("Cambiaron los requirements, instalando dependencias con el venv del proyecto.")
            code, _, stderr = await self._run(sys.executable, "-m", "pip", "install", "-r", "requirements.txt")
            if code != 0:
                await self.bot.messager.log(f"No pude instalar las dependencias nuevas: {stderr}", level="ERROR")
            else:
                await self.bot.messager.log("Dependencias instaladas.")

        await self._restart()


async def setup(bot):
    await bot.add_cog(ReiniciarCommand(bot))
