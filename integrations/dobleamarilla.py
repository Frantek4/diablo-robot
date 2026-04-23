import logging
import aiohttp
from bs4 import BeautifulSoup

from models.news_source import NewsSource

logger = logging.getLogger(__name__)


class DobleAmarillaScraper:
    def __init__(self, bot):
        self.bot = bot
        self.domain = "https://www.dobleamarilla.com.ar"
        self.urls = [
            "liga-_c58daeec046fa270dcb9eb65a",
            "rosca_c5990f5953107d82c75d563f0",
            "search?text=independiente"
        ]
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

    async def scrape_news(self):
        async with aiohttp.ClientSession() as session:
            for url in self.urls:
                try:
                    async with session.get(
                        f"{self.domain}/{url}",
                        headers=self.headers,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as response:
                        response.raise_for_status()
                        html = await response.text()

                    soup = BeautifulSoup(html, "lxml")
                    section_label = url.split("_")[0]

                    for item in self._extract_news(soup):
                        news_url = self.bot.news_dao.normalize_url(self.domain, item["url"])
                        if not news_url or self.bot.news_dao.exists(news_url):
                            continue

                        await self.bot.messager.news(
                            type=NewsSource.PRESS,
                            title=item["title"],
                            description=item["description"],
                            url=news_url,
                            image_url=item["image_url"],
                            publisher=f"Doble Amarilla • {section_label}",
                            color="#F68A3F",
                        )
                        self.bot.news_dao.insert(news_url)

                except Exception as e:
                    await self.bot.messager.log(f"Error al scrapear Doble Amarilla ({url}): {str(e)}")

    def _extract_news(self, soup):
        items = []

        for a in soup.find_all("a", href=True):
            article = a.find("article", class_="item")
            if not article:
                continue

            title_tag = article.find("h2", class_="title")
            deck_tag = article.find("h3", class_="deck")
            if not title_tag:
                continue

            image_url = self._extract_image(article)

            items.append({
                "url": a["href"],
                "title": title_tag.get_text(strip=True),
                "description": deck_tag.get_text(strip=True) if deck_tag else "",
                "image_url": image_url,
            })

        return items

    def _extract_image(self, article):
        picture = article.find("picture")
        if not picture:
            return None

        # Prefer highest-res webp, fall back to jpeg
        for mime in ("image/webp", "image/jpeg"):
            source = picture.find("source", type=mime)
            if source and source.get("srcset"):
                # srcset format: "url1 144w, url2 360w, url3 720w"
                last_entry = source["srcset"].rsplit(",", 1)[-1].strip()
                return last_entry.split()[0]

        return None