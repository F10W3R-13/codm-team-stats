# Discord slash command Cog
#
# /stats       Player overall stats (HP + SND averages)
# /compare     Compare two players
# /lastmatch   Recall the most recent match
# /leaderboard Mode-based ranking
# /matchreport Match analysis report (MOM, team avg, AI insight)
# /weekly      Trend report over N days
# /trend       Player form analysis
# /addalias    Register an IGN → player mapping
# /removealias Delete an IGN mapping
# /listalias   List IGN mappings
#
# All responses are in English (player-facing).

import discord
from discord import app_commands
from discord.ext import commands

import queries
import analytics
import report_embeds
import metrics
import db as dbmod


class StatsCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── /stats ────────────────────────────────────────────────────────────
    @app_commands.command(name="stats", description="Show a player's average stats")
    @app_commands.describe(player="Player name (e.g. Shisui)")
    async def stats(self, interaction: discord.Interaction, player: str):
        pid = queries.get_player_id(player)
        if not pid:
            await interaction.response.send_message(
                f"❌ Player `{player}` not found.\n"
                f"Registered players: {', '.join(queries.list_players())}",
                ephemeral=True,
            )
            return

        s = queries.player_overall_stats(pid)
        embed = discord.Embed(
            title=f"📊 {s['name']} Stats",
            color=0x2ECC71,
        )

        # HP section + custom metrics
        if s["hp"]:
            h = s["hp"]
            adv = metrics.all_hp_metrics(
                h["avg_k"], h["avg_d"], h["avg_obj"],
                h["avg_score"], h["avg_impact"],
                h["avg_dmg"], h["avg_capture"],
            )
            embed.add_field(
                name=f"🎯 Hardpoint ({h['matches']} matches)",
                value=(
                    f"```\n"
                    f"K/D      : {h['avg_k']}/{h['avg_d']}  ({h['avg_kd']})\n"
                    f"Avg Kills: {h['avg_k']}\n"
                    f"Avg Deaths: {h['avg_d']}\n"
                    f"OBJ (sec): {h['avg_obj']}\n"
                    f"Score    : {h['avg_score']:.0f}\n"
                    f"Impact   : {h['avg_impact']:.0f}\n"
                    f"Total DMG: {h['avg_dmg']:.0f}\n"
                    f"Cap Kill : {h['avg_capture']}\n"
                    f"```"
                ),
                inline=False,
            )
            embed.add_field(
                name="🧮 Advanced Metrics",
                value=(
                    f"```\n"
                    f"DPD : {adv['dpd']}  (DMG/Death)\n"
                    f"DPK : {adv['dpk']}  (DMG/Kill)\n"
                    f"ID  : {adv['impact_delta']}  (Impact−Score/34)\n"
                    f"AP% : {adv['ap_pct']}  (CapKill/Kills)\n"
                    f"ZCS : {adv['zcs']}  (Zone Control)\n"
                    f"```"
                ),
                inline=False,
            )
        else:
            embed.add_field(name="🎯 Hardpoint", value="No data", inline=False)

        # SND section
        if s["snd"]:
            sn = s["snd"]
            embed.add_field(
                name=f"🔍 Search & Destroy ({sn['matches']} matches)",
                value=(
                    f"```\n"
                    f"K/D/A     : {sn['avg_k']}/{sn['avg_d']}/{sn['avg_a']}  ({sn['avg_kd']})\n"
                    f"Avg Kills: {sn['avg_k']}\n"
                    f"Avg Deaths: {sn['avg_d']}\n"
                    f"Avg Assists: {sn['avg_a']}\n"
                    f"Score     : {sn['avg_score']:.0f}\n"
                    f"Impact    : {sn['avg_impact']:.0f}\n"
                    f"ADR       : {sn['avg_adr']:.0f}\n"
                    f"First Kill: {sn['avg_fk']}\n"
                    f"Lone Wolf : {sn['avg_lww']}\n"
                    f"```"
                ),
                inline=False,
            )
        else:
            embed.add_field(name="🔍 Search & Destroy", value="No data", inline=False)

        embed.set_footer(text="All-time averages")
        await interaction.response.send_message(embed=embed)

    # ── /compare ──────────────────────────────────────────────────────────
    @app_commands.command(name="compare", description="Compare two players' stats")
    @app_commands.describe(player_a="Player 1", player_b="Player 2", mode="HP or SND (default HP)")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Hardpoint (HP)", value="HP"),
        app_commands.Choice(name="Search & Destroy (SND)", value="SND"),
    ])
    async def compare(
        self,
        interaction: discord.Interaction,
        player_a: str,
        player_b: str,
        mode: app_commands.Choice[str] = None,
    ):
        m = mode.value if mode else "HP"
        pa = queries.get_player_id(player_a)
        pb = queries.get_player_id(player_b)
        if not pa or not pb:
            missing = player_a if not pa else player_b
            await interaction.response.send_message(
                f"❌ Player `{missing}` not found.\n"
                f"Registered players: {', '.join(queries.list_players())}",
                ephemeral=True,
            )
            return

        sa = queries.player_overall_stats(pa)
        sb = queries.player_overall_stats(pb)
        key = "hp" if m == "HP" else "snd"
        ha = sa[key]
        hb = sb[key]

        if not ha or not hb:
            await interaction.response.send_message(
                f"❌ Not enough {m} data (both players need records).",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"⚔️ {sa['name']} vs {sb['name']} ({m})",
            color=0xE67E22,
        )

        if m == "HP":
            rows = [
                ("Matches", ha["matches"], hb["matches"], False),
                ("Avg K/D", ha["avg_kd"], hb["avg_kd"], True),
                ("Avg Kills", ha["avg_k"], hb["avg_k"], True),
                ("Avg Deaths", ha["avg_d"], hb["avg_d"], False),
                ("OBJ (sec)", ha["avg_obj"], hb["avg_obj"], True),
                ("Score", ha["avg_score"], hb["avg_score"], True),
                ("Impact", ha["avg_impact"], hb["avg_impact"], True),
                ("Total DMG", ha["avg_dmg"], hb["avg_dmg"], True),
                ("Cap Kill", ha["avg_capture"], hb["avg_capture"], True),
            ]
        else:
            rows = [
                ("Matches", ha["matches"], hb["matches"], False),
                ("Avg K/D", ha["avg_kd"], hb["avg_kd"], True),
                ("Avg Kills", ha["avg_k"], hb["avg_k"], True),
                ("Avg Deaths", ha["avg_d"], hb["avg_d"], False),
                ("Avg Assists", ha["avg_a"], hb["avg_a"], True),
                ("Score", ha["avg_score"], hb["avg_score"], True),
                ("Impact", ha["avg_impact"], hb["avg_impact"], True),
                ("ADR", ha["avg_adr"], hb["avg_adr"], True),
                ("First Kill", ha["avg_fk"], hb["avg_fk"], True),
                ("Lone Wolf", ha["avg_lww"], hb["avg_lww"], True),
            ]

        lower_better = {"Avg Deaths"}
        text = "```\n"
        text += f"{'Metric':<14}{'':<3}{sa['name']:<12}{sb['name']:<12}\n"
        text += "-" * 52 + "\n"
        for label, va, vb, higher_better in rows:
            mark_a = mark_b = "  "
            try:
                a_f, b_f = float(va), float(vb)
                if label in lower_better:
                    if a_f < b_f:
                        mark_a = "◀ "
                    elif b_f < a_f:
                        mark_b = " ◀"
                elif higher_better:
                    if a_f > b_f:
                        mark_a = "▶ "
                    elif b_f > a_f:
                        mark_b = " ◀"
            except (ValueError, TypeError):
                pass
            text += f"{label:<14}{mark_a:<3}{str(va):<12}{str(vb):<12}{mark_b}\n"
        text += "```\n* ◀ = leads this metric"

        embed.description = text
        embed.set_footer(text="All-time averages")
        await interaction.response.send_message(embed=embed)

    # ── /lastmatch ────────────────────────────────────────────────────────
    @app_commands.command(name="lastmatch", description="Show the most recent match result")
    @app_commands.describe(mode="HP or SND (default: overall most recent)")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Hardpoint (HP)", value="HP"),
        app_commands.Choice(name="Search & Destroy (SND)", value="SND"),
    ])
    async def lastmatch(
        self,
        interaction: discord.Interaction,
        mode: app_commands.Choice[str] = None,
    ):
        m = mode.value if mode else None
        lm = queries.last_match_summary(mode=m)
        if not lm:
            await interaction.response.send_message(
                "❌ No match records found for that filter.", ephemeral=True
            )
            return

        mode_name = "Hardpoint" if lm["mode"] == "HP" else "Search & Destroy"
        embed = discord.Embed(
            title=f"🎮 Match #{lm['match_id']} — {mode_name}",
            color=0x9B59B6,
        )
        date_str = lm["match_date"] or "Unknown date"
        map_str = lm["map_name"] or "Unknown map"
        embed.add_field(name="📅 Date", value=date_str, inline=True)
        embed.add_field(name="🗺️ Map", value=map_str, inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)

        if lm["mode"] == "HP":
            text = "```\n"
            text += f"{'Player':<10}{'K':>4}{'D':>4}{'K/D':>6}{'Score':>8}{'DMG':>7}\n"
            text += "-" * 42 + "\n"
            for p in lm["players"]:
                text += f"{p['name']:<10}{p['k']:>4}{p['d']:>4}{str(p['kd']):>6}{p['score']:>8}{p['dmg']:>7}\n"
            text += "```"
        else:
            text = "```\n"
            text += f"{'Player':<10}{'K':>4}{'D':>4}{'A':>4}{'K/D':>6}{'Score':>8}{'ADR':>6}\n"
            text += "-" * 44 + "\n"
            for p in lm["players"]:
                text += f"{p['name']:<10}{p['k']:>4}{p['d']:>4}{p['a']:>4}{str(p['kd']):>6}{p['score']:>8}{str(p['adr']):>6}\n"
            text += "```"
        embed.description = text

        await interaction.response.send_message(embed=embed)

    # ── /leaderboard ──────────────────────────────────────────────────────
    @app_commands.command(name="leaderboard", description="Show the team ranking")
    @app_commands.describe(
        mode="HP or SND (default HP)",
        metric="Sort metric (default K/D)",
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="Hardpoint (HP)", value="HP"),
        app_commands.Choice(name="Search & Destroy (SND)", value="SND"),
    ])
    @app_commands.choices(metric=[
        app_commands.Choice(name="K/D", value="avg_kd"),
        app_commands.Choice(name="Avg Kills", value="avg_k"),
        app_commands.Choice(name="Avg DMG/Score", value="avg_dmg"),
        app_commands.Choice(name="Avg Score", value="avg_score"),
        app_commands.Choice(name="DPD (DMG/Death)", value="dpd"),
        app_commands.Choice(name="DPK (DMG/Kill)", value="dpk"),
        app_commands.Choice(name="ID (Impact Delta)", value="impact_delta"),
        app_commands.Choice(name="AP% (Cap Ratio)", value="ap_pct"),
        app_commands.Choice(name="ZCS (Zone Control)", value="zcs"),
    ])
    async def leaderboard(
        self,
        interaction: discord.Interaction,
        mode: app_commands.Choice[str] = None,
        metric: app_commands.Choice[str] = None,
    ):
        m = mode.value if mode else "HP"
        met = metric.value if metric else "avg_kd"
        custom = {"dpd", "dpk", "impact_delta", "ap_pct", "zcs"}
        if met in custom:
            rows = queries.advanced_leaderboard(met, 15)
        else:
            rows = queries.leaderboard(mode=m, metric=met, limit=15)

        if not rows:
            await interaction.response.send_message(
                "❌ No ranking data available.", ephemeral=True
            )
            return

        metric_label = {
            "avg_kd": "K/D", "avg_k": "Avg Kills",
            "avg_dmg": "Avg DMG/Score", "avg_score": "Avg Score",
            "dpd": "DPD", "dpk": "DPK", "impact_delta": "ID",
            "ap_pct": "AP%", "zcs": "ZCS",
        }.get(met, met)

        embed = discord.Embed(
            title=f"🏆 {m} Leaderboard — {metric_label}",
            color=0xF1C40F,
        )
        text = "```\n"
        text += f"{'#':<3}{'Player':<12}{'Matches':>7}{'':<2}{metric_label:>10}\n"
        text += "-" * 38 + "\n"
        for i, r in enumerate(rows, 1):
            medal = ""
            if i == 1:
                medal = "🥇"
            elif i == 2:
                medal = "🥈"
            elif i == 3:
                medal = "🥉"
            text += f"{i:<3}{r['name']:<12}{r['matches']:>7}{'':<2}{str(r['value']):>10} {medal}\n"
        text += "```"
        embed.description = text

        await interaction.response.send_message(embed=embed)

    # ── /matchreport ──────────────────────────────────────────────────────
    @app_commands.command(name="matchreport", description="Match analysis report (MOM, team avg, AI insight)")
    @app_commands.describe(match_id="Match number (defaults to most recent)")
    async def matchreport(self, interaction: discord.Interaction, match_id: int = None):
        if match_id is None:
            match_id = analytics.last_match_id()
        if match_id is None:
            await interaction.response.send_message(
                "❌ No match records exist.", ephemeral=True
            )
            return

        await interaction.response.defer()
        embed = report_embeds.build_match_report_embed(match_id)
        if not embed:
            await interaction.followup.send(
                f"❌ Match #{match_id} not found.", ephemeral=True
            )
            return
        await interaction.followup.send(embed=embed)

    # ── /weekly ───────────────────────────────────────────────────────────
    @app_commands.command(name="weekly", description="Trend report over the last N days (K/D change + AI insight)")
    @app_commands.describe(days="Number of days (default 7)")
    async def weekly(self, interaction: discord.Interaction, days: int = 7):
        if days < 1 or days > 90:
            await interaction.response.send_message(
                "❌ days must be between 1 and 90.", ephemeral=True
            )
            return
        await interaction.response.defer()
        embed = report_embeds.build_weekly_report_embed(days)
        if not embed:
            await interaction.followup.send(
                f"❌ No match data in the last {days} days.", ephemeral=True
            )
            return
        await interaction.followup.send(embed=embed)

    # ── /trend ────────────────────────────────────────────────────────────
    @app_commands.command(name="trend", description="Player form analysis (recent vs overall avg + AI diagnosis)")
    @app_commands.describe(
        player="Player name",
        recent="Based on last N matches (default 10)",
    )
    async def trend(
        self,
        interaction: discord.Interaction,
        player: str,
        recent: int = 10,
    ):
        if not queries.player_exists(player):
            await interaction.response.send_message(
                f"❌ Player `{player}` not found.\n"
                f"Registered players: {', '.join(queries.list_players())}",
                ephemeral=True,
            )
            return
        await interaction.response.defer()
        embed = report_embeds.build_trend_embed(player, recent)
        if not embed:
            await interaction.followup.send(
                f"❌ Not enough data for `{player}`.", ephemeral=True
            )
            return
        await interaction.followup.send(embed=embed)

    # ── /addalias ─────────────────────────────────────────────────────────
    @app_commands.command(name="addalias", description="Register an IGN → player mapping")
    @app_commands.describe(
        ign="In-game nickname shown on screen (e.g. BLACKPINK)",
        player="Standard player name (e.g. Cartels)",
    )
    async def addalias(self, interaction: discord.Interaction, ign: str, player: str):
        result = dbmod.add_alias(ign, player)
        if result["ok"]:
            await interaction.response.send_message(f"✅ `{ign}` → `{player}` registered")
        else:
            await interaction.response.send_message(f"⚠️ {result['message']}", ephemeral=True)

    # ── /removealias ──────────────────────────────────────────────────────
    @app_commands.command(name="removealias", description="Delete an IGN mapping")
    @app_commands.describe(ign="Nickname to remove")
    async def removealias(self, interaction: discord.Interaction, ign: str):
        result = dbmod.remove_alias(ign)
        if result["ok"]:
            await interaction.response.send_message(
                f"🗑️ `{ign}` (→ {result['player']}) removed"
            )
        else:
            await interaction.response.send_message(f"⚠️ {result['message']}", ephemeral=True)

    # ── /listalias ────────────────────────────────────────────────────────
    @app_commands.command(name="listalias", description="List IGN mappings")
    @app_commands.describe(player="Filter to a specific player (optional)")
    async def listalias(self, interaction: discord.Interaction, player: str = None):
        aliases = dbmod.list_aliases(player)
        if not aliases:
            msg = "No aliases registered." if not player else f"No aliases for `{player}`."
            await interaction.response.send_message(msg, ephemeral=True)
            return

        embed = discord.Embed(
            title="🏷️ IGN Mappings" + (f" — {player}" if player else ""),
            color=0x95A5A6,
        )
        by_player = {}
        for a in aliases:
            by_player.setdefault(a["player_name"], []).append(a["ign"])

        for pname, igns in sorted(by_player.items()):
            embed.add_field(
                name=pname,
                value=", ".join(f"`{i}`" for i in igns),
                inline=False,
            )
        embed.set_footer(text=f"{len(aliases)} aliases total")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(StatsCommands(bot))
