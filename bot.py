
import os
import json
import asyncio
from pathlib import Path
from urllib.parse import urljoin

import discord
from bs4 import BeautifulSoup
from discord.ext import commands
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
SITE_URL = "https://witanime.site/"
CHANNEL_NAME = "anime alerts"
SEEN_FILE = Path(__file__).with_name("seen_episodes.json")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


def normalize(name):
    return name.lower().replace("_", " ").replace("-", " ").strip()


async def fetch_episodes():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        try:
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                locale="ar",
            )

            page = await context.new_page()

            response = await page.goto(
                SITE_URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            if response is None:
                raise RuntimeError(
                    "WitAnime returned no main document response."
                )

            print(f"WitAnime HTTP status: {response.status}")
            print(f"Final page URL: {page.url}")
            print(f"Page title: {await page.title()}")

            if response.status >= 400:
                raise RuntimeError(
                    f"WitAnime returned HTTP {response.status}"
                )

            await page.wait_for_timeout(3000)
            html = await page.content()

            soup = BeautifulSoup(html, "html.parser")
            episodes = []
            found = set()

            for a in soup.select('a[href*="/watch/"]'):
                url = urljoin(SITE_URL, a.get("href", ""))
                title = a.get_text(" ", strip=True)

                if (
                    "/watch/" not in url
                    or not title
                    or url in found
                ):
                    continue

                found.add(url)
                episodes.append({
                    "title": title,
                    "url": url,
                })

            print(f"Episode links found: {len(episodes)}")
            return episodes

        finally:
            await browser.close()


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
            indent=2,
        ),
        encoding="utf-8",
    )


@bot.event
async def on_ready():
    print(f"Bot connected: {bot.user}")

    try:
        episodes = await fetch_episodes()

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
            None,
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
