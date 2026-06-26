# Match / Weekly / Trend report Embed builders
#
# Combines analytics.py data + analytics_insights.py GPT insights into
# Discord Embed objects. Shared by the bot (auto trigger) and commands.

import discord

import analytics
import analytics_insights


def build_match_report_embed(match_id: int, include_insight: bool = True) -> discord.Embed | None:
    """Build a match report Embed. Returns None if match doesn't exist."""
    r = analytics.match_report(match_id)
    if not r:
        return None

    mode_name = "Hardpoint" if r["mode"] == "HP" else "Search & Destroy"
    mode_emoji = "🎯" if r["mode"] == "HP" else "🔍"
    embed = discord.Embed(
        title=f"{mode_emoji} Match Report #{match_id} — {mode_name}",
        color=0x9B59B6,
    )
    date_str = r["match_date"] or "Unknown date"
    map_str = r["map_name"] or "Unknown map"
    embed.add_field(name="📅 Date", value=date_str, inline=True)
    embed.add_field(name="🗺️ Map", value=map_str, inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)

    # MOM
    if r["mom"]:
        embed.add_field(
            name="👑 Man of the Match",
            value=f"**{r['mom']['name']}** — {r['mom']['reason']}",
            inline=False,
        )

    # Team averages
    t = r["team_totals"]
    n = len(r["players"]) or 1
    if r["mode"] == "HP":
        embed.add_field(
            name="📊 Team Average",
            value=(
                f"Kills {t.get('kills',0)/n:.1f} · Deaths {t.get('deaths',0)/n:.1f} · "
                f"DMG {t.get('dmg',0)/n:.0f} · OBJ {t.get('obj',0)/n:.0f}s · "
                f"Score {t.get('score',0)/n:.0f}"
            ),
            inline=False,
        )
    else:
        embed.add_field(
            name="📊 Team Average",
            value=(
                f"Kills {t.get('kills',0)/n:.1f} · Deaths {t.get('deaths',0)/n:.1f} · "
                f"Assists {t.get('assists',0)/n:.1f} · First Kills {t.get('fk',0)/n:.1f}"
            ),
            inline=False,
        )

    # Player table
    if r["mode"] == "HP":
        text = "```\n"
        text += f"{'Player':<10}{'K':>4}{'D':>4}{'K/D':>6}{'DMG':>7}{'OBJ':>6}{'Score':>8}\n"
        text += "-" * 48 + "\n"
        for p in r["players"]:
            text += f"{p['name']:<10}{p['k']:>4}{p['d']:>4}{str(p['kd']):>6}{p['dmg']:>7}{p['obj']:>6}{p['score']:>8}\n"
        text += "```"
    else:
        text = "```\n"
        text += f"{'Player':<10}{'K':>4}{'D':>4}{'A':>4}{'K/D':>6}{'ADR':>6}{'FK':>4}\n"
        text += "-" * 42 + "\n"
        for p in r["players"]:
            text += f"{p['name']:<10}{p['k']:>4}{p['d']:>4}{p['a']:>4}{str(p['kd']):>6}{str(p['adr']):>6}{p['fk']:>4}\n"
        text += "```"
    embed.description = text

    # GPT insight
    if include_insight:
        insight = analytics_insights.match_insight(r, lang="en")
        if insight:
            embed.add_field(name="🧠 AI Insight", value=insight, inline=False)

    return embed


def build_weekly_report_embed(days: int = 7, include_insight: bool = True) -> discord.Embed | None:
    """Build a weekly report Embed."""
    w = analytics.weekly_report(days)
    if not w or not w["players"]:
        return None

    embed = discord.Embed(
        title=f"📅 {days}-Day Trend Report",
        color=0x3498DB,
        description=(
            f"Recent matches: **{w['matches_recent']}** / {w['matches_total']} total"
        ),
    )

    text = "```\n"
    text += f"{'Player':<10}{'Mode':<5}{'RecK/D':>7}{'OvrK/D':>7}{'Change':>8}\n"
    text += "-" * 40 + "\n"
    for p in w["players"][:15]:
        text += f"{p['name']:<10}{p['mode']:<5}{str(p['recent_kd']):>7}{str(p['overall_kd']):>7}{p['trend']}{p['delta_pct']:>+7}%\n"
    text += "```"
    embed.add_field(name="📈 K/D Change by Player", value=text, inline=False)

    if include_insight:
        insight = analytics_insights.weekly_insight(w, lang="en")
        if insight:
            embed.add_field(name="🧠 AI Insight", value=insight, inline=False)

    return embed


def build_trend_embed(name: str, recent_n: int = 10, include_insight: bool = True) -> discord.Embed | None:
    """Build a player trend Embed."""
    t = analytics.player_trend(name, recent_n)
    if not t:
        return None

    mode_name = "Hardpoint" if t["mode"] == "HP" else "Search & Destroy"
    d = t["delta"]
    kd_trend = "📈" if d["kd_pct"] > 3 else ("📉" if d["kd_pct"] < -3 else "➡️")
    embed = discord.Embed(
        title=f"📉 {t['name']} Form Analysis ({mode_name})",
        color=0xE74C3C,
        description=f"Last {t['recent_matches']} matches vs overall {t['total_matches']} matches average",
    )

    rec = t["recent"]
    ovr = t["overall"]
    if t["mode"] == "HP":
        text = "```\n"
        text += f"{'Metric':<8}{'Recent':>8}{'Overall':>8}{'Change':>8}\n"
        text += "-" * 34 + "\n"
        text += f"{'K/D':<8}{str(rec['kd']):>8}{str(ovr['kd']):>8}{d['kd_pct']:>+7}%\n"
        text += f"{'Kills':<8}{str(rec['k']):>8}{str(ovr['k']):>8}{d['k_pct']:>+7}%\n"
        text += f"{'Deaths':<8}{str(rec['d']):>8}{str(ovr['d']):>8}{d['d_pct']:>+7}%\n"
        text += f"{'DMG':<8}{str(rec.get('dmg',0)):>8}{str(ovr.get('dmg',0)):>8}\n"
        text += "```"
    else:
        text = "```\n"
        text += f"{'Metric':<8}{'Recent':>8}{'Overall':>8}{'Change':>8}\n"
        text += "-" * 34 + "\n"
        text += f"{'K/D':<8}{str(rec['kd']):>8}{str(ovr['kd']):>8}{d['kd_pct']:>+7}%\n"
        text += f"{'Kills':<8}{str(rec['k']):>8}{str(ovr['k']):>8}{d['k_pct']:>+7}%\n"
        text += f"{'Deaths':<8}{str(rec['d']):>8}{str(ovr['d']):>8}{d['d_pct']:>+7}%\n"
        text += f"{'ADR':<8}{str(rec.get('adr',0)):>8}{str(ovr.get('adr',0)):>8}\n"
        text += "```"
    embed.add_field(name=f"{kd_trend} Recent Form Comparison", value=text, inline=False)

    # Recent K/D flow
    flow = " · ".join(str(m["kd"]) for m in t["last_matches"][-8:])
    embed.add_field(name="📋 Recent K/D Flow", value=f"`{flow}`", inline=False)

    if include_insight:
        insight = analytics_insights.trend_insight(t, lang="en")
        if insight:
            embed.add_field(name="🧠 AI Insight", value=insight, inline=False)

    return embed
