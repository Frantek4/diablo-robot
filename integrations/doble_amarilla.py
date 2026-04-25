import aiohttp
from bs4 import BeautifulSoup

from models.news_source import NewsSource


class DobleAmarillaScraper:
    def __init__(self, bot):
        self.bot = bot
        self.domain = "https://www.dobleamarilla.com.ar"
        self.urls = {
            #"liga-_c58daeec046fa270dcb9eb65a": "Liga",
            "rosca_c5990f5953107d82c75d563f0": "Rosca",
            "search?text=independiente": "Independiente",
        }
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

    async def scrape_news(self):
        async with aiohttp.ClientSession() as session:
            for url, label in self.urls.items():
                try:
                    async with session.get(
                        f"{self.domain}/{url}",
                        headers=self.headers,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as response:
                        response.raise_for_status()
                        html = await response.text()

                    soup = BeautifulSoup(html, "lxml")

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
                            publisher=f"Doble Amarilla • {label}",
                            color="#F68A3F",
                        )
                        self.bot.news_dao.insert(news_url)

                except Exception as e:
                    await self.bot.messager.log(f"No pude scrapear Doble Amarilla ({label}): {e}", level="ERROR", exc=e)

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

            items.append({
                "url": a["href"],
                "title": title_tag.get_text(strip=True),
                "description": deck_tag.get_text(strip=True) if deck_tag else "",
                "image_url": self._extract_image(article),
            })

        return items

    def _extract_image(self, article):
        picture = article.find("picture")
        if not picture:
            return None

        for mime in ("image/webp", "image/jpeg"):
            source = picture.find("source", type=mime)
            if source and source.get("srcset"):
                last_entry = source["srcset"].rsplit(",", 1)[-1].strip()
                return last_entry.split()[0]

        return None