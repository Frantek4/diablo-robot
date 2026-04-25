# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Bot

```bash
python main.py
```

Requires MongoDB running (see `DATABASE_URL` in `.env`). All required environment variables are validated at startup in `main.py`.

## Architecture

**Diablo Robot** is an async Discord bot (`discord.py`) for Club Atlético Independiente's server. It tracks football fixtures, posts live match commentary, and aggregates news/social media.

### Layer Structure

- **`main.py`** — Entry point: validates env vars, creates bot, starts run loop
- **`config/settings.py`** — Pydantic BaseSettings loading all env vars; `config/database.py` — MongoDB singleton
- **`bot/client.py`** — `DiabloRobot` class; `setup_hook()` loads all cogs/commands/listeners/schedulers; `on_ready()` starts scheduled tasks
- **`bot/commands/`** — Prefix commands (`!cmd`); admin-only ones check guild permissions
- **`bot/scheduled/`** — Background `tasks.loop` coroutines started in `on_ready()`; each runs independently
- **`bot/cogs/`** — Stateful Discord cogs (fixture event creation, event lifecycle)
- **`bot/listeners/`** — Event handler cogs (reactions, event announcements)
- **`bot/config/messager.py`** — Centralized message dispatcher; holds references to all channel objects
- **`data_access/`** — DAO classes wrapping raw PyMongo queries; one DAO per MongoDB collection
- **`models/`** — Pydantic-style dataclasses; `fixture.py` handles emoji formatting and change detection
- **`integrations/`** — Web scrapers (BeautifulSoup + aiohttp) for Promiedos, Olé, TycSports, DobleAmarilla, Twitter (via Nitter RSS), YouTube RSS

### Data Flow

1. **Fixture check** (`bot/scheduled/fixture_check.py`, 1h loop): scrapes Promiedos → upserts into `fixtures` collection → `FixtureEventCreator` cog creates/updates Discord scheduled events
2. **Live match** (`bot/scheduled/live_match_scheduler.py`, 1min loop): polls Promiedos for live scores/events → posts to `#comentador` channel via messager
3. **News** (`bot/scheduled/news_check.py`, 1h loop): scrapes Olé/TycSports/DobleAmarilla → deduplicates via `news` collection → posts to `#prensa` or `#club` channel
4. **Social media** (`twitter_check.py`, `youtube_check.py`): fetches RSS → posts new entries to configured channels

### Key Patterns

- All DAOs follow: `insert()`, `get_*()`, `exists()`, `upsert()`, `update_*()` — raw PyMongo, no ORM
- Adding a new command: create file in `bot/commands/`, add `await bot.load_extension('bot.commands.filename')` in `bot/client.py`
- Adding a new scheduled task: create file in `bot/scheduled/` with a `setup(bot)` function; load it in `client.py`
- Discord channel IDs are env vars loaded via settings object on `config/settings.py` and accessed through the messager

### MongoDB Collections

| Collection | Purpose |
|---|---|
| `fixtures` | Match data: teams, date, score, status, competition |
| `games` | Game channels: game_name, message_id, text_channel_id |
| `news` | URL deduplication to prevent duplicate news posts |
| `influencers` | Social media accounts: platform, account_id, source type |

### Teams Tracked

Defined in `models/team_url.py` as an enum with Promiedos URLs: Profesional Masculino, Reserva Masculino, Femenino, Selección Nacional, Selección Sub-20.

## Environment Variables

All defined in `config/settings.py`. Required vars are also validated at startup in `main.py`. Key ones:

- `DISCORD_TOKEN`, `GUILD_ID` — Discord auth
- `DATABASE_URL`, `DATABASE_USERNAME`, `DATABASE_PASSWORD` — MongoDB
- `TWITTER_RSS_BRIDGE_URL` — Nitter instance for Twitter RSS (default: `http://nitter.net`)
- Channel IDs: `GENERAL_TEXT_CHANNEL_ID`, `ANNOUNCEMENTS_TEXT_CHANNEL_ID`, `CLUB_TEXT_CHANNEL_ID`, `PRESS_TEXT_CHANNEL_ID`, `COMMENTATOR_TEXT_CHANNEL_ID`, `GAMES_TEXT_CHANNEL_ID`, `ROBOT_DEVIL_TEXT_CHANNEL_ID`
- `GENERAL_VOICE_CHANNEL_ID`, `TERMOS_VOICE_CHANNEL_ID` — Text and voice channels with automatization processes
- `GAMES_CATEGORY_ID`, `GENERAL_CATEGORY_ID` — Category IDs for channel organization
- `FOOTBALL_FORUM_ID` — Forum channel for match discussion
