import asyncio
import os
import sys

from discord.ext import commands

from utils.required_settings import missing_settings


class ReiniciarCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _run(self, *args):
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode, stdout.decode().strip(), stderr.decode().strip()

    async def _missing_settings_for(self, ref):
        """Que vars requeridas por el codigo de `ref` no estan en el .env de esta maquina.

        Devuelve None si no pude averiguarlo (ahi conviene no bajar nada).
        """
        code, settings_source, _ = await self._run("git", "show", f"{ref}:config/settings.py")
        if code != 0:
            return None
        code, main_source, _ = await self._run("git", "show", f"{ref}:main.py")
        if code != 0:
            return None
        try:
            return missing_settings(settings_source, main_source)
        except SyntaxError:
            return None

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

        if "config/settings.py" in changed or "main.py" in changed:
            missing = await self._missing_settings_for(upstream)

            if missing is None:
                await self.bot.messager.log(
                    "Cambió config/settings.py en el remoto y no pude leer cómo quedó para "
                    "chequear las env vars. No hago el pull para no dejarme sin levantar: "
                    "bajá los cambios a mano. Reinicio igual con el código actual.",
                    level="WARNING",
                )
                await self._restart()
                return

            if missing:
                faltantes = "\n".join(f"- {key}" for key in missing)
                await self.bot.messager.log(
                    "Cambió config/settings.py en el remoto y al .env le faltan env vars "
                    f"requeridas, así que no bajo nada para no quedarme sin levantar:\n{faltantes}\n"
                    "Cargalas en el .env y tirame `!reiniciar` de nuevo, que ahí sí bajo todo solo. "
                    "Reinicio igual con el código actual.",
                    level="WARNING",
                )
                await self._restart()
                return

            await self.bot.messager.log(
                "Cambió config/settings.py en el remoto, pero el .env ya tiene todas las vars "
                "requeridas, así que sigo con la actualización."
            )

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
