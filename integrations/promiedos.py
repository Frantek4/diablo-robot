import json
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime
import re
from zoneinfo import ZoneInfo
from config.settings import settings
from models.fixture import Fixture

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}


async def scrape_next_match(team_url: str) -> Fixture | None:
    """Scrapes the next match information from Promiedos website"""
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        # Primera request: página del equipo
        async with session.get(team_url) as response:
            response.raise_for_status()
            team_content = await response.read()

        team_soup = BeautifulSoup(team_content, 'html.parser')

        match_url = _extract_match_url(team_soup)
        if match_url is None:
            return None

        # Segunda request: página del partido
        async with session.get(match_url) as response:
            response.raise_for_status()
            match_content = await response.read()

    match_soup = BeautifulSoup(match_content, 'html.parser')
    return _parse_match(match_soup)


def _extract_match_url(team_soup: BeautifulSoup) -> str | None:
    """Extrae la URL del próximo partido desde los scripts de la página del equipo"""
    scripts = team_soup.find_all('script')
    for script in scripts:
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
            games = (
                data.get("props", {})
                .get("pageProps", {})
                .get("data", {})
                .get("games", {})
                .get("next", {})
                .get("rows", [])
            )
            if games:
                game = games[0].get("game", {})
                url_name = game.get("url_name")
                game_id = game.get("id")
                if url_name and game_id:
                    return f"https://www.promiedos.com.ar/game/{url_name}/{game_id}"
        except (json.JSONDecodeError, AttributeError):
            continue
    return None


def _parse_match(match_soup: BeautifulSoup) -> Fixture | None:
    """Parsea la página del partido y devuelve un Fixture"""
    home_team = "A confirmar"
    away_team = "A confirmar"
    competition = "Competición"
    venue = None
    referee = None
    tv_channels = None

    # Equipos y competición desde meta description
    meta_tag = match_soup.find('meta', attrs={'name': 'description'})
    if meta_tag:
        description = meta_tag.get('content', '')
        teams_match = re.search(r"^(.*?)\s+vs\.?\s+(.*?)\s+en\s+([^\.]+)\.", description)
        if teams_match:
            home_team = teams_match.group(1).strip()
            away_team = teams_match.group(2).strip()
            competition = teams_match.group(3).strip()

    # Fecha y hora
    soup_str = str(match_soup)
    time_match = re.search(r'"start_time":"(\d{2}-\d{2}-\d{4} \d{2}:\d{2})"', soup_str)
    if time_match is None:
        return None

    start_time_str = time_match.group(1)
    match_datetime = datetime.strptime(start_time_str, "%d-%m-%Y %H:%M")

    now = datetime.now(settings.TIMEZONE)

    if match_datetime.replace(year=now.year) > now.replace(tzinfo=None):
        match_datetime = match_datetime.replace(year=now.year)
    else:
        match_datetime = match_datetime.replace(year=now.year + 1)

    match_date = match_datetime.replace(tzinfo=settings.TIMEZONE)

    # Datos adicionales
    venue = _extract_field(soup_str, r'Estadio')
    referee = _extract_field(soup_str, r'Árbitro')
    tv_channels = _extract_field(soup_str, r'Arg TV')

    return Fixture(
        home_team=home_team,
        away_team=away_team,
        match_date=match_date,
        competition=competition,
        venue=venue,
        referee=referee,
        tv_channels=tv_channels
    )


def _extract_field(soup_str: str, label: str) -> str | None:
    """Extrae un campo (Estadio, Árbitro, Arg TV) del HTML del partido"""
    pattern = rf'{label}\s*(.*?)(?=\s*[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]*\s*:|\s*$)'
    match = re.search(pattern, soup_str, re.DOTALL)
    if not match:
        return None

    potential = match.group(1).strip()
    if not potential or re.match(r'^[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]*\s*:$', potential):
        return None

    try:
        return potential.split('"')[4]
    except IndexError:
        return potential