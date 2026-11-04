# Discord slash commands for the coaching brain (player-facing, EN/ES)
#
# /ask       Ask the coaching brain a question (answer in the question's language)
# /reminder  Post a pre-scrim reminder for today's maps (EN or ES)
#
# Answers come only from "coaching brain/player-guide" (see player_guide.py).
# Uses the same OpenAI-compatible client/model as the stats bot (config.OPENAI_MODEL).

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

import config
import player_guide as pg

log = logging.getLogger(__name__)

_client = None
MAP_CHOICES = [app_commands.Choice(name=n, value=v) for v, n in [
    ("takeoff", "Takeoff"), ("combine", "Combine"), ("hacienda", "Hacienda"), ("summit", "Summit"),
    ("arsenal", "Arsenal"), ("raid", "Raid"), ("standoff", "Standoff"), ("crossroads-strike", "Crossroads Strike"),
    ("firing-range", "Firing Range"), ("coastal", "Coastal"), ("slums", "Slums")]]
NO_PINGS = discord.AllowedMentions.none()


def _openai():
    global _client
    if _client is None:
        from openai import OpenAI  # lazy: same RAM-saving pattern as bot.py
        _client = OpenAI(api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL)
    return _client


def _answer(context: str, question: str) -> str:
    r = _openai().chat.completions.create(
        model=config.OPENAI_MODEL,
        messages=[{"role": "system", "content": context}, {"role": "user", "content": question}],
        **config.chat_params(0.2, 1500),
    )
    return (r.choices[0].message.content or "").strip()


class CoachCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ask", description="Ask Coach Flower's notes (English or Spanish)")
    @app_commands.describe(question="Your question, e.g. 'Takeoff P3, they hold it — what do we do?'",
                           map="Optional: limit the answer to one map",
                           private="Only you see the answer (default: everyone in the channel)")
    @app_commands.choices(map=MAP_CHOICES)
    async def ask(self, interaction: discord.Interaction, question: str,
                  map: app_commands.Choice[str] | None = None, private: bool = False):
        await interaction.response.defer(thinking=True, ephemeral=private)
        context, maps = pg.build_context(question, map.value if map else None)
        try:
            text = await asyncio.to_thread(_answer, context, question)
        except Exception:
            log.exception("/ask failed")
            await interaction.followup.send("Couldn't reach the AI right now — try again in a minute.", ephemeral=True)
            return
        if not text:
            text = "No answer came back — try asking it differently."
        scope = ", ".join(maps) if maps else "all maps"
        body = f"> **Q:** {question}\n-# notes used: {scope}\n\n{text}"
        for chunk in pg.split_message(body):
            await interaction.followup.send(chunk, ephemeral=private, allowed_mentions=NO_PINGS)

    @app_commands.command(name="reminder", description="Post a pre-scrim reminder for today's maps")
    @app_commands.describe(opponent="Opponent team, e.g. UD",
                           maps="Map keys separated by spaces, e.g. 'takeoff coastal'",
                           language="en or es",
                           fix="What the team agreed to fix last time (optional — replaces the defaults)")
    @app_commands.choices(language=[app_commands.Choice(name="English", value="en"),
                                    app_commands.Choice(name="Español", value="es")])
    @app_commands.default_permissions(manage_messages=True)
    async def reminder(self, interaction: discord.Interaction, opponent: str, maps: str,
                       language: app_commands.Choice[str], fix: str | None = None):
        keys = [k.strip().lower() for k in maps.replace(",", " ").split() if k.strip()]
        try:
            msgs = pg.build_reminder(language.value, opponent, keys, [fix] if fix else None)
        except KeyError as e:
            valid = " ".join(c.value for c in MAP_CHOICES)
            await interaction.response.send_message(f"Unknown map {e}. Use: `{valid}`", ephemeral=True)
            return
        await interaction.response.send_message(msgs[0], allowed_mentions=NO_PINGS)
        for m in msgs[1:]:
            await interaction.followup.send(m, allowed_mentions=NO_PINGS)


async def setup(bot: commands.Bot):
    await bot.add_cog(CoachCommands(bot))
