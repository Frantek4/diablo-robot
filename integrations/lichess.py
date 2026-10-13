import json
from datetime import datetime, timedelta, timezone

import aiohttp

from models.chess_tournament import ChessTournament
from utils.date_format import to_local

API = "https://lichess.org/api"
# Lichess pide que los clientes de la API se identifiquen; no hace falta token para nada de esto
HEADERS = {"Accept": "application/x-ndjson", "User-Agent": "diablo-robot (bot de Discord del club)"}
TIMEOUT = aiohttp.ClientTimeout(total=20)

# Los nombres que usa Lichess para el ritmo, según la duración estimada (base + 40 jugadas de incremento)
_SPEEDS = ((30, "UltraBullet"), (180, "Bullet"), (480, "Blitz"), (1500, "Rápida"))


async def fetch_upcoming(team_ids: list[str]) -> list[ChessTournament]:
    """Arenas y suizos de los equipos que todavía no arrancaron. Las arenas incluyen las batallas
    de equipos que armó otro club y en las que juega el nuestro.

    Si es abierto o no lo dice el propio equipo (`open`): no se escribe a mano cuál es cuál. Un
    torneo que aparece en dos equipos queda como el del equipo abierto, porque por ahí se puede
    entrar a jugarlo sin pedir permiso."""
    tournaments: dict[str, ChessTournament] = {}
    async with aiohttp.ClientSession(headers=HEADERS, timeout=TIMEOUT) as session:
        teams = []
        for team_id in team_ids:
            async with session.get(f"{API}/team/{team_id}", headers={"Accept": "application/json"}) as response:
                response.raise_for_status()
                teams.append((team_id, (await response.json())["open"]))

        for team_id, team_open in sorted(teams, key=lambda team: not team[1]):
            arenas = await _get_ndjson(session, f"{API}/team/{team_id}/arena", {"status": "created", "max": 50})
            swisses = await _get_ndjson(session, f"{API}/team/{team_id}/swiss", {"status": "created", "max": 50})
            found = [_from_arena(t, team_id, team_open) for t in arenas]
            found += [_from_swiss(t, team_id, team_open) for t in swisses if t.get("startsAt")]
            for tournament in found:
                tournaments.setdefault(tournament.lichess_id, tournament)

    return sorted(tournaments.values(), key=lambda t: t.starts_at)


async def exists(system: str, lichess_id: str) -> bool:
    """Lichess borra los torneos cancelados, así que un 404 es la única señal de que se cayó."""
    path = "tournament" if system == "arena" else "swiss"
    async with aiohttp.ClientSession(headers={"User-Agent": HEADERS["User-Agent"]}, timeout=TIMEOUT) as session:
        async with session.get(f"{API}/{path}/{lichess_id}") as response:
            if response.status == 404:
                return False
            response.raise_for_status()
            return True


async def _get_ndjson(session: aiohttp.ClientSession, url: str, params: dict) -> list[dict]:
    async with session.get(url, params=params) as response:
        response.raise_for_status()
        text = await response.text()
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _from_arena(t: dict, team_id: str, team_open: bool) -> ChessTournament:
    starts_at = to_local(datetime.fromtimestamp(t["startsAt"] / 1000, tz=timezone.utc))
    limit, increment = t["clock"]["limit"], t["clock"]["increment"]
    variant = t.get("variant", {}).get("key", "standard")
    return ChessTournament(
        lichess_id=t["id"],
        system="arena",
        name=t["fullName"],
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=t["minutes"]),
        clock=_format_clock(limit, increment),
        speed=_speed(limit, increment) if variant == "standard" else t["variant"]["name"],
        rated=t.get("rated", True),
        team_id=team_id,
        team_open=team_open,
        team_battle=t.get("teamBattle", {}).get("teams", []),
    )


def _from_swiss(t: dict, team_id: str, team_open: bool) -> ChessTournament:
    starts_at = to_local(datetime.fromisoformat(t["startsAt"].replace("Z", "+00:00")))
    limit, increment = t["clock"]["limit"], t["clock"]["increment"]
    # El suizo no tiene duración fija: se estima cada ronda como una partida que se juega
    # entera (los dos relojes + 40 jugadas de incremento) más el minuto entre rondas
    round_seconds = 2 * (limit + 40 * increment) + 60
    return ChessTournament(
        lichess_id=t["id"],
        system="swiss",
        name=t["name"],
        starts_at=starts_at,
        ends_at=starts_at + timedelta(seconds=round_seconds * t["nbRounds"]),
        clock=_format_clock(limit, increment),
        speed=_speed(limit, increment) if t.get("variant", "standard") == "standard" else t["variant"],
        rated=t.get("rated", True),
        team_id=team_id,
        team_open=team_open,
        rounds=t["nbRounds"],
    )


def _format_clock(limit: int, increment: int) -> str:
    return f"{limit / 60:g}+{increment}"


def _speed(limit: int, increment: int) -> str:
    estimated = limit + 40 * increment
    return next((name for top, name in _SPEEDS if estimated < top), "Clásica")
