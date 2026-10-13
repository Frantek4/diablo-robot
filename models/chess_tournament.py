from dataclasses import dataclass, field
from datetime import datetime

from utils.date_format import format_datetime


@dataclass
class ChessTournament:
    lichess_id: str
    system: str  # "arena" | "swiss"
    name: str
    starts_at: datetime
    ends_at: datetime
    clock: str  # "3+2"
    speed: str  # "Blitz", "Rápida", ...
    rated: bool
    team_id: str
    # Si el equipo por el que nos enteramos del torneo es de ingreso libre. Es lo que decide quién
    # puede jugar: en un equipo cerrado hay que pedir entrar y esperar que un líder acepte
    team_open: bool
    team_battle: list[str] = field(default_factory=list)
    rounds: int | None = None

    @property
    def url(self) -> str:
        path = "tournament" if self.system == "arena" else "swiss"
        return f"https://lichess.org/{path}/{self.lichess_id}"

    @property
    def kind(self) -> str:
        if self.team_open:
            return "Abierto"
        return "Liga" if self.team_battle else "Interno"

    @property
    def icon(self) -> str:
        return "🟢" if self.team_open else "🔒"

    @property
    def event_name(self) -> str:
        return f"{self.icon} {self.kind} · {self.name}"[:100]

    @property
    def banner(self) -> str:
        # Por ahora la misma para los dos: la de los cerrados está pendiente
        return "assets/banners/cai-chess.jpg"

    def to_description(self) -> str:
        if self.system == "arena":
            formato = f"Arena de {int((self.ends_at - self.starts_at).total_seconds() // 60)} min"
        else:
            formato = f"Suizo a {self.rounds} rondas"
        lines = [
            f"♟️ **{self.name}**",
            f"🏆 Torneo {'de Liga' if self.kind == 'Liga' else self.kind}",
            f"📅 {format_datetime(self.starts_at)}",
            f"⏱️ {self.speed} {self.clock} · {formato} · {'Con rating' if self.rated else 'Sin rating'}",
        ]
        if self.team_battle:
            lines.append(f"⚔️ Batalla de equipos: {len(self.team_battle)} clubes")
        lines.append(f"🔗 {self.url}")
        if self.team_open:
            lines.append(f"👥 Para participar necesitás sumarte al equipo: https://lichess.org/team/{self.team_id}")
        return "\n".join(lines)
