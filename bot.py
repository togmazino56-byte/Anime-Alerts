
import os
import json
import asyncio
from pathlib import Path
from urllib.parse import urljoin

import discord
import cloudscraper
from bs4 import BeautifulSoup
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
SITE_URL = "https://witanime.site/"
CHANNEL_NAME = "anime alerts"
SEEN_FILE = Path(__file__).with_name("seen_episodes.json")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


def normalize(name):
    return name.lower().replace("_", " ").replace("-", " ").strip()


def fetch_episodes():
    scraper = cloudscraper.create_scraper(
        browser={
            "browser": "chrome",
            "platform": "windows",
            "desktop": True
        }
    )

    response = scraper.get(
        SITE_URL,
        timeout=25,
        headers={
            "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
            "Referer": SITE_URL
        }
    )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    episodes = []
    found = set()

    for a in soup.select('a[href*="/watch/"]'):
        url = urljoin(SITE_URL, a.get("href", ""))
        title = a.get_text(" ", strip=True)

        if "/watch/" not in url or not title or url in found:
            continue

        found.add(url)
        episodes.append({
            "title": title,
            "url": url
        })

    return episodes


def load_seen():
    if SEEN_FILE.exists():
        try:
            return set(json.loads(
                SEEN_FILE.read_text(encoding="utf-8")
            ))
        except (ValueError, OSError):
            pass

    return None


def save_seen(seen):
    SEEN_FILE.write_text(
        json.dumps(
            sorted(seen),
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


@bot.event
async def on_ready():
    print(f"Bot connected: {bot.user}")

    try:
        episodes = await asyncio.to_thread(fetch_episodes)

        if not episodes:
            print("No episode links found.")
            return

        seen = load_seen()

        if seen is None:
            save_seen({ep["url"] for ep in episodes})
            print("Initial scan saved; no old alerts sent.")
            return

        channel = next(
            (
                c for c in bot.get_all_channels()
                if isinstance(c, discord.TextChannel)
                and normalize(c.name) == normalize(CHANNEL_NAME)
            ),
            None
        )

        if channel is None:
            print(f"Channel not found: {CHANNEL_NAME}")
            return

        for ep in reversed(episodes):
            if ep["url"] in seen:
                continue

            await channel.send(
                f"🆕 **حلقة جديدة على WitAnime!**\n"
                f"**{ep['title']}**\n{ep['url']}"
            )

            seen.add(ep["url"])
            save_seen(seen)
            print(f"Notification sent: {ep['title']}")

    except Exception as e:
        print(f"Monitoring error: {e}")

    finally:
        await bot.close()


if not TOKEN:
    raise ValueError("DISCORD_TOKEN is missing")


bot.run(TOKEN)
