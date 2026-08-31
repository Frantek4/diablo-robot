import discord
from discord.ext import commands

from bot.config.command_access import ANY_CHANNEL, is_allowed_in


class AyudaHelpCommand(commands.HelpCommand):

    COLOR = discord.Color.red()

    def __init__(self):
        super().__init__(command_attrs={
            "name": "help",
            "aliases": ["ayuda"],
            "help": "Muestra esta ayuda.",
            "extras": {"channels": ANY_CHANNEL},
        })

    def get_command_signature(self, command):
        return f"{self.context.clean_prefix}{command.qualified_name} {command.signature}".strip()

    async def _visible_commands(self, commands_iterable):
        """Los comandos que se pueden usar en este canal y que además el que pregunta
        tiene permisos para correr (filter_commands corre los checks de cada uno)."""
        channel_id = self.context.channel.id
        in_this_channel = [command for command in commands_iterable if is_allowed_in(command, channel_id)]
        return await self.filter_commands(in_this_channel, sort=True)

    async def send_bot_help(self, mapping):
        all_commands = [command for commands_list in mapping.values() for command in commands_list]
        visible = await self._visible_commands(all_commands)

        if not visible:
            await self.get_destination().send("Acá no tenés ningún comando a mano.")
            return

        embed = discord.Embed(
            title="Comandos de Diablo Robot",
            description=(
                f"Estos son los que podés usar acá. "
                f"Escribí `{self.context.clean_prefix}help <comando>` para ver el detalle de alguno."
            ),
            color=self.COLOR,
        )

        for command in visible:
            embed.add_field(
                name=self.get_command_signature(command),
                value=command.short_doc or "Sin descripción.",
                inline=False,
            )

        await self.get_destination().send(embed=embed)

    async def send_command_help(self, command):
        visible = await self._visible_commands([command])
        if not visible:
            await self.send_error_message(await self.command_not_found(command.qualified_name))
            return

        embed = discord.Embed(
            title=self.get_command_signature(command),
            description=command.help or "No tengo más info sobre este comando.",
            color=self.COLOR,
        )
        await self.get_destination().send(embed=embed)

    async def command_not_found(self, string):
        return f"No conozco ningún comando '{string}' que puedas usar acá. Fijate con `{self.context.clean_prefix}help`."

    async def subcommand_not_found(self, command, string):
        return f"'{command.qualified_name}' no tiene ningún subcomando '{string}'."


async def setup(bot):
    bot.help_command = AyudaHelpCommand()
