import asyncio
from datetime import datetime, timedelta, timezone

import instaloader

from config.settings import settings
from models.social_media import SocialMedia


class Instagram:
    def __init__(self, bot):
        self.bot = bot
        self._loader: instaloader.Instaloader | None = None

    def _get_loader(self) -> instaloader.Instaloader:
        if self._loader is not None:
            return self._loader

        loader = instaloader.Instaloader(
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            quiet=True,
        )

        try:
            loader.load_session_from_file(settings.IG_USERNAME)
        except FileNotFoundError:
            raise RuntimeError(
                f"No hay sesión de Instagram guardada. "
                f"Ejecutá 'instaloader --login={settings.IG_USERNAME}' en el servidor para generarla."
            )

        self._loader = loader
        return loader

    async def check_notifications(self):
        influencers: list[dict] = self.bot.influencer_dao.get_by_platform(SocialMedia.INSTAGRAM)
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)

        for influencer in influencers:
            try:
                await self._process_influencer(influencer, cutoff)
            except instaloader.exceptions.LoginRequiredException:
                await self.bot.messager.log(
                    f"La sesión de Instagram expiró. Ejecutá 'instaloader --login={settings.IG_USERNAME}' "
                    f"en el servidor para renovarla.",
                    level="ERROR",
                )
                return
            except Exception as e:
                name = influencer.get("name", "unknown")
                await self.bot.messager.log(
                    f"No pude procesar el feed de Instagram de @{name}: {e}",
                    level="ERROR",
                    exc=e,
                )
            await asyncio.sleep(3)

    async def _process_influencer(self, influencer: dict, cutoff: datetime):
        username = influencer["name"]
        loop = asyncio.get_running_loop()

        try:
            posts = await loop.run_in_executor(
                None, self._fetch_recent_posts, username, cutoff
            )
        except instaloader.exceptions.LoginRequiredException:
            self._loader = None
            raise

        for post in reversed(posts):
            url = f"https://www.instagram.com/p/{post['shortcode']}/"

            if self.bot.news_dao.exists(url):
                continue

            await self.bot.messager.news(
                type=influencer["source"],
                title=f"{influencer['description']} en Instagram",
                description=post["caption"],
                url=url,
                image_url=post["image_url"],
                publisher=f"Instagram • @{username}",
                color="#E1306C",
            )
            self.bot.news_dao.insert(url)
            await asyncio.sleep(1)

    def _fetch_recent_posts(self, username: str, cutoff: datetime) -> list:
        loader = self._get_loader()
        profile = instaloader.Profile.from_username(loader.context, username)

        results = []
        for post in profile.get_posts():
            post_dt = post.date_utc.replace(tzinfo=timezone.utc)
            if post_dt < cutoff:
                break

            caption = post.caption or ""
            if len(caption) > 400:
                caption = caption[:400] + "..."

            image_url = post.url

            results.append({
                "shortcode": post.shortcode,
                "caption": caption,
                "image_url": image_url,
            })

            if len(results) >= 5:
                break

        return results
