from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

# De dónde salió el mirror: del wiki de Nitter, del .env, o cargado a mano en Mongo
SOURCE_WIKI = "wiki"
SOURCE_ENV = "env"
SOURCE_SEED = "seed"


def normalize_mirror_url(url: str) -> str | None:
    """Deja la URL como la guardo: sin barra final, sin path, y con esquema. None si no sirve."""
    url = (url or "").strip()
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    parsed = urlparse(url)
    if not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


@dataclass
class NitterMirror:
    url: str
    source: str = SOURCE_WIKI
    # None = todavía no lo probé nunca
    is_online: bool | None = None
    last_check: datetime | None = None
    last_ok: datetime | None = None
    last_reason: str | None = None
    consecutive_failures: int = 0
    latency_ms: float | None = None

    @classmethod
    def from_doc(cls, doc: dict) -> "NitterMirror":
        return cls(
            url=doc["_id"],
            source=doc.get("source", SOURCE_WIKI),
            is_online=doc.get("is_online"),
            last_check=doc.get("last_check"),
            last_ok=doc.get("last_ok"),
            last_reason=doc.get("last_reason"),
            consecutive_failures=doc.get("consecutive_failures", 0),
            latency_ms=doc.get("latency_ms"),
        )

    @property
    def host(self) -> str:
        return urlparse(self.url).netloc

    @property
    def status_emoji(self) -> str:
        if self.is_online is None:
            return "❔"
        return "🟢" if self.is_online else "🔴"
