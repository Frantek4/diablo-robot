"""Dónde se puede usar cada comando.

Cada comando declara sus canales con `extras={"channels": (...)}`; el que no
declara nada vive solo en #robot-devil. Tanto el ruteo de `on_message` como el
`!ayuda` leen esto, así la ayuda muestra exactamente los comandos que el que
pregunta puede correr en el canal donde está preguntando.
"""

from config.settings import settings

ANY_CHANNEL = "*"

DEFAULT_CHANNELS = (settings.ROBOT_DEVIL_TEXT_CHANNEL_ID,)


def allowed_channels(command):
    return command.extras.get("channels", DEFAULT_CHANNELS)


def is_allowed_in(command, channel_id: int) -> bool:
    channels = allowed_channels(command)
    return channels == ANY_CHANNEL or channel_id in channels
