
import os
import json
import asyncio
from pathlib import Path
from urllib.parse import urljoin

import discord
import requests
from bs4 import BeautifulSoup
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
SITE_URL = "https://witanime.site/"
CHANNEL_NAME = "anime alerts"
SEEN_FILE = Path(__file__).with_name("seen_episodes.json")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


def normalize(name):
    return name.lower().replace("_", " ").replace("-", " ").strip()


def fetch_episodes():
    response = requests.get(
        SITE_URL,
        timeout=25,
        headers={"User-Agent": "Mozilla/5.0"}
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
        episodes.append({"title": title, "url": url})

    return episodes


def load_seen():
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            pass
    return None


def save_seen(seen):
    SEEN_FILE.write_text(
        json.dumps(sorted(seen), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


@bot.event
async def on_ready():
    print(f"Bot is online: {bot.user}")

    if not monitor_episodes.is_running():
        monitor_episodes.start()


@bot.command()
async def ping(ctx):
    await ctx.send("Pong! Anime Alerts is working.")


@tasks.loop(minutes=5)
async def monitor_episodes():
    try:
        episodes = await asyncio.to_thread(fetch_episodes)

        if not episodes:
            print("No episode links found. Will retry.")
            return

        seen = load_seen()

        # First run: save existing episodes without sending old alerts.
        if seen is None:
            save_seen({ep["url"] for ep in episodes})
            print(f"Initial scan complete: {len(episodes)} links saved.")
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


@monitor_episodes.before_loop
async def before_monitor():
    await bot.wait_until_ready()


if not TOKEN:
    raise ValueError("DISCORD_TOKEN is missing from .env")


bot.run(TOKEN)
