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
import asyncio
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Query, HTTPException, Request, Body, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

load_dotenv()

import db
import queries
import admin_write
import analytics
import analytics_insights
import coaching_brain_loader
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


def _heat_class(pct: float) -> str:
    """맵 히트맵 색 등급 (±% 기준). HP/SND 공용.

    5단계: 강함(heat-2/heat-1), 평균(heat-0), 약함(heat--1/heat--2).
    절대 임계값이 아닌 맵 간 상대 차이 표현.
    """
    if pct >= 15:
        return "heat-2"
    if pct >= 5:
        return "heat-1"
    if pct <= -15:
        return "heat--2"
    if pct <= -5:
        return "heat--1"
    return "heat-0"


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
async def coaching_hub_page(request: Request, lang: str = Query("ko"),
                            recent: str = Query("10")):
    # recent: "5" | "10" | "season" — 이외값은 10으로 폴백
    if recent == "season":
        n = None
    elif recent in ("5", "10"):
        n = int(recent)
    else:
        n = 10
    data = analytics.coaching_hub(recent_matches=n)
    # 코칭 노트 (관리자 전용 위젯)
    cookie_val = request.cookies.get(auth.COOKIE_NAME)
    is_admin = bool(cookie_val and auth.check_cookie(cookie_val))
    data["open_notes"] = queries.open_notes() if is_admin else []
    data["players_list"] = [
        {"id": p["id"], "name": p["name"]}
        for p in queries.all_players_overview("HP")
    ] if is_admin else []
    return render("coaching_hub.html", lang=lang, data=data, is_admin=is_admin)


@app.get("/players", response_class=HTMLResponse)
async def players_page(
    request: Request,
    mode: str = Query("HP", pattern="^(HP|SND)$"),
    lang: str = Query("ko"),
):
    players = queries.all_players_overview(mode)
    # HP 모드: 역할 스펙트럼 데이터(slay/obj_score + 위치) 추가 — 허브와 동일 출처.
    if mode == "HP" and players:
        import metrics
        roles = {r["name"]: r for r in queries.team_role_distribution()}
        for p in players:
            r = roles.get(p["name"])
            if r:
                p["role"] = r["role"]
                p["slay_score"] = r["slay_score"]
                p["obj_score"] = r["obj_score"]
                p["spectrum_pos"] = metrics.role_spectrum_pos(r["slay_score"], r["obj_score"])
    return render("players.html", lang=lang, players=players, mode=mode)


@app.get("/players/{name}", response_class=HTMLResponse)
async def player_detail(request: Request, name: str, lang: str = Query("ko")):
    pid = queries.get_player_id(name)
    if not pid:
        raise HTTPException(404, "선수를 찾을 수 없습니다")
    stats = queries.player_overall_stats(pid)
    team_hp = queries.team_averages("HP") if stats["hp"] else {}
    # key 비대칭 정규화: team_averages(all_players_overview)는 avg_ck를 쓰지만
    # player_overall_stats는 avg_capture를 씀. 통합 패널 루프를 위해 별칭 추가.
    if team_hp:
        if "avg_capture" not in team_hp and "avg_ck" in team_hp:
            team_hp["avg_capture"] = team_hp["avg_ck"]
    # 역할 스펙트럼 (HP 전용) — 허브와 동일 출처(team_role_distribution).
    if stats["hp"]:
        import metrics
        roles = {r["name"]: r for r in queries.team_role_distribution()}
        r = roles.get(stats["name"])
        if r:
            stats["hp"]["role"] = r["role"]
            stats["hp"]["slay_score"] = r["slay_score"]
            stats["hp"]["obj_score"] = r["obj_score"]
            stats["hp"]["spectrum_pos"] = metrics.role_spectrum_pos(r["slay_score"], r["obj_score"])
    # 맵별 성적 — HP(ZCS)/SND(RDS) 본인 평균 대비 강은/약한 맵
    player_maps = queries.player_map_breakdown(pid, mode="HP", min_matches=5) if stats["hp"] else []
    player_maps_snd = queries.player_map_breakdown(pid, mode="SND", min_matches=2) if stats["snd"] else []
    # 히트맵 색 클래스 — metric_pct 크기에 비례한 5단계 (HP/SND 공용)
    for m in player_maps:
        m["heat_class"] = _heat_class(m["metric_pct"])
    for m in player_maps_snd:
        m["heat_class"] = _heat_class(m["metric_pct"])
    # AI 인사이트 — 캐시 hit 시에만 즉시 렌더. miss면 None (프런트가 fetch로 비동기 로드).
    cache_key = stats["name"] if stats["name"] else ""
    insight = insight_cache.get("player", cache_key, lang,
                                fingerprint=coaching_brain_loader.fingerprint())
    return render(
        "player_detail.html", lang=lang,
        stats=stats, team_hp=team_hp,
        insight=insight, player_maps=player_maps, player_maps_snd=player_maps_snd,
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
    custom_metrics = {"dpd", "dpk", "impact_delta", "ap_pct", "zcs", "rds"}
    if metric in custom_metrics:
        rows = queries.advanced_leaderboard(metric, 20)
    else:
        rows = queries.leaderboard(mode, metric, 20)
    # 팀 평균 (±% 계산용) + 지표 방향 (DPK만 낮을수록 좋음)
    team_avg = queries.team_averages(mode) if mode == "HP" else queries.team_averages(mode)
    avg_value = team_avg.get(metric) if team_avg else None
    higher_better = metric != "dpk"
    return render(
        "leaderboard.html", lang=lang,
        rows=rows, mode=mode, metric=metric,
        avg_value=avg_value, higher_better=higher_better,
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
    day_notes = admin_write.get_day_notes(report.get("match_date")) or {}
    # 코칭 노트 (관리자: 해당 매치 관련 이력)
    match_notes = queries.notes_for_match(match_id) if is_admin else []
    # 노트 선수 태그용 — 이 매치 선수들의 (id, name)
    match_players = []
    if is_admin:
        for p in report.get("players", []):
            pid = queries.get_player_id(p["name"])
            if pid:
                match_players.append({"id": pid, "name": p["name"]})
    # GPT 매치 인사이트 — 캐시 hit 시에만 즉시 렌더. miss면 None (프런트 fetch).
    insight = insight_cache.get("match", str(match_id), lang,
                                fingerprint=coaching_brain_loader.fingerprint())
    return render("match_detail.html", lang=lang, report=report, insight=insight,
                  is_admin=is_admin, day_notes=day_notes, match_notes=match_notes,
                  match_players=match_players)


# ── JSON API (차트용) ────────────────────────────────────────────────────
@app.get("/api/player/{name}/timeseries")
async def api_player_timeseries(name: str, mode: str = "HP", limit: int = 50):
    """모든 지표 시계열 JSON (trends 차트용)."""
    pid = queries.get_player_id(name)
    if not pid:
        raise HTTPException(404, "선수 없음")
    return queries.player_metric_timeseries(pid, mode, limit)


# ── 인사이트 비동기 API (페이지는 즉시 렌더, 인사이트는 fetch로 로드) ───────
# 캐시 hit 시 즉시 반환. miss면 run_in_executor로 GPT 호출 (이벤트 루프 블록 방지).
@app.get("/api/insight/player/{name}")
async def api_player_insight(name: str, lang: str = "ko"):
    cache_key = name
    fp = coaching_brain_loader.fingerprint()
    cached = insight_cache.get("player", cache_key, lang, fingerprint=fp)
    if cached is not None:
        return {"insight": cached, "cached": True}
    pid = queries.get_player_id(name)
    if not pid:
        raise HTTPException(404, "선수 없음")
    stats = queries.player_overall_stats(pid)
    if not (stats.get("hp") or stats.get("snd")):
        return {"insight": "", "cached": False}
    team_hp = queries.team_averages("HP") if stats["hp"] else {}
    if team_hp:
        if "avg_capture" not in team_hp and "avg_ck" in team_hp:
            team_hp["avg_capture"] = team_hp["avg_ck"]
    loop = asyncio.get_running_loop()
    insight = await loop.run_in_executor(
        None, lambda: analytics_insights.player_profile_insight(stats, team_hp, lang=lang))
    if insight:
        insight_cache.set("player", cache_key, lang, insight, fingerprint=fp)
    return {"insight": insight, "cached": False}


@app.get("/api/insight/match/{match_id}")
async def api_match_insight(match_id: int, lang: str = "ko"):
    fp = coaching_brain_loader.fingerprint()
    cached = insight_cache.get("match", str(match_id), lang, fingerprint=fp)
    if cached is not None:
        return {"insight": cached, "cached": True}
    report = analytics.match_report(match_id)
    if not report:
        raise HTTPException(404, "매치 없음")
    loop = asyncio.get_running_loop()
    insight = await loop.run_in_executor(
        None, lambda: analytics_insights.match_insight(report, lang=lang))
    if insight:
        insight_cache.set("match", str(match_id), lang, insight, fingerprint=fp)
    return {"insight": insight, "cached": False}


@app.get("/api/insight/map/{map_name}")
async def api_map_insight(map_name: str, mode: str = "HP", lang: str = "ko"):
    cache_key = f"{map_name}_{mode}"
    fp = coaching_brain_loader.fingerprint()
    cached = insight_cache.get("map", cache_key, lang, fingerprint=fp)
    if cached is not None:
        return {"insight": cached, "cached": True}
    data = analytics.map_detail(map_name, mode)
    if not data:
        raise HTTPException(404, "맵 데이터 없음")
    loop = asyncio.get_running_loop()
    advice = await loop.run_in_executor(
        None, lambda: analytics_insights.map_advice(data, lang=lang))
    if advice:
        insight_cache.set("map", cache_key, lang, advice, fingerprint=fp)
    return {"insight": advice, "cached": False}


@app.get("/api/insight/briefing")
async def api_briefing(recent: str = Query("10")):
    """코칭 허브 프리매치 브리핑 (코치 전용, ko 고정).

    버튼 클릭 시 호출. 캐시 키: ("briefing", recent, "ko").
    """
    if recent not in ("5", "10", "season"):
        recent = "10"
    fp = coaching_brain_loader.fingerprint()
    cached = insight_cache.get("briefing", recent, "ko", fingerprint=fp)
    if cached is not None:
        return {"insight": cached, "cached": True}
    n = None if recent == "season" else int(recent)
    try:
        hub_data = analytics.coaching_hub(recent_matches=n)
        hub_data["open_notes"] = queries.open_notes()
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"insight": "", "error": f"data: {e}"}
    loop = asyncio.get_running_loop()
    insight = await loop.run_in_executor(
        None, lambda: analytics_insights.briefing_insight(hub_data, lang="ko"))
    if insight:
        insight_cache.set("briefing", recent, "ko", insight, fingerprint=fp)
    return {"insight": insight, "cached": False}


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
    # AI 간접 제언 — 캐시 hit 시에만 즉시 렌더. miss면 None (프런트 fetch).
    cache_key = f"{map_name}_{mode}"
    advice = insight_cache.get("map", cache_key, lang,
                               fingerprint=coaching_brain_loader.fingerprint())
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
    data = admin_write.admin_match_list(page_size, offset, mode_filter, hr)
    total_pages = max(1, (data["total"] + page_size - 1) // page_size)
    return render(
        "admin.html", lang=lang,
        data=data, mode=mode, has_result=has_result,
        page=page, total_pages=total_pages,
    )


@app.get("/admin/match/{match_id}", response_class=HTMLResponse)
async def admin_match_edit(request: Request, match_id: int, lang: str = Query("ko")):
    match = admin_write.match_raw_stats(match_id)
    if not match:
        raise HTTPException(404, "매치 없음")
    players = admin_write.list_players_with_ids()  # 선수 재매핑 드롭다운용
    return render("admin_match.html", lang=lang, match=match, players=players)


@app.post("/admin/match/{match_id}/meta")
async def admin_update_meta(match_id: int, payload: dict = Body(...)):
    ok = admin_write.update_match_meta(match_id, **payload)
    return {"ok": ok}


@app.post("/admin/stat/{stat_id}")
async def admin_update_stat(stat_id: int, mode: str = Query(...), payload: dict = Body(...)):
    ok = admin_write.update_player_stat(stat_id, mode, **payload)
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
    ok = admin_write.add_player_to_match(match_id, mode, player_id, **payload)
    return {"ok": ok}


# ── 날짜 단위 복기 편집 (VOD/코치메모/전사) ───────────────────────────────
@app.get("/admin/day/{match_date}", response_class=HTMLResponse)
async def admin_day_edit(request: Request, match_date: str, lang: str = Query("ko")):
    day_notes = admin_write.get_day_notes(match_date) or {}
    matches = admin_write.matches_by_date(match_date)
    return render("admin_day.html", lang=lang,
                  match_date=match_date, day_notes=day_notes, matches=matches)


@app.post("/admin/day/{match_date}/meta")
async def admin_update_day_meta(match_date: str, payload: dict = Body(...)):
    ok = admin_write.update_day_meta(match_date, **payload)
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
    matches = admin_write.matches_by_date(match_date)
    if not matches:
        return {"ok": False, "error": "no_matches_on_date"}
    report = analytics.match_report(matches[0]["id"])
    if not report:
        return {"ok": False, "error": "report_failed"}

    summary = await asyncio.get_running_loop().run_in_executor(
        None, lambda: analytics_insights.summarize_transcript(report, text, lang=lang))
    if not summary:
        return {"ok": False, "error": "summary_failed"}

    admin_write.update_day_meta(match_date, transcript_summary=summary)
    return {"ok": True, "summary": summary}


@app.delete("/admin/match/{match_id}")
async def admin_delete_match(match_id: int):
    ok = admin_write.delete_match(match_id)
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


# ── 선수 관리 (삭제/병합) ────────────────────────────────────────────────
@app.get("/admin/players", response_class=HTMLResponse)
async def admin_players_page(request: Request, lang: str = Query("ko")):
    """선수 관리 페이지 — 선수 삭제/병합. 배포 DB 정리(Swish 삭제 등)용."""
    players = admin_write.list_players_admin()
    return render("admin_players.html", lang=lang, players=players)


@app.delete("/admin/player/{player_id}")
async def admin_delete_player(player_id: int):
    ok = admin_write.delete_player(player_id)
    return {"ok": ok}


@app.post("/admin/player/merge")
async def admin_merge_player(payload: dict = Body(...)):
    """선수 병합 — src 선수의 스탯/alias를 dst 선수로 이관 후 src 삭제.
    {src_id, dst_player}. db.merge_player 재사용.
    """
    src_id = payload.get("src_id")
    dst_player = (payload.get("dst_player") or "").strip()
    if not src_id or not dst_player:
        return {"ok": False, "message": "src_id 와 dst_player 가 필요합니다"}
    result = db.merge_player(int(src_id), dst_player)
    return result


# ── 코칭 노트 (액션 아이템) ──────────────────────────────────────────────────
@app.post("/admin/notes")
async def admin_add_note(request: Request,
                         content: str = Form(...),
                         match_id: str = Form(""),
                         player_id: str = Form("")):
    """노트 추가 (폼 제출). 매치 상세/허브에서 POST → referer로 되돌아감."""
    mid = int(match_id) if match_id else None
    pid = int(player_id) if player_id else None
    admin_write.add_note(content, match_id=mid, player_id=pid)
    insight_cache.invalidate("briefing")  # 노트가 브리핑 컨텍스트 → 무효화
    return RedirectResponse(url=request.headers.get("referer", "/"), status_code=303)


@app.post("/admin/notes/{note_id}/toggle")
async def admin_toggle_note(note_id: int, request: Request):
    """노트 상태 토글 — open→done, done→open."""
    status = admin_write.get_note_status(note_id)
    if status == "open":
        admin_write.resolve_note(note_id)
    elif status == "done":
        admin_write.reopen_note(note_id)
    insight_cache.invalidate("briefing")  # 노트가 브리핑 컨텍스트 → 무효화
    return RedirectResponse(url=request.headers.get("referer", "/"), status_code=303)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web_api:app", host="0.0.0.0", port=8000, reload=True)
