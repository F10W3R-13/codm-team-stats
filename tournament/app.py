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

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="CODM Tournament Analyzer")

# 시작 시 스키마 초기화
db.init_db()


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
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/standings", response_class=HTMLResponse)
async def standings_page(request: Request):
    table = standings_mod.compute()
    final = standings_mod.final_match()
    return templates.TemplateResponse(request, "standings.html", {
        "table": table, "final": final,
    })


@app.get("/players", response_class=HTMLResponse)
async def players_page(request: Request):
    rankings = awards.player_rankings()
    return templates.TemplateResponse(request, "players.html", {
        "rankings": rankings,
    })


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
