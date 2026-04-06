import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re
import pytz
from config.settings import settings
from models.fixture import Fixture

def scrape_next_match(team_url: str) -> Fixture | None:
    """Scrapes the next match information from Promiedos website"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    team_html = requests.get(team_url, headers=headers)
    team_html.raise_for_status()
    
    team_soup = BeautifulSoup(team_html.content, 'html.parser')

    match_url = None

    scripts = team_soup.find_all('script')
    for script in scripts:
        if script.string:
            try:
                data = json.loads(script.string)
                games = data.get("props", {}).get("pageProps", {}).get("data", {}).get("games", {}).get("next", {}).get("rows", [])
                if games:
                    game_data = games[0] 
                    game = game_data.get("game", {})
                    url_name = game.get("url_name")
                    game_id = game.get("id")
                    if url_name and game_id:
                         match_url = f"https://www.promiedos.com.ar/game/{url_name}/{game_id}"
            except json.JSONDecodeError:
                continue

    if match_url is None:
        return None
    
    match_html = requests.get(match_url, headers=headers)
    match_html.raise_for_status()

    match_soup = BeautifulSoup(match_html.content, 'html.parser')

    home_team = "A confirmar"
    away_team = "A confirmar"
    competition = "Competición"
    venue = None
    referee = None
    tv_channels = None

    meta_description_tag = match_soup.find('meta', attrs={'name': 'description'})
    if meta_description_tag:
        description_content = meta_description_tag.get('content', '')
        match = re.search(r"^(.*?)\s+vs\.?\s+(.*?)\s+en\s+([^\.]+)\.", description_content)
        if match:
            home_team = match.group(1).strip()
            away_team = match.group(2).strip()
            competition = match.group(3).strip()
    
    time_pattern = r'"start_time":"(\d{2}-\d{2}-\d{4} \d{2}:\d{2})"'
    match = re.search(time_pattern, str(match_soup))

    start_time_str = match.group(1)
    match_datetime = datetime.strptime(start_time_str, "%d-%m-%Y %H:%M")
    
    if match_datetime > datetime.today():
        match_datetime = match_datetime.replace(year=datetime.now(settings.TIMEZONE).year)
    else:
        match_datetime = match_datetime.replace(year=datetime.now(settings.TIMEZONE).year + 1)


    tz = settings.TIMEZONE
    match_date = tz.localize(match_datetime)

    stadium_match = re.search(r'Estadio\s*(.*?)(?=\s*[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]*\s*:|\s*$)', str(match_soup), re.DOTALL)
    if stadium_match:
        potential_stadium = stadium_match.group(1).strip()
        if potential_stadium and not re.match(r'^[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]*\s*:$', potential_stadium):
            try:
                venue = potential_stadium.split('"')[4]
            except IndexError:
                venue = potential_stadium

    referee_match = re.search(r'Árbitro\s*(.*?)(?=\s*[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]*\s*:|\s*$)', str(match_soup), re.DOTALL)
    if referee_match:
        potential_referee = referee_match.group(1).strip()
        if potential_referee and not re.match(r'^[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]*\s*:$', potential_referee):
            try:
                referee = potential_referee.split('"')[4]
            except IndexError:
                referee = potential_referee

    tv_match = re.search(r'Arg TV\s*(.*?)(?=\s*[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]*\s*:|\s*$)', str(match_soup), re.DOTALL)
    if tv_match:
        potential_tv = tv_match.group(1).strip()
        if potential_tv and not re.match(r'^[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]*\s*:$', potential_tv):
            try:
                tv_channels = potential_tv.split('"')[4]
            except IndexError:
                tv_channels = potential_tv

    return Fixture(
        home_team=home_team,
        away_team=away_team,
        match_date=match_date,
        competition=competition,
        venue=venue,
        referee=referee,
        tv_channels=tv_channels
    )