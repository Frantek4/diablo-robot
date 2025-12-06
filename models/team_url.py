from enum import Enum
from config.settings import settings

class Teams(Enum):
    PROFESIONAL_MASCULINO = ("https://www.promiedos.com.ar/team/independiente/ihe", "assets/banners/profesional.jpeg", settings.TERMOS_VOICE_CHANNEL_ID)
    RESERVA_MASCULINO = ("https://www.promiedos.com.ar/team/independiente-res./ghjfh", "assets/banners/reserva.jpg", settings.TERMOS_VOICE_CHANNEL_ID)
    PROFESIONAL_FEMENINO = ("https://www.promiedos.com.ar/team/independiente-(w)/ceede", "assets/banners/femenino.jpg", settings.TERMOS_VOICE_CHANNEL_ID) # PAGINA ABANDONADA
    SELECCION_NACIONAL = ("https://www.promiedos.com.ar/team/argentina/cdhi", "assets/banners/seleccion.jpg", settings.GENERAL_VOICE_CHANNEL_ID)
    SELECCION_SUB20 = ("https://www.promiedos.com.ar/team/argentina-u20/baaff", "assets/banners/sub20.jpg", settings.GENERAL_VOICE_CHANNEL_ID)