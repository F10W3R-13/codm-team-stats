# 웹 AI 인사이트(선수·매치·맵·브리핑) 모델 실측 비교
#
# 운영 인사이트 함수를 그대로 실행하되 OpenAI 클라이언트를 가짜로 바꿔 실제 프롬프트를 가로챈 뒤,
# 후보 모델에 재생한다. 운영 모델(Luna)은 운영 프롬프트 그대로, 다른 계열은 같은 재료(지시문·규칙·
# 지표 정의·기준선·코칭 브레인)를 그 모델 문법에 맞게 재배치해 공정하게 비교한다.
#   - prod      : 운영 system 프롬프트 그대로 (참고 자료 → Task → Output Rules)
#   - anthropic : 참고 자료를 XML 태그로 system에, 데이터·지시·규칙은 user 끝에
#   - glm       : 번호 매긴 HARD RULES를 맨 위에 + 답하기 전 자체 점검 지시
# 객관 채점(길이·마크다운·추적 불가 숫자·승패 단정·과장어)과 본문을 bench_out/에 남긴다.
#
# 2026-10 결과: 프롬프트를 맞추면 세 모델 품질이 비슷 → 가성비로 Luna low 유지.
#   Haiku medium은 해석이 가장 깊지만 ~1.7배 비용·~2배 지연, GLM은 15s 타임아웃 근접·과장어.
#
# 실행 (배포 DB 기준, 프로젝트 루트에서):
#   railway run --service Postgres python scripts/insight_model_bench.py            # 키 있는 설정 전부
#   railway run --service Postgres python scripts/insight_model_bench.py --only luna
#
# 키: OPENAI_API_KEY / ANTHROPIC_API_KEY(+ pip install anthropic) / OPENAI_API_KEY_ZAI — 없으면 건너뜀.

import argparse
import datetime
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)  # 코칭 브레인 상대경로 기준
# railway run --service Postgres 의 DATABASE_URL은 프라이빗 호스트 → 로컬에선 공개 URL로 접속
if os.environ.get("DATABASE_PUBLIC_URL"):
    os.environ["DATABASE_URL"] = os.environ["DATABASE_PUBLIC_URL"]

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))

import analytics  # noqa: E402
import analytics_insights  # noqa: E402
import coaching_brain_loader  # noqa: E402
import db  # noqa: E402
import prompt_context  # noqa: E402
import queries  # noqa: E402

SEASON = db.CURRENT_SEASON
PROD_TIMEOUT = 15.0  # analytics_insights._client() 타임아웃

# $/1M 토큰: (입력, 캐시 입력, 출력). Haiku는 입력 100k 초과 시 5배.
PRICES = {
    "luna": (0.10, 0.01, 0.50),
    "haiku": (0.10, 0.01, 0.50),
    "haiku_long": (0.50, 0.05, 2.50),
    "glm": (0.15, 0.03, 0.50),
}

# 출력 한도는 넉넉히 (길이는 프롬프트가 통제) — 잘림이 비교를 왜곡하지 않게
CONFIGS = [
    {"name": "luna-low", "vendor": "openai", "model": "gpt-6-luna", "effort": "low", "style": "prod", "max_out": 4000},
    {"name": "luna-medium", "vendor": "openai", "model": "gpt-6-luna", "effort": "medium", "style": "prod", "max_out": 4000},
    {"name": "haiku-low", "vendor": "anthropic", "model": "claude-haiku-5-5", "effort": "low", "style": "anthropic", "max_out": 8000},
    {"name": "haiku-medium", "vendor": "anthropic", "model": "claude-haiku-5-5", "effort": "medium", "style": "anthropic", "max_out": 8000},
    # GLM thinking은 끌 수 없음(400) → reasoning_effort로 깊이만 조절
    {"name": "glm-low", "vendor": "zai", "model": "glm-5.3-flash", "effort": "low", "style": "glm", "max_out": 8000},
]


# ── 모델 호출 ────────────────────────────────────────────────────────────

def call_openai_compat(cfg, system, user):
    from openai import OpenAI
    if cfg["vendor"] == "zai":
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY_ZAI"],
                        base_url="https://api.z.ai/api/paas/v4/", timeout=600.0, max_retries=0)
        extra = {"max_tokens": cfg["max_out"], "reasoning_effort": cfg["effort"]}
    else:
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=180.0, max_retries=0)
        extra = {"max_completion_tokens": cfg["max_out"], "reasoning_effort": cfg["effort"]}
    r = client.chat.completions.create(
        model=cfg["model"],
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        **extra,
    )
    u = r.usage
    ptd = getattr(u, "prompt_tokens_details", None)
    return {
        "text": (r.choices[0].message.content or "").strip(),
        "stop": r.choices[0].finish_reason,
        "in": u.prompt_tokens,
        "cached": (getattr(ptd, "cached_tokens", 0) or 0) if ptd else 0,
        "out": u.completion_tokens,  # reasoning 토큰 포함
    }


def call_anthropic(cfg, system, user):
    import anthropic
    client = anthropic.Anthropic(timeout=180.0, max_retries=0)
    r = client.messages.create(
        model=cfg["model"],
        max_tokens=cfg["max_out"],
        output_config={"effort": cfg["effort"]},
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    u = r.usage
    return {
        "text": "".join(b.text for b in r.content if b.type == "text").strip(),
        "stop": r.stop_reason,
        "in": u.input_tokens + (u.cache_read_input_tokens or 0),
        "cached": u.cache_read_input_tokens or 0,
        "out": u.output_tokens,  # thinking 토큰 포함
    }


def available(cfg):
    if cfg["vendor"] == "openai":
        return bool(os.environ.get("OPENAI_API_KEY"))
    if cfg["vendor"] == "zai":
        return bool(os.environ.get("OPENAI_API_KEY_ZAI"))
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def run_one(cfg, system, user):
    t0 = time.perf_counter()
    try:
        fn = call_anthropic if cfg["vendor"] == "anthropic" else call_openai_compat
        res = fn(cfg, system, user)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}", "sec": round(time.perf_counter() - t0, 1)}
    res["sec"] = round(time.perf_counter() - t0, 1)
    if cfg["vendor"] == "anthropic":
        key = "haiku_long" if res["in"] > 100_000 else "haiku"
    else:
        key = "glm" if cfg["vendor"] == "zai" else "luna"
    p_in, p_cache, p_out = PRICES[key]
    res["usd"] = round(((res["in"] - res["cached"]) * p_in + res["cached"] * p_cache
                        + res["out"] * p_out) / 1_000_000, 5)
    return res


# ── 운영 프롬프트 가로채기 ────────────────────────────────────────────────

class _Capture:
    """chat.completions.create 호출 인자를 가로채는 가짜 OpenAI 클라이언트."""

    def __init__(self):
        self.calls = []
        self.chat = self
        self.completions = self

    def with_options(self, **_):
        return self

    def create(self, **kw):
        self.calls.append(kw)

        class _Msg:
            content = "x"

        class _Choice:
            message = _Msg()

        class _Resp:
            choices = [_Choice()]

        return _Resp()


def capture_cases():
    """운영과 같은 데이터·함수로 인사이트 프롬프트와 그 재료(task·domains·rules) 수집."""
    cap = _Capture()
    analytics_insights._client = lambda: cap
    recs = []
    orig_build = prompt_context.build_system_prompt

    def spy(task, lang="ko", domains=None, rules=None):
        recs.append({"task": task, "domains": domains, "rules": rules or []})
        return orig_build(task, lang, domains, rules)

    prompt_context.build_system_prompt = spy
    cases = []

    def grab(label, fn):
        before = len(cap.calls)
        fn()
        if len(cap.calls) == before:
            print(f"[skip] {label}: 데이터 부족으로 호출 없음", flush=True)
            return
        msgs = cap.calls[-1]["messages"]
        cases.append({
            "label": label,
            "kind": label.split(":")[0],
            "system": next(m["content"] for m in msgs if m["role"] == "system"),
            "user": next(m["content"] for m in msgs if m["role"] == "user"),
            **recs[-1],
        })

    try:
        # 선수 탭: HP 출전 상위 2명
        team_hp = queries.team_averages("HP", SEASON)
        if team_hp and "avg_capture" not in team_hp and "avg_ck" in team_hp:
            team_hp["avg_capture"] = team_hp["avg_ck"]
        for p in queries.all_players_overview("HP", SEASON)[:2]:
            stats = queries.player_overall_stats(queries.get_player_id(p["name"]), SEASON)
            grab(f"player:{p['name']}", lambda: analytics_insights.player_profile_insight(
                stats, team_hp if stats.get("hp") else {}, lang="ko"))

        # 매치 탭: 최근 HP·SND 각 1경기
        for mode in ("HP", "SND"):
            ms = queries.match_history(limit=1, mode=mode, season=SEASON)["matches"]
            if ms:
                rep = analytics.match_report(ms[0]["id"])
                grab(f"match:{mode}#{ms[0]['id']}", lambda: analytics_insights.match_insight(rep, lang="ko"))

        # 맵 탭: HP 경기 수 상위 2개 맵
        for m in queries.map_team_stats("HP", season=SEASON)[:2]:
            data = analytics.map_detail(m["map_name"], "HP", season=SEASON)
            if data:
                grab(f"map:{m['map_name']}", lambda: analytics_insights.map_advice(data, lang="ko"))

        # 코칭 허브(대시보드) 브리핑: 최근 10경기
        hub = analytics.coaching_hub(recent_matches=10, season=SEASON)
        hub["open_notes"] = queries.open_notes()
        grab("briefing:recent10", lambda: analytics_insights.briefing_insight(hub, lang="ko"))
    finally:
        prompt_context.build_system_prompt = orig_build
    return cases


# ── 모델별 프롬프트 재배치 (내용은 운영과 동일) ─────────────────────────────

def _knowledge(case):
    docs = []
    for d in case["domains"] if case["domains"] is not None else prompt_context._DEFAULT_DOMAINS:
        rel = coaching_brain_loader._resolve_domain(d)
        text = coaching_brain_loader._read_cached(rel) if rel else ""
        if text:
            docs.append((d, text))
    return {
        "metrics": prompt_context._METRIC_DEFINITIONS + prompt_context.season_baselines_context(),
        "ign": prompt_context._format_ign_map(),
        "docs": docs,
        "date": datetime.date.today().isoformat(),
        "roster": prompt_context.team_roster_context(),
    }


def build_anthropic(case):
    k = _knowledge(case)
    docs = "\n".join(f'<document title="{name}">\n{text}\n</document>' for name, text in k["docs"])
    system = (
        "You are the analytics assistant for a competitive Call of Duty Mobile team's coaching staff. "
        "You turn the team's stat data into short coaching insight shown in their web app. "
        "The reference material below is the coach's own knowledge base; use it to interpret the numbers.\n\n"
        f"<metric_definitions>\n{k['metrics']}\n{k['ign']}\n</metric_definitions>\n\n"
        f"<coaching_knowledge>\n{docs}\n</coaching_knowledge>\n\n"
        f"<team_context>\nDate (meta snapshot): {k['date']}\n{k['roster']}\n</team_context>"
    )
    rules = "\n".join(f"- {r}" for r in case["rules"] + ["Respond in Korean."])
    user = (f"<data>\n{case['user']}\n</data>\n\n<task>\n{case['task']}\n</task>\n\n"
            f"<output_requirements>\n{rules}\n</output_requirements>\n\nWrite the insight now.")
    return system, user


def build_glm(case):
    k = _knowledge(case)
    rules = "\n".join(f"{i}. {r}" for i, r in enumerate(case["rules"] + ["Respond in Korean."], 1))
    docs = "\n\n".join(f"[Coaching knowledge: {name}]\n{text}" for name, text in k["docs"])
    system = (
        "You are a CODM team analytics assistant. Follow the HARD RULES exactly.\n\n"
        f"HARD RULES\n{rules}\n\nTASK\n{case['task']}\n\n"
        f"REFERENCE (for interpretation only)\n{k['metrics']}\n{k['ign']}\n\n"
        f"{docs}\n\n[Team context]\nDate: {k['date']}\n{k['roster']}"
    )
    user = (f"DATA (JSON):\n{case['user']}\n\n"
            "Before answering, silently check every HARD RULE (format, length, every number traceable "
            "to DATA, no win/loss claim without a result, sample-size caution). Then write only the answer.")
    return system, user


BUILDERS = {"prod": lambda c: (c["system"], c["user"]), "anthropic": build_anthropic, "glm": build_glm}


# ── 객관 채점 ────────────────────────────────────────────────────────────

_NUM = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")
SENT_RANGE = {"player": (5, 8), "match": (3, 4), "map": (4, 6)}


def _numbers(obj, out):
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.append(abs(float(obj)))
    elif isinstance(obj, str):
        out.extend(float(m.replace(",", "")) for m in _NUM.findall(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _numbers(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _numbers(v, out)


def score(kind, data_json, text):
    """부호는 무시(−/- 혼용)하고, 데이터·지표 정의·기준선에 없는 숫자를 찾는다."""
    allowed = []
    _numbers(json.loads(data_json), allowed)
    _numbers(prompt_context._METRIC_DEFINITIONS + prompt_context.season_baselines_context(), allowed)
    untraced = []
    for m in _NUM.finditer(text):
        tail = text[m.end():m.end() + 1]
        at_line_start = m.start() == text.rfind("\n", 0, m.start()) + 1
        if tail == "%" or (kind == "briefing" and at_line_start and tail == "."):
            continue
        x = float(m.group().replace(",", ""))
        if not any(abs(x - v) <= max(0.051, 0.006 * v) for v in allowed):
            untraced.append(m.group())
    md_pat = r"\*\*|^#|^\s*[-•*]\s|```" + ("" if kind == "briefing" else r"|^\s*\d+\.\s")
    sentences = [s for s in re.split(r"(?<=[.!?。])\s+", text.strip()) if s.strip()]
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    if kind == "briefing":
        length_ok = len(lines) == 3 and len(text) <= 250
    else:
        lo, hi = SENT_RANGE[kind]
        length_ok = lo <= len(sentences) <= hi
    has_result = json.loads(data_json).get("result") not in (None, "")
    return {
        "chars": len(text),
        "sentences": len(sentences),
        "lines": len(lines),
        "length_ok": length_ok,
        "markdown": bool(re.search(md_pat, text, re.M)),
        "untraced": untraced,
        "result_claim": bool(kind == "match" and not has_result
                             and re.search(r"승리했|패배했|이겼|졌다|진 경기|이긴 경기", text)),
        "overclaim": re.findall(r"무조건|반드시|확실히|확정|주전급|에이스급|완벽", text),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="설정 이름 부분일치 필터 (예: luna, haiku, glm)")
    args = ap.parse_args()

    configs = [c for c in CONFIGS if args.only in c["name"]]
    for c in configs:
        if not available(c):
            print(f"[skip] {c['name']}: API 키 또는 SDK 없음", flush=True)
    configs = [c for c in configs if available(c)]
    if not configs:
        sys.exit("실행할 모델이 없음")

    cases = capture_cases()
    print(f"케이스 {len(cases)}개: {[c['label'] for c in cases]}", flush=True)

    rows = []
    for case in cases:
        for cfg in configs:
            system, user = BUILDERS[cfg["style"]](case)
            print(f"[run] {case['label']} × {cfg['name']} ...", flush=True)
            res = run_one(cfg, system, user)
            row = {"case": case["label"], "config": cfg["name"], **res}
            if "error" not in res:
                row.update(score(case["kind"], case["user"], res["text"]))
                row["fits_15s"] = res["sec"] <= PROD_TIMEOUT
            rows.append(row)
            print("      → " + (res.get("error") or
                  f"{res['sec']}s out={res['out']} chars={row['chars']} len_ok={row['length_ok']} "
                  f"md={row['markdown']} untraced={row['untraced']} overclaim={row['overclaim']}"), flush=True)

    os.makedirs("bench_out", exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(f"bench_out/insight_bench_{stamp}.json", "w", encoding="utf-8") as f:
        json.dump({"season": SEASON, "cases": [{k: v for k, v in c.items() if k != "system"} for c in cases],
                   "rows": rows}, f, ensure_ascii=False, indent=2)

    md = [f"# 인사이트 모델 실측 ({stamp}, 시즌 {SEASON})", "",
          "| 케이스 | 설정 | 시간(s) | ≤15s | 출력토큰 | 글자 | 문장/줄 | 길이OK | 마크다운 | 추적불가 숫자 | 승패단정 | 과장어 | 비용($) |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if "error" in r:
            md.append(f"| {r['case']} | {r['config']} | ERROR {r['error'][:60]} |" + " |" * 10)
            continue
        md.append(f"| {r['case']} | {r['config']} | {r['sec']} | {'O' if r['fits_15s'] else 'X'} | "
                  f"{r['out']:,} | {r['chars']} | {r['sentences']}/{r['lines']} | "
                  f"{'O' if r['length_ok'] else 'X'} | {'X' if r['markdown'] else 'O'} | "
                  f"{', '.join(r['untraced']) or '-'} | {'X' if r['result_claim'] else '-'} | "
                  f"{', '.join(r['overclaim']) or '-'} | {r['usd']:.4f} |")
    for case in cases:
        md += ["", f"## {case['label']}", "", "<details><summary>입력 데이터(user)</summary>", "",
               "```json", case["user"][:6000], "```", "</details>"]
        for r in rows:
            if r["case"] == case["label"] and "error" not in r:
                md += ["", f"### {r['config']}", "", r["text"] or "(빈 응답)"]
    out = f"bench_out/insight_bench_{stamp}.md"
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    print(f"\n결과: {out}", flush=True)


if __name__ == "__main__":
    main()
