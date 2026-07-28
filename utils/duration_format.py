import re

_DURATION_RE = re.compile(r"(\d+)([smhd])")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_UNIT_NAMES = {"s": ("segundo", "segundos"), "m": ("minuto", "minutos"), "h": ("hora", "horas"), "d": ("día", "días")}


def parse_duration(text: str) -> int:
    match = _DURATION_RE.fullmatch(text.strip().lower())
    if not match:
        raise ValueError(f"Duración inválida: {text!r}, formato esperado tipo '15m', '1h' o '1d'")
    amount, unit = match.groups()
    return int(amount) * _UNIT_SECONDS[unit]


def humanize_duration(text: str) -> str:
    amount, unit = _DURATION_RE.fullmatch(text.strip().lower()).groups()
    amount = int(amount)
    singular, plural = _UNIT_NAMES[unit]
    return f"{amount} {singular if amount == 1 else plural}"
