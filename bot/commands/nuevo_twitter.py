from datetime import datetime

from discord.ext import commands

from config.settings import settings
from integrations.social_errors import AccountFlagged, ClientOutdated, TargetMissing, Throttled, Unreachable
from models.influencer import InfluencerModel
from models.news_source import NewsSource
from models.social_media import SocialMedia


class NuevoTwitter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='nuevo_twitter')
    async def nuevo_influencer(self, ctx, username: str, description: str, source: str):
        """Sigue una cuenta de Twitter desde la del bot y la anota en la tabla: a qué canal van sus tweets y con qué nombre."""
        username = username.lstrip("@")
        try:
            source_enum = NewsSource(source.lower())
        except ValueError:
            await self.bot.messager.log(f"No reconozco la fuente '{source}' para Twitter.", level="WARNING")
            return

        if self.bot.influencer_dao.exists(username, SocialMedia.TWITTER):
            await self.bot.messager.log(f'@{username} ya está en la tabla de Twitter.')
            return

        # Sólo se lee la home de la cuenta del bot: si no la sigue, sus tweets nunca aparecen. El
        # follow va antes de anotar, así una cuenta que no existe no queda en la tabla por un typo
        account_id, note = await self._follow(username)
        if account_id is False:
            return

        self.bot.influencer_dao.insert(InfluencerModel(
            account_id=account_id,
            name=username,
            description=description,
            source=source_enum,
            platform=SocialMedia.TWITTER,
        ))
        await self.bot.messager.log(f'Anoté a {description} (@{username}) en la tabla de Twitter. {note}')

    async def _follow(self, username: str):
        """Devuelve (id, nota). id es None si no se pudo seguir pero igual hay que anotarla, y False
        si no hay que anotarla."""
        scheduler = self.bot.get_cog("TwitterCheckScheduler")
        if not settings.X_USERNAME:
            return None, "No la seguí: no hay `X_USERNAME` configurado."
        state = self.bot.twitter_state_dao.get()
        if state.get("blocked"):
            # Con el freno puesto no sale ningún pedido, tampoco éste: es la misma cuenta
            return None, (f"No la seguí porque el scaneo está frenado ({state.get('blocked_reason')}): "
                          f"seguila a mano desde @{settings.X_USERNAME}.")
        try:
            return await scheduler.twitter.follow(username), f"La sigo desde @{settings.X_USERNAME}."
        except TargetMissing as e:
            await self.bot.messager.log(f"No anoté a @{username}: {e}.", level="WARNING")
            return False, ""
        except AccountFlagged as e:
            await scheduler._handle_flagged(e, datetime.now(settings.TIMEZONE))
            return None, "No la pude seguir: frené el scaneo (mirá el aviso de arriba)."
        except ClientOutdated as e:
            await scheduler._handle_outdated(e, datetime.now(settings.TIMEZONE))
            return None, "No la pude seguir: frené el scaneo (mirá el aviso de arriba)."
        except (Throttled, Unreachable) as e:
            return None, (f"No la pude seguir ({e.reason}): seguila a mano desde @{settings.X_USERNAME}.")


async def setup(bot):
    await bot.add_cog(NuevoTwitter(bot))
