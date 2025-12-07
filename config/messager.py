import asyncio
import aiohttp
from bs4 import BeautifulSoup
import discord
from config.settings import settings

class Messager:

    def __init__(self, bot):
        self.bot = bot
        self.guild = self.bot.get_guild(settings.GUILD_ID)
        if not self.guild:
            raise RuntimeError(f"Mensajero invocado antes de conectarse al servidor.")

        self.general_channel = discord.utils.get(self.guild.text_channels, id=settings.GENERAL_TEXT_CHANNEL_ID)
        self.announcements_channel = discord.utils.get(self.guild.text_channels, id=settings.ANNOUNCEMENTS_TEXT_CHANNEL_ID)
        self.news_channel = discord.utils.get(self.guild.text_channels, id=settings.NEWS_TEXT_CHANNEL_ID)
        self.games_channel = discord.utils.get(self.guild.text_channels, id=settings.GAMES_TEXT_CHANNEL_ID)
        self.devil_robot_channel = discord.utils.get(self.guild.text_channels, id=settings.ROBOT_DEVIL_TEXT_CHANNEL_ID)
        self.football_forum = discord.utils.get(self.guild.channels, id=settings.FOOTBALL_FORUM_ID, type=discord.ChannelType.forum)

        missing_channels = []
        if not self.general_channel:
            missing_channels.append(settings.GENERAL_TEXT_CHANNEL_ID)
        if not self.announcements_channel:
            missing_channels.append(settings.ANNOUNCEMENTS_TEXT_CHANNEL_ID)
        if not self.news_channel:
            missing_channels.append(settings.NEWS_TEXT_CHANNEL_ID)
        if not self.games_channel:
            missing_channels.append(settings.GAMES_TEXT_CHANNEL_ID)
        if not self.devil_robot_channel:
            missing_channels.append(settings.ROBOT_DEVIL_TEXT_CHANNEL_ID)
        if not self.football_forum:
            missing_channels.append(settings.FOOTBALL_FORUM_ID)

        if missing_channels:
            raise RuntimeError(f"Canales no encontrados: {', '.join(missing_channels)}. Revisá las configuraciones.")

    async def chat(self, msg: str):
        await self.general_channel.send(msg)
    
    async def announce(self, msg: str):
        await self.announcements_channel.send(msg)

    async def news(self, link: str):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(link, timeout=10, headers={'User-Agent': 'Mozilla/5.0'}) as response:
                    if response.status != 200:
                        await self.log(f"No se pudo cargar el contenido de {link} (Status: {response.status})")
                        return
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Extraer metadatos Open Graph
                    title_tag = soup.find('meta', property='og:title', content=True)
                    desc_tag = soup.find('meta', property='og:description', content=True)
                    image_tag = soup.find('meta', property='og:image', content=True)
                    
                    # Fallback a metadatos estándar
                    if not title_tag:
                        title_tag = soup.title
                    if not desc_tag:
                        desc_tag = soup.find('meta', attrs={'name': 'description'}, content=True)
                    
                    title = title_tag['content'] if title_tag and hasattr(title_tag, 'content') else (title_tag.text if title_tag else 'Sin título')
                    description = desc_tag['content'] if desc_tag and hasattr(desc_tag, 'content') else (desc_tag.text if desc_tag else 'Sin descripción')
                    image_url = image_tag['content'] if image_tag else None
                    
                    # Crear embed
                    embed = discord.Embed(
                        title=title[:256],
                        description=description[:4096],
                        url=link,
                        color=0x3498db
                    )
                    
                    if image_url:
                        embed.set_image(url=image_url)
                    
                    embed.set_footer(text="Noticia automática")
                    
                    await self.news_channel.send(embed=embed)
                    
        except asyncio.TimeoutError:
            await self.log(f"Tiempo de espera agotado para: {link}")
        except Exception as e:
            await self.log(f"Error al procesar {link}: {str(e)}")
            
    async def announce_interactive(self, msg: str, view):
        await self.announcements_channel.send(msg, view=view)

    async def post_thread(self,title:str,content:str):
        return await self.football_forum.create_thread(
            title=title,
            content=content,
            auto_archive_duration=1440
        )

    async def add_to_catalogue(self, title: str, attachment_file: discord.File):
        message = await self.games_channel.send(content=title, file=attachment_file)
        return message
    
    async def log(self, msg: str):
        print(msg)
        if len(msg) > 2000:
            msg = msg[:1997] + "..."
        await self.devil_robot_channel.send(msg)

def init_messager(bot):
    if hasattr(bot, 'messager') and bot.messager is not None:
        return bot.messager

    messager = Messager(bot)
    bot.messager = messager
