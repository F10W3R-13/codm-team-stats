"""토너먼트 로컬 웹앱 — FastAPI.

실행: cd tournament && uvicorn app:app --port 8001 --reload
라우트: / (import), /standings, /players, /matches/{id}, /report
"""
import os
from pathlib import Path

from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import db
import standings as standings_mod
import awards
import import_pipeline


def _friendly_error(e: Exception) -> str:
    """GPT/시스템 에러를 사용자 친화적 한글 메시지로 변환.

    사용자가 영어 트레이스백이나 GPT 내부 에러를 보고 막히지 않도록.
    """
    msg = str(e)
    # GPT API 에러 (OpenAI 라이브러리)
    if "rate_limit" in msg.lower() or "rate limit" in msg.lower():
        return "GPT 호출 한도 초과. 잠시 후 다시 시도해주세요."
    if "timeout" in msg.lower() or "timed out" in msg.lower():
        return "GPT 응답 시간 초과. 다시 시도해보세요. (계속되면 스크린샷 화질을 확인해주세요.)"
    if "unsupported image" in msg.lower() or "image" in msg.lower() and "valid" in msg.lower():
        return "스크린샷 파일이 손상되었거나 지원하지 않는 형식입니다. 다른 파일로 다시 올려주세요."
    if "insufficient_quota" in msg.lower() or "billing" in msg.lower():
        return "GPT API 사용량이 초과되었습니다. 관리자에게 문의하세요."
    if "invalid_api_key" in msg.lower() or "authentication" in msg.lower():
        return "GPT API 키 오류. .env 파일의 OPENAI_API_KEY를 확인하세요."
    # JSON 파싱 실패 (GPT가 JSON 형식을 안 지킨 경우)
    if "json" in msg.lower() and ("decode" in msg.lower() or "parse" in msg.lower()):
        return "GPT 응답 파싱 실패. 다시 시도해보세요. (스크린샷이 너무 작거나 흐리면 발생할 수 있습니다.)"
    # 팀 식별 실패
    if "팀 식별" in msg:
        return msg  # 이미 한글
    # 그 외 — 원문을 그대로 보되 안내 추가
    return f"오류가 발생했습니다. 다시 시도해보세요.\n({msg[:150]})"

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="CODM Tournament Analyzer")

# 시작 시 스키마 초기화
db.init_db()


@app.get("/api/teams")
def api_teams():
    """팀 목록 (드롭다운용)."""
    return db.list_teams()


@app.get("/", response_class=HTMLResponse)
async def import_page(request: Request):
    """스크린샷 업로드 + 파싱 미리보기."""
    teams = db.list_teams()
    players_count = len(db.list_players())
    return templates.TemplateResponse(request, "import.html", {
        "teams_seeded": len(teams),
        "players_seeded": players_count,
    })


@app.post("/api/preview")
def api_preview(file1: UploadFile = File(...), file2: UploadFile = File(...)):
    """스크린샷 2장 → GPT 파싱 미리보기 (저장 전).

    동기 def로 선언 → FastAPI가 스레드풀에서 실행.
    GPT 비전 호출(10~60초 동기 블로킹)이 async 이벤트 루프를
    얼리지 않도록 async def 대신 일반 def를 쓴다.
    """
    try:
        img1 = file1.file.read()
        img2 = file2.file.read()
        result = import_pipeline.preview(img1, img2)
        # _raw 필드는 JSON 응답에서 제거
        result.pop("_raw_left", None)
        result.pop("_raw_right", None)
        return result
    except Exception as e:
        # 사용자 친화적 한글 에러 메시지로 변환 (영어 GPT 에러 차단)
        msg = _friendly_error(e)
        raise HTTPException(status_code=500, detail=msg)


@app.post("/api/confirm")
async def api_confirm(request: Request):
    """미리보기 확정 → 매치 저장.

    async def: 본문을 읽으려면 await request.json() 필요.
    import_pipeline.confirm은 DB 쓰기만 (GPT 호출 없음)이라 짧은 블로킹이라
    이벤트 루프에 영향 없음 — /api/preview와 달리 async 유지해도 OK.
    """
    body = await request.json()
    try:
        match_id = import_pipeline.confirm(body)
        return {"match_id": match_id, "ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=_friendly_error(e))


@app.post("/api/control")
async def api_control(request: Request):
    """Control 세트 점수 수동 입력 (스크린샷 없이 팀+점수만).

    스탠딩에 즉시 반영됨 (mode='CTL' 매치로 저장).
    같은 팀 대결에 이미 CTL이 있으면 덮어쓰기 (기존 CTL 매치 삭제 후 재입력).
    """
    body = await request.json()
    t1, t2 = body.get("team_a_id"), body.get("team_b_id")
    s1, s2 = body.get("team_a_score"), body.get("team_b_score")
    if not t1 or not t2 or s1 is None or s2 is None:
        raise HTTPException(status_code=400, detail="팀/점수 누락")
    try:
        conn = db.get_conn()
        try:
            a, b = min(t1, t2), max(t1, t2)
            # 같은 팀 대결의 기존 CTL 매치 삭제 (1팀대결 1CTL 원칙)
            conn.execute(
                """DELETE FROM matches WHERE mode='CTL'
                   AND ((team_a_id=? AND team_b_id=?) OR (team_a_id=? AND team_b_id=?))""",
                (a, b, b, a))
            # 새 CTL 매치 입력
            conn.execute(
                """INSERT INTO matches(mode, map_name, match_date, stage,
                       team_a_id, team_b_id, team_a_score, team_b_score)
                   VALUES('CTL', NULL, ?, 'round_robin', ?, ?, ?, ?)""",
                (body.get("match_date"), t1, t2, s1, s2))
            conn.commit()
        finally:
            conn.close()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=_friendly_error(e))


@app.get("/standings", response_class=HTMLResponse)
async def standings_page(request: Request):
    table = standings_mod.compute()
    duels = standings_mod.duel_details()
    final = standings_mod.final_match()
    return templates.TemplateResponse(request, "standings.html", {
        "request": request, "table": table, "duels": duels, "final": final,
    })


@app.get("/players", response_class=HTMLResponse)
async def players_page(request: Request):
    rankings = awards.player_rankings()
    hp = awards.hp_rankings()
    snd = awards.snd_rankings()
    return templates.TemplateResponse(request, "players.html", {
        "rankings": rankings, "hp": hp, "snd": snd,
    })


@app.get("/matches", response_class=HTMLResponse)
async def matches_list_page(request: Request):
    """매치 목록 (삭제 가능)."""
    matches = db.list_matches()
    return templates.TemplateResponse(request, "matches.html", {
        "request": request, "matches": matches,
    })


@app.post("/api/match/{match_id}/delete")
async def api_delete_match(match_id: int):
    """매치 삭제 (잘못 입력한 매치 정리용)."""
    try:
        db.delete_match(match_id)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=_friendly_error(e))


@app.post("/api/match/{match_id}/update")
async def api_update_match(match_id: int, request: Request):
    """매치 점수/팀/모드 수정 (잘못 입력된 점수 정정용)."""
    body = await request.json()
    try:
        db.update_match(match_id,
                        team_a_id=body.get("team_a_id"),
                        team_b_id=body.get("team_b_id"),
                        team_a_score=body.get("team_a_score"),
                        team_b_score=body.get("team_b_score"),
                        mode=body.get("mode"))
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=_friendly_error(e))


@app.get("/metrics", response_class=HTMLResponse)
async def metrics_page(request: Request):
    """ZCS/RDS 커스텀 지표 설명 페이지."""
    return templates.TemplateResponse(request, "metrics.html", {"request": request})


@app.get("/matches/{match_id}", response_class=HTMLResponse)
async def match_page(match_id: int, request: Request):
    conn = db.get_conn()
    try:
        match = conn.execute(
            """SELECT m.*, ta.name AS team_a_name, tb.name AS team_b_name
               FROM matches m
               JOIN teams ta ON ta.id = m.team_a_id
               JOIN teams tb ON tb.id = m.team_b_id
               WHERE m.id=?""", (match_id,)).fetchone()
        if not match:
            raise HTTPException(status_code=404, detail="Match not found")
        match = dict(match)
        table = "player_stats_hp" if match["mode"] == "HP" else "player_stats_snd"
        stats = [dict(r) for r in conn.execute(
            f"""SELECT s.*, p.name AS player_name FROM {table} s
                JOIN players p ON p.id = s.player_id
                WHERE s.match_id=? ORDER BY s.team_id, p.name""",
            (match_id,)).fetchall()]
    finally:
        conn.close()

    team_a = [s for s in stats if s["team_id"] == match["team_a_id"]]
    team_b = [s for s in stats if s["team_id"] == match["team_b_id"]]
    return templates.TemplateResponse(request, "match.html", {
        "match": match,
        "team_a": team_a, "team_b": team_b,
    })


@app.get("/report", response_class=HTMLResponse)
async def report_page(request: Request):
    table = standings_mod.compute()
    final = standings_mod.final_match()
    mvps = awards.mvps()
    rankings = awards.player_rankings()[:10]  # 상위 10
    return templates.TemplateResponse(request, "report.html", {
        "table": table, "final": final,
        "mvps": mvps, "rankings": rankings,
    })
