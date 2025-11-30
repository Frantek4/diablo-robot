from enum import Enum
from config.settings import settings

class Teams(Enum):
    PROFESIONAL_MASCULINO = ("https://www.promiedos.com.ar/team/independiente/ihe",settings.TERMOS_VOICE_CHANNEL_ID)
    RESERVA_MASCULINO = ("https://www.promiedos.com.ar/team/independiente-res./ghjfh",settings.TERMOS_VOICE_CHANNEL_ID)
    PROFESIONAL_FEMENINO = ("https://www.promiedos.com.ar/team/independiente-(w)/ceede",settings.TERMOS_VOICE_CHANNEL_ID) # PAGINA ABANDONADA
    SELECCION_NACIONAL = ("https://www.promiedos.com.ar/team/argentina/cdhi",settings.GENERAL_VOICE_CHANNEL_ID)
    SELECCION_SUB20 = ("https://www.promiedos.com.ar/team/argentina-u20/baaff",settings.GENERAL_VOICE_CHANNEL_ID)