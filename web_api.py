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
from fastapi import FastAPI, Query, HTTPException, Request, Body, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

load_dotenv()

import db
import queries
import analytics
import analytics_insights
import insight_cache
import i18n
import auth
import config

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


@app.middleware("http")
async def admin_auth_middleware(request: Request, call_next):
    """미들웨어: /admin/* (단, /admin/login 제외) 접근 시 인증 쿠키 검증.

    - HTML 페이지(GET, Accept: text/html): 미인증 시 /admin/login 로 303 리다이렉트
    - JSON API(POST/DELETE 또는 XHR): 미인증 시 401 JSON
    /admin/login 자체는 통과시킨다.
    """
    path = request.url.path
    if path.startswith("/admin") and path != "/admin/login":
        cookie_val = request.cookies.get(auth.COOKIE_NAME)
        if not (cookie_val and auth.check_cookie(cookie_val)):
            accept = request.headers.get("accept", "")
            is_html = "text/html" in accept or request.method == "GET"
            if is_html and "application/json" not in accept:
                return RedirectResponse(url="/admin/login", status_code=303)
            return JSONResponse({"ok": False, "detail": "admin login required"}, status_code=401)
    return await call_next(request)


# ── 페이지 ────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def coaching_hub_page(request: Request, lang: str = Query("ko")):
    data = analytics.coaching_hub()
    return render("coaching_hub.html", lang=lang, data=data)


@app.get("/overview", response_class=HTMLResponse)
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
    # key 비대칭 정규화: team_averages(all_players_overview)는 avg_ck/id를 쓰지만
    # player_overall_stats는 avg_capture/impact_delta를 씀. 통합 패널 루프를 위해 별칭 추가.
    if team_hp:
        if "avg_capture" not in team_hp and "avg_ck" in team_hp:
            team_hp["avg_capture"] = team_hp["avg_ck"]
        if "impact_delta" not in team_hp and "id" in team_hp:
            team_hp["impact_delta"] = team_hp["id"]
    # 역할 분류 (HP 전용) — player_overall_stats엔 team 컨텍스트가 없어 여기서 추가
    if stats["hp"] and team_hp:
        import metrics
        stats["hp"]["role"] = metrics.classify_role(stats["hp"], team_hp)
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
        insight=insight,
    )


# ── 팀 인사이트 페이지 ───────────────────────────────────────────────────
@app.get("/compare", response_class=HTMLResponse)
async def compare_page(
    request: Request,
    a: str = Query(None),
    b: str = Query(None),
    mode: str = Query("HP", pattern="^(HP|SND)$"),
    lang: str = Query("ko"),
):
    players = queries.list_players()
    data = None
    if a and b and a != b:
        data = queries.compare_players(a, b, mode)
    return render(
        "compare.html", lang=lang,
        players=players, a=a, b=b, mode=mode, data=data,
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
    mode_filter = None if mode == "ALL" else mode
    # 날짜 그룹 페이지네이션 — 한 페이지 = 최근 7일치 매치
    data = queries.match_history_grouped(mode_filter, date_page=page, dates_per_page=7)
    # 코치 로그인 여부 → 날짜 헤더 '복기 편집' 링크 노출
    cookie_val = request.cookies.get(auth.COOKIE_NAME)
    is_admin = bool(cookie_val and auth.check_cookie(cookie_val))
    return render(
        "matches.html", lang=lang,
        data=data, mode=mode, page=data["date_page"], total_pages=data["total_date_pages"],
        is_admin=is_admin,
    )


@app.get("/matches/{match_id}", response_class=HTMLResponse)
async def match_detail(request: Request, match_id: int, lang: str = Query("ko")):
    report = analytics.match_report(match_id)
    if not report:
        raise HTTPException(404, "매치를 찾을 수 없습니다")
    # 코치 로그인 여부 → '편집' 링크 노출 (VOD/메모/전사 패널 진입)
    cookie_val = request.cookies.get(auth.COOKIE_NAME)
    is_admin = bool(cookie_val and auth.check_cookie(cookie_val))
    # 날짜 단위 복기 데이터 (VOD/메모/전사는 날짜 단위)
    day_notes = queries.get_day_notes(report.get("match_date")) or {}
    # GPT 매치 인사이트 (캐싱 — 1시간 TTL, 매치 기록 시 무효화)
    insight = insight_cache.get("match", str(match_id), lang)
    if insight is None:
        insight = analytics_insights.match_insight(report, lang=lang)
        insight_cache.set("match", str(match_id), lang, insight)
    return render("match_detail.html", lang=lang, report=report, insight=insight,
                  is_admin=is_admin, day_notes=day_notes)


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


# ── 맵 페이지 ─────────────────────────────────────────────────────────────
@app.get("/maps", response_class=HTMLResponse)
async def maps_page(
    request: Request,
    mode: str = Query("HP", pattern="^(HP|SND)$"),
    lang: str = Query("ko"),
):
    maps = queries.map_team_stats(mode, min_matches=2)
    return render("maps.html", lang=lang, maps=maps, mode=mode)


@app.get("/maps/{map_name}", response_class=HTMLResponse)
async def map_detail_page(
    request: Request,
    map_name: str,
    mode: str = Query("HP", pattern="^(HP|SND)$"),
    lang: str = Query("ko"),
):
    data = analytics.map_detail(map_name, mode)
    if not data:
        raise HTTPException(404, "맵 데이터를 찾을 수 없습니다")
    # AI 간접 제언 (캐싱 — map+mode+lang 키)
    cache_key = f"{map_name}_{mode}"
    advice = insight_cache.get("map", cache_key, lang)
    if advice is None:
        advice = analytics_insights.map_advice(data, lang=lang)
        insight_cache.set("map", cache_key, lang, advice)
    return render("map_detail.html", lang=lang, data=data, advice=advice)


# ── 관리(Admin) 페이지 ───────────────────────────────────────────────────
@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request, lang: str = Query("ko"), error: str = Query("")):
    """관리자 로그인 페이지. 이미 인증된 경우 /admin 로 리다이렉트."""
    cookie_val = request.cookies.get(auth.COOKIE_NAME)
    if cookie_val and auth.check_cookie(cookie_val):
        return RedirectResponse(url="/admin", status_code=303)
    return render("admin_login.html", lang=lang, error=error)


@app.post("/admin/login")
async def admin_login_submit(payload: dict = Body(...)):
    """비번 검증 → 쿠키 발급. 맞으면 /admin 로."""
    password = (payload.get("password") or "").strip()
    if auth.verify_password(password):
        name, value = auth.make_cookie()
        resp = JSONResponse({"ok": True, "redirect": "/admin"})
        resp.set_cookie(
            name, value,
            max_age=config.ADMIN_COOKIE_MAX_AGE,
            httponly=True, samesite="lax",
            secure=False,  # Railway는 HTTPS termination 이라 서버는 HTTP; 브라우저엔 HTTPS로 옴
        )
        return resp
    return JSONResponse({"ok": False, "message": "비밀번호가 틀렸습니다"}, status_code=401)


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
    players = queries.list_players_with_ids()  # 선수 재매핑 드롭다운용
    return render("admin_match.html", lang=lang, match=match, players=players)


@app.post("/admin/match/{match_id}/meta")
async def admin_update_meta(match_id: int, payload: dict = Body(...)):
    ok = queries.update_match_meta(match_id, **payload)
    return {"ok": ok}


@app.post("/admin/stat/{stat_id}")
async def admin_update_stat(stat_id: int, mode: str = Query(...), payload: dict = Body(...)):
    ok = queries.update_player_stat(stat_id, mode, **payload)
    return {"ok": ok}


@app.post("/admin/match/{match_id}/player")
async def admin_add_player(match_id: int, mode: str = Query(...), payload: dict = Body(...)):
    """기존 매치에 누락된 선수 한 명을 추가 (AI가 4명만 읽은 경우 보정)."""
    payload = payload or {}
    player_id = payload.pop("player_id", None)
    if player_id in (None, ""):
        return {"ok": False, "error": "player_id required"}
    try:
        player_id = int(player_id)
    except (ValueError, TypeError):
        return {"ok": False, "error": "invalid player_id"}
    ok = queries.add_player_to_match(match_id, mode, player_id, **payload)
    return {"ok": ok}


# ── 날짜 단위 복기 편집 (VOD/코치메모/전사) ───────────────────────────────
@app.get("/admin/day/{match_date}", response_class=HTMLResponse)
async def admin_day_edit(request: Request, match_date: str, lang: str = Query("ko")):
    day_notes = queries.get_day_notes(match_date) or {}
    matches = queries.matches_by_date(match_date)
    return render("admin_day.html", lang=lang,
                  match_date=match_date, day_notes=day_notes, matches=matches)


@app.post("/admin/day/{match_date}/meta")
async def admin_update_day_meta(match_date: str, payload: dict = Body(...)):
    ok = queries.update_day_meta(match_date, **payload)
    return {"ok": ok}


@app.post("/admin/day/{match_date}/transcript")
async def admin_upload_day_transcript(match_date: str, lang: str = Query("ko"),
                                      file: UploadFile = File(...)):
    """전사 파일(.txt/.md) 업로드 → AI 요약 생성 → 날짜 단위 저장. 원본은 저장 안 함."""
    content = await file.read()
    if len(content) > 1_500_000:  # 1.5MB 상한
        return {"ok": False, "error": "file_too_large"}
    try:
        text = content.decode("utf-8", errors="ignore")
    except Exception:
        return {"ok": False, "error": "decode_failed"}
    if not text.strip():
        return {"ok": False, "error": "empty"}

    # 그 날짜의 대표 매치(첫 매치) 수치를 전사 요약 컨텍스트로 사용
    matches = queries.matches_by_date(match_date)
    if not matches:
        return {"ok": False, "error": "no_matches_on_date"}
    report = analytics.match_report(matches[0]["id"])
    if not report:
        return {"ok": False, "error": "report_failed"}

    summary = analytics_insights.summarize_transcript(report, text, lang=lang)
    if not summary:
        return {"ok": False, "error": "summary_failed"}

    queries.update_day_meta(match_date, transcript_summary=summary)
    return {"ok": True, "summary": summary}


@app.delete("/admin/match/{match_id}")
async def admin_delete_match(match_id: int):
    ok = queries.delete_match(match_id)
    return {"ok": ok}


# ── Alias 관리 ──────────────────────────────────────────────────────────
@app.get("/admin/aliases", response_class=HTMLResponse)
async def admin_aliases_page(
    request: Request,
    source: str = Query("ALL", pattern="^(ALL|Manual|OCR Auto)$"),
    player: str = Query(""),
    lang: str = Query("ko"),
):
    """Alias(IGN 변형) 관리 페이지. 자가학습(OCR Auto) alias 점검/정리용."""
    source_filter = None if source == "ALL" else source
    player_filter = player.strip() or None
    aliases = db.list_aliases(player_name=player_filter, source=source_filter)
    players = queries.list_players()
    counts = {"Manual": 0, "OCR Auto": 0}
    for a in db.list_aliases():
        counts[a.get("source", "Manual")] = counts.get(a.get("source", "Manual"), 0) + 1
    return render(
        "admin_aliases.html", lang=lang,
        aliases=aliases, players=players,
        source=source, player=player,
        counts=counts, total=sum(counts.values()),
    )


@app.post("/admin/alias")
async def admin_add_alias(payload: dict = Body(...)):
    ign = (payload.get("ign") or "").strip()
    player = (payload.get("player") or "").strip()
    result = db.add_alias(ign, player)
    return result


@app.delete("/admin/alias")
async def admin_delete_alias(ign: str = Query(...)):
    result = db.remove_alias(ign)
    return result


# ── 미매칭(게스트/OCR 실패) 닉네임 관리 ──────────────────────────────
@app.get("/admin/unmatched", response_class=HTMLResponse)
async def admin_unmatched_page(request: Request, lang: str = Query("ko")):
    """GPT 가 정규화하지 못해 players 에 신규 생성된 IGN(게스트/OCR실패) 모아보기."""
    unmatched = db.list_unmatched_players()
    roster = list(db.ROSTER_NAMES)
    return render("admin_unmatched.html", lang=lang, unmatched=unmatched, roster=roster)


@app.post("/admin/unmatched/merge")
async def admin_merge_unmatched(payload: dict = Body(...)):
    """게스트 player 를 정식 선수로 병합. {src_id, dst_player}."""
    src_id = payload.get("src_id")
    dst_player = (payload.get("dst_player") or "").strip()
    if not src_id or not dst_player:
        return {"ok": False, "message": "src_id 와 dst_player 가 필요합니다"}
    result = db.merge_player(int(src_id), dst_player)
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web_api:app", host="0.0.0.0", port=8000, reload=True)
