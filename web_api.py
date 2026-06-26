# 웹 대시보드 FastAPI 서버
#
# 실행:  uvicorn web_api:app --reload --port 8000
# 접속:  http://localhost:8000
#
# 화면:
#   /                개요 대시보드 (총 통계, 맵 분포 차트, 최근 매치)
#   /players         선수별 스탯 페이지 (평균 스탯 표 + 정렬)
#   /leaderboard     리더보드 (기준별 순위)
#   /matches         매치 히스토리 (페이지네이션)
#   /matches/{id}    매치 상세
#   /players/{name}  선수 상세 (K/D 트렌드 차트)
#
# 인증 없음 (로컬 전용).

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Query, HTTPException, Request, Body
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

load_dotenv()

import db
import queries
import analytics
import analytics_insights
import insight_cache
import i18n

db.init_db()

BASE_DIR = Path(__file__).parent
# Starlette 1.x 의 Jinja2Templates 캐시 키(unhashable dict) 버그를 피해
# 직접 Jinja2 Environment로 렌더링한다.
_env = Environment(
    loader=FileSystemLoader(str(BASE_DIR / "templates")),
    autoescape=select_autoescape(["html", "xml"]),
    cache_size=0,  # 캐시 비활성화
)


def render(template_name: str, lang: str = "ko", **context) -> str:
    """템플릿 렌더링 헬퍼. lang과 i18n 사전(t), languages를 자동 주입."""
    t = i18n.get(lang)
    tpl = _env.get_template(template_name)
    return tpl.render(lang=lang, t=t, languages=i18n.LANGUAGES, **context)


app = FastAPI(title="CODM Team Stats")


# ── 페이지 ────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, lang: str = Query("ko")):
    data = queries.overview_stats()
    return render("dashboard.html", lang=lang, data=data)


@app.get("/players", response_class=HTMLResponse)
async def players_page(
    request: Request,
    mode: str = Query("HP", pattern="^(HP|SND)$"),
    lang: str = Query("ko"),
):
    players = queries.all_players_overview(mode)
    return render("players.html", lang=lang, players=players, mode=mode)


@app.get("/players/{name}", response_class=HTMLResponse)
async def player_detail(request: Request, name: str, lang: str = Query("ko")):
    pid = queries.get_player_id(name)
    if not pid:
        raise HTTPException(404, "선수를 찾을 수 없습니다")
    stats = queries.player_overall_stats(pid)
    team_hp = queries.team_averages("HP") if stats["hp"] else {}
    trend_hp = queries.player_kd_trend(pid, "HP", 30) if stats["hp"] else []
    trend_snd = queries.player_kd_trend(pid, "SND", 30) if stats["snd"] else []
    # AI 인사이트 (캐싱 — 1시간 TTL, 매치 기록 시 무효화)
    cache_key = stats["name"] if stats["name"] else ""
    insight = insight_cache.get("player", cache_key, lang)
    if insight is None and (stats["hp"] or stats["snd"]):
        insight = analytics_insights.player_profile_insight(stats, team_hp, lang=lang)
        insight_cache.set("player", cache_key, lang, insight)
    return render(
        "player_detail.html", lang=lang,
        stats=stats, team_hp=team_hp,
        trend_hp=trend_hp, trend_snd=trend_snd,
        insight=insight,
    )


@app.get("/leaderboard", response_class=HTMLResponse)
async def leaderboard_page(
    request: Request,
    mode: str = Query("HP", pattern="^(HP|SND)$"),
    metric: str = Query("avg_kd"),
    lang: str = Query("ko"),
):
    custom_metrics = {"dpd", "dpk", "id", "ap_pct", "zcs"}
    if metric in custom_metrics:
        rows = queries.advanced_leaderboard(metric, 20)
    else:
        rows = queries.leaderboard(mode, metric, 20)
    return render(
        "leaderboard.html", lang=lang,
        rows=rows, mode=mode, metric=metric,
    )


@app.get("/matches", response_class=HTMLResponse)
async def matches_page(
    request: Request,
    mode: str = Query("ALL", pattern="^(ALL|HP|SND)$"),
    page: int = Query(1, ge=1),
    lang: str = Query("ko"),
):
    page_size = 20
    offset = (page - 1) * page_size
    mode_filter = None if mode == "ALL" else mode
    data = queries.match_history(page_size, offset, mode_filter)
    total_pages = max(1, (data["total"] + page_size - 1) // page_size)
    return render(
        "matches.html", lang=lang,
        data=data, mode=mode, page=page, total_pages=total_pages,
    )


@app.get("/matches/{match_id}", response_class=HTMLResponse)
async def match_detail(request: Request, match_id: int, lang: str = Query("ko")):
    report = analytics.match_report(match_id)
    if not report:
        raise HTTPException(404, "매치를 찾을 수 없습니다")
    return render("match_detail.html", lang=lang, report=report)


@app.get("/trends", response_class=HTMLResponse)
async def trends_page(
    request: Request,
    player: str = Query(None),
    mode: str = Query("HP", pattern="^(HP|SND)$"),
    metric: str = Query("kd"),
    lang: str = Query("ko"),
):
    players = queries.list_players()
    selected = player or (players[0] if players else None)
    series = []
    if selected:
        pid = queries.get_player_id(selected)
        if pid:
            series = queries.player_metric_timeseries(pid, mode, 50)
    return render(
        "trends.html", lang=lang,
        players=players, selected=selected, mode=mode,
        metric=metric, series=series,
    )


# ── JSON API (차트용) ────────────────────────────────────────────────────
@app.get("/api/overview")
async def api_overview():
    return queries.overview_stats()


@app.get("/api/player/{name}/trend")
async def api_player_trend(name: str, mode: str = "HP", limit: int = 30):
    pid = queries.get_player_id(name)
    if not pid:
        raise HTTPException(404, "선수 없음")
    return queries.player_kd_trend(pid, mode, limit)


@app.get("/api/player/{name}/timeseries")
async def api_player_timeseries(name: str, mode: str = "HP", limit: int = 50):
    """모든 지표 시계열 JSON (trends 차트용)."""
    pid = queries.get_player_id(name)
    if not pid:
        raise HTTPException(404, "선수 없음")
    return queries.player_metric_timeseries(pid, mode, limit)


# ── 팀 인사이트 페이지 ───────────────────────────────────────────────────
@app.get("/insights", response_class=HTMLResponse)
async def team_insights_page(
    request: Request,
    mode: str = Query("HP", pattern="^(HP|SND)$"),
    days: int = Query(30),
    lang: str = Query("ko"),
):
    data = analytics.team_insights_data(days=days, mode=mode)
    # AI 팀 인사이트 (캐싱 — mode+days+lang 키)
    cache_key = f"{mode}_{days}"
    insight = insight_cache.get("team", cache_key, lang)
    if insight is None and data.get("maps"):
        insight = analytics_insights.team_insight(data, lang=lang)
        insight_cache.set("team", cache_key, lang, insight)
    return render(
        "team_insights.html", lang=lang,
        data=data, mode=mode, days=days, insight=insight,
        selected_map_detail=True,
    )


# ── 관리(Admin) 페이지 ───────────────────────────────────────────────────
@app.get("/admin", response_class=HTMLResponse)
async def admin_page(
    request: Request,
    mode: str = Query("ALL", pattern="^(ALL|HP|SND)$"),
    page: int = Query(1, ge=1),
    has_result: str = Query("ALL", pattern="^(ALL|YES|NO)$"),
    lang: str = Query("ko"),
):
    page_size = 25
    offset = (page - 1) * page_size
    mode_filter = None if mode == "ALL" else mode
    hr = {"ALL": None, "YES": True, "NO": False}[has_result]
    data = queries.admin_match_list(page_size, offset, mode_filter, hr)
    total_pages = max(1, (data["total"] + page_size - 1) // page_size)
    return render(
        "admin.html", lang=lang,
        data=data, mode=mode, has_result=has_result,
        page=page, total_pages=total_pages,
    )


@app.get("/admin/match/{match_id}", response_class=HTMLResponse)
async def admin_match_edit(request: Request, match_id: int, lang: str = Query("ko")):
    match = queries.match_raw_stats(match_id)
    if not match:
        raise HTTPException(404, "매치 없음")
    return render("admin_match.html", lang=lang, match=match)


@app.post("/admin/match/{match_id}/meta")
async def admin_update_meta(match_id: int, payload: dict = Body(...)):
    ok = queries.update_match_meta(match_id, **payload)
    return {"ok": ok}


@app.post("/admin/stat/{stat_id}")
async def admin_update_stat(stat_id: int, mode: str = Query(...), payload: dict = Body(...)):
    ok = queries.update_player_stat(stat_id, mode, **payload)
    return {"ok": ok}


@app.delete("/admin/match/{match_id}")
async def admin_delete_match(match_id: int):
    ok = queries.delete_match(match_id)
    return {"ok": ok}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web_api:app", host="0.0.0.0", port=8000, reload=True)
