# GPT 자연어 인사이트 생성
#
# analytics.py가 만든 숫자 데이터를 GPT에게 넘겨
# 자연어 코칭 인사이트로 요약한다.
# (숫자만 보여주는 것보다 "Shisui가 이번 매치 폼이 좋았다" 식의 통찰이 유용)
#
# 모든 함수는 lang 파라미터("ko"/"en"/"es")를 받아 응답 언어를 제어한다.
# 코치용 페이지는 ko, 선수용은 en/es.

import json

import config
import prompt_context
from openai import OpenAI


def _domains_for_match(mode: str, map_name: str = None, extra: list = None) -> list:
    """매치/맵 계열 인사이트 공용: 모드+맵 도메인 조합.

    mode: 'HP'/'SND'/'Control'. map_name: DB map_name (대소문자 무관, loader가 매칭).
    extra: 추가 영역 (예: ['team','mechanics-terms']).
    """
    d = ["principles", "mechanics-core"]
    mode_key = {"HP": "mode-hp", "SND": "mode-snd", "CTRL": "mode-control",
                "Control": "mode-control"}.get(mode)
    if mode_key:
        d.append(mode_key)
    if map_name:
        d.append(f"maps:{map_name}")  # 코칭 브레인에 없으면 loader가 스킵
    if extra:
        d.extend(extra)
    return d


def _domains_for_player(stats: dict) -> list:
    """선수 프로필용 도메인: hp/snd 존재 여부로 모드 영역 선택."""
    d = ["principles", "mechanics-core", "mechanics-meta"]
    if stats.get("hp"):
        d.append("mode-hp")
    if stats.get("snd"):
        d.append("mode-snd")
    if stats.get("ctrl"):
        d.append("mode-control")
    return d


_openai = None

# 언어별 시스템 프롬프트 지시문
_LANG_INSTRUCT = {
    "ko": "한국어로",
    "en": "in English",
    "es": "en español",
}


def _client():
    global _openai
    if _openai is None:
        # timeout=15s: 인사이트 동기 대기 무한정 블록 방지.
        # max_retries=1: 지연 시 재시도 최소화 (기본 2 → 3배 지연 위험).
        _openai = OpenAI(api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL,
                         timeout=15.0, max_retries=1)
    return _openai


def _lang_instruction(lang: str) -> str:
    return _LANG_INSTRUCT.get(lang, _LANG_INSTRUCT["ko"])


# 웹 인사이트 출력 한도 — reasoning 토큰도 여기서 차감되므로 넉넉히 둔다.
# 실측(Luna low) 최대 ~400토큰. 길이는 _web_rules가 통제하고, 이 값은 잘림 방지용 안전판.
_WEB_MAX_OUT = 1500


def _web_rules(length: str, numbered: bool = False) -> list:
    """웹 인사이트 공통 출력 규칙 (2026-10 모델·프롬프트 실측으로 확정).

    웹은 textContent로 넣어 마크다운이 기호 그대로 보이고, 근거 없는 승패·과장 표현이
    실측에서 반복돼 규칙으로 명시한다. 이유를 함께 적어야 모델이 일관되게 지킨다.
    """
    fmt = ("Plain text only — the page inserts it with textContent, so markdown (**, #, bullet "
           "symbols, code blocks), JSON and emoji would show up as literal characters. No title.")
    if numbered:
        fmt = ("Plain text except the required '1. ' line numbers — the page inserts it with "
               "textContent, so other markdown, emoji or a title would show up as literal characters.")
    return [
        fmt,
        f"Length: {length}. The insight sits next to the numbers on the page — longer is not better.",
        "Use only numbers from the data or the baselines (a simple ± % between two of them is fine). "
        "If the data has no result or score, never say the team won or lost.",
        "When a figure rests on fewer than 3 matches, call it tentative and avoid labels like 'ace' "
        "or absolute wording ('must', 'definitely', 'guaranteed').",
        "Use the formal IGNs.",
    ]


def match_insight(report: dict, lang: str = "ko") -> str:
    """매치 리포트 데이터 → 1-2문장 자연어 인사이트.

    실패 시 빈 문자열 반환 (리포트 표시에 영향 주지 않음).
    """
    if not report:
        return ""
    try:
        # team_totals의 zcs/rds는 선수 평균, score는 인게임 점수 합 — 이름 그대로 넘기면
        # AI가 "팀 ZCS 합계"·"팀 점수(=스코어)"로 오독하므로 의미가 드러나게 바꿔 넘긴다.
        totals = dict(report["team_totals"] or {})
        for old, new in (("zcs", "zcs_avg_per_player"), ("rds", "rds_avg_per_player"),
                         ("score", "ingame_score_sum")):
            if old in totals:
                totals[new] = totals.pop(old)
        data = {
            "mode": report["mode"],
            "map": report.get("map_name"),
            "result": report.get("result"),
            "team_score": report.get("team_score"),
            "opponent_score": report.get("opponent_score"),
            "mom": report["mom"],
            "best": report["best"],
            "worst": report["worst"],
            "team_totals": totals,
            "players": report["players"],
        }
        completion = _client().chat.completions.create(
            model=config.OPENAI_MODEL,
            **config.chat_params(0.5, _WEB_MAX_OUT),
            messages=[
                {
                    "role": "system",
                    "content": prompt_context.build_system_prompt(
                        "Write 3-4 sentences of key insight from the match stats JSON. "
                        "Provide insight (who had good form, team strengths/weaknesses, "
                        "what stands out tactically — e.g. anchor play, slayer dominance, "
                        "ZCS outliers), not just a list of numbers. "
                        "For the match page and Discord.",
                        lang,
                        domains=_domains_for_match(report["mode"], report.get("map_name")),
                        rules=_web_rules("3-4 sentences"),
                    ),
                },
                {"role": "user", "content": json.dumps(data, ensure_ascii=False, default=str)},
            ],
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        import traceback
        print(f"[match_insight] ERROR: {e}\n{traceback.format_exc()}", flush=True)
        return ""


def weekly_insight(report: dict, lang: str = "ko") -> str:
    """주간 트렌드 데이터 → 자연어 요약."""
    if not report or not report.get("players"):
        return ""
    try:
        data = {
            "period": report["period"],
            "matches_recent": report["matches_recent"],
            "players": report["players"],
        }
        completion = _client().chat.completions.create(
            model=config.OPENAI_MODEL,
            **config.chat_params(0.5, 600),
            messages=[
                {
                    "role": "system",
                    "content": prompt_context.build_system_prompt(
                        "Summarize the weekly trend data in 4-6 sentences. "
                        "Include rising/falling players (with role context — e.g. 'the AR slayer "
                        "is finding form'), notable changes, and coaching suggestions. "
                        "Actionable, for Discord.",
                        lang,
                        domains=["principles", "mechanics-core", "team"],
                    ),
                },
                {"role": "user", "content": json.dumps(data, ensure_ascii=False, default=str)},
            ],
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        import traceback
        print(f"[weekly_insight] ERROR: {e}\n{traceback.format_exc()}", flush=True)
        return ""


def trend_insight(trend: dict, lang: str = "ko") -> str:
    """선수 트렌드 데이터 → 자연어 폼 진단."""
    if not trend:
        return ""
    try:
        data = {
            "name": trend["name"],
            "mode": trend["mode"],
            "recent_matches": trend["recent_matches"],
            "recent": trend["recent"],
            "overall": trend["overall"],
            "delta": trend["delta"],
            "last_matches": trend["last_matches"],
        }
        li = _lang_instruction(lang)
        completion = _client().chat.completions.create(
            model=config.OPENAI_MODEL,
            **config.chat_params(0.5, 500),
            messages=[
                {
                    "role": "system",
                    "content": prompt_context.build_system_prompt(
                        f"Diagnose the player's recent form vs overall average in 2-4 "
                        f"sentences {li}. Include whether rising/falling with specific "
                        f"numeric evidence.",
                        lang,
                        domains=_domains_for_match(trend.get("mode")),
                    ),
                },
                {"role": "user", "content": json.dumps(data, ensure_ascii=False, default=str)},
            ],
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        import traceback
        print(f"[trend_insight] ERROR: {e}\n{traceback.format_exc()}", flush=True)
        return ""


def player_profile_insight(stats: dict, team_hp: dict = None, lang: str = "ko") -> str:
    """선수 프로필 페이지용 종합 인사이트 (웹).

    강점/약점(팀 평균 대비), 플레이 스타일 치우침, 안정성 등을
    자연어로 요약. 실패 시 빈 문자열.
    """
    if not stats or not (stats.get("hp") or stats.get("snd") or stats.get("ctrl")):
        return ""
    try:
        data = {
            "name": stats["name"],
            "hp": stats.get("hp"),
            "snd": stats.get("snd"),
            "ctrl": stats.get("ctrl"),
            "team_hp_avg": team_hp,
        }
        completion = _client().chat.completions.create(
            model=config.OPENAI_MODEL,
            **config.chat_params(0.5, _WEB_MAX_OUT),
            messages=[
                {
                    "role": "system",
                    "content": prompt_context.build_system_prompt(
                        "Write 5-8 sentences of coaching insight from a player's overall stats "
                        "and team average. Include: 1) clear strengths/weaknesses vs team average "
                        "(mention ±% with metric interpretation), "
                        f"2) play style bias — "
                        f"{'infer slayer/objective/balanced from OBJ, CapKill, ZCS, DPD (HP-only metrics). ' if stats.get('hp') else ''}"
                        f"3) form stability (mention std dev if present). "
                        f"IMPORTANT: ZCS/OBJ/CapKill are HP-only metrics — never reference them for SND-only or Control-only data. "
                        f"Grounded in numbers, no over-interpretation. Actionable, for web display.",
                        lang,
                        domains=_domains_for_player(stats),
                        rules=_web_rules("5-8 sentences"),
                    ),
                },
                {"role": "user", "content": json.dumps(data, ensure_ascii=False, default=str)},
            ],
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        import traceback
        print(f"[player_profile_insight] ERROR: {e}\n{traceback.format_exc()}", flush=True)
        return ""


def map_advice(map_data: dict, lang: str = "ko") -> str:
    """단일 맵에 대한 간접적 수치 경향성 제언.

    직접적 지시("X를 해라")가 아닌 수치 기반 경향성 짚기:
    - 팀 K/D/(HP면 ZCS)의 최근 vs 시즌 변화
    - 선수별 이 맵 퍼포먼스 분포 (HP면 ZCS 위주, SND면 K/D·FK·LWW)
    - 승률 경향 (데이터 있을 때)
    실패 시 빈 문자열.
    """
    if not map_data:
        return ""
    try:
        mode = map_data.get("mode", "HP")
        is_hp = mode == "HP"
        # AI에게 넘길 핵심 수치만 추출 (HP만 ZCS 포함)
        if is_hp:
            player_keys = ("player_name", "matches", "avg_kd",
                           "avg_zcs", "avg_k", "avg_dmg", "avg_obj")
        elif mode == "CTRL":
            player_keys = ("player_name", "matches", "avg_kd",
                           "avg_k", "avg_dmg", "avg_capture")
        else:
            player_keys = ("player_name", "matches", "avg_kd",
                           "avg_k", "avg_d", "avg_score")
        payload = {
            "map_name": map_data["map_name"],
            "mode": mode,
            "trend": map_data.get("trend"),
            "win_loss": map_data.get("win_loss"),
            "players": [
                {k: p.get(k) for k in player_keys}
                for p in map_data.get("players", [])
            ],
            "team_avg": map_data.get("team_avg"),
        }
        zcs_hint = (
            "'player X has highest ZCS at 220'). " if is_hp else ""
        )
        completion = _client().chat.completions.create(
            model=config.OPENAI_MODEL,
            **config.chat_params(0.4, _WEB_MAX_OUT),
            messages=[
                {
                    "role": "system",
                    "content": prompt_context.build_system_prompt(
                        f"Describe the NUMERIC TRENDS of one map ({mode}) in 4-6 sentences. "
                        f"RULES: only point out statistical tendencies (e.g. 'on this map "
                        f"team K/D is -12% vs season'{zcs_hint}"
                        + ("Do NOT mention ZCS — it is undefined for SND/Control. " if not is_hp else "")
                        + "). Cross-reference the map tendency in your domain context when "
                        "relevant. Do NOT give direct orders or tactical instructions. "
                        "Stick to what the numbers show — let the coach interpret. "
                        "Grounded strictly in the JSON. For web display.",
                        lang,
                        domains=_domains_for_match(mode, map_data.get("map_name"),
                                                   extra=["mechanics-terms"]),
                        rules=_web_rules("4-6 sentences"),
                    ),
                },
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
            ],
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        import traceback
        print(f"[map_advice] ERROR: {e}\n{traceback.format_exc()}", flush=True)
        return ""


def summarize_transcript(report: dict, transcript: str, lang: str = "ko") -> str:
    """경기 전사(voice/text transcript) 파일을 코칭 관점에서 요약.

    report: analytics.match_report() 결과 (수치 컨텍스트).
    transcript: 업로드된 전사 원문 텍스트.
    반환: 요약문 (실패 시 빈 문자열). 원문은 저장하지 않고 요약만 반환.
    """
    if not transcript or not transcript.strip():
        return ""
    try:
        # 전사가 너무 길면 자름 (약 60000자 ≈ 25k토큰 — luna 단가로 1회 ~$0.005)
        trunc = transcript[:60000]
        if len(transcript) > 60000:
            trunc += "\n...[전사 일부 생략]..."

        # 수치 컨텍스트 압축 (전체 report는 너무 큼)
        ctx = {
            "mode": report.get("mode"),
            "map": report.get("map_name"),
            "date": report.get("match_date"),
            "result": report.get("result"),
            "score": f"{report.get('team_score')}-{report.get('opponent_score')}" if report.get("team_score") is not None else None,
            "mom": report.get("mom"),
            "team_totals": report.get("team_totals"),
        }

        # 입력이 커서(~45k토큰) 공용 15s 타임아웃으론 부족 → 요약만 60s.
        # 출력 한도는 reasoning 토큰 포함이라 넉넉히 2000.
        completion = _client().with_options(timeout=60.0).chat.completions.create(
            model=config.OPENAI_MODEL,
            **config.chat_params(0.4, 2000),
            messages=[
                {
                    "role": "system",
                    "content": prompt_context.build_system_prompt(
                        "Summarize a match transcript (voice-to-text from a coaching VOD review) "
                        "for the coach. Write a review in 8-12 sentences covering: "
                        "1) key moments/turning points of the round flow, "
                        "2) tactical decisions (rotations, setups, spawn flips, holder positions) mentioned, "
                        "3) communication/callout observations, "
                        "4) connect the transcript narrative with the numeric stats provided "
                        "(MOM, K/D, ZCS, score, mode-appropriate metrics). "
                        "IMPORTANT: transcript text has pronunciation drift (e.g. 'Mao' = Maozyn, "
                        "'Shizi' = Shisui, 'P3' = the third hardpoint) — use the formal IGNs and "
                        "tactical terms in your output. Grounded in transcript + match numbers. "
                        "No fabrication. For internal coach review display.",
                        lang,
                        domains=_domains_for_match(
                            report.get("mode"),
                            report.get("map_name"),
                            extra=["mechanics-terms", "team"],
                        ),
                    ),
                },
                {"role": "user", "content": json.dumps(
                    {"match_context": ctx, "transcript": trunc}, ensure_ascii=False, default=str
                )},
            ],
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        import traceback
        print(f"[summarize_transcript] ERROR: {e}\n{traceback.format_exc()}", flush=True)
        return ""


def briefing_insight(hub_data: dict, lang: str = "ko") -> str:
    """코칭 허브 데이터 → 프리매치 브리핑 (코치 전용).

    폼 경고·맵 델타·역할 스펙트럼·ZCS 추이·미해결 노트를 종합해
    "다음 매치 전 봐야 할 3가지"를 생성. 직접 제안 허용 (코치 전용).
    실패/데이터 부족 시 빈 문자열 반환.
    """
    if not hub_data:
        return ""
    # 데이터 최소 임계 — 매치 수 3 미만이면 브리핑 무의미
    period_matches = (hub_data.get("summary") or {}).get("period_matches") or 0
    if period_matches < 3:
        return ""
    try:
        data = {
            "period_matches": period_matches,
            "summary": hub_data.get("summary"),
            "form_alerts": [
                {"name": p["name"], "delta_pct": p["delta_pct"],
                 "season_kd": p["season_kd"], "recent_kd": p["recent_kd"]}
                for p in (hub_data.get("form_alerts") or [])
            ],
            "banpick": [
                {"map": m["map_name"], "mode": mode,
                 "score": m["score"], "delta": m["delta_pct"],
                 "badge": m["badge"], "n": m["recent_matches"]}
                for mode in ("HP", "SND", "CTRL")
                for m in ((hub_data.get("banpick") or {}).get(mode, {}) or {}).get("ranked", [])
            ],
            "roles": [
                {"name": r["name"], "role": r["role"],
                 "slay": r.get("slay_score"), "obj": r.get("obj_score")}
                for r in (hub_data.get("roles") or [])
            ],
            "open_notes_count": len(hub_data.get("open_notes") or []),
        }
        completion = _client().chat.completions.create(
            model=config.OPENAI_MODEL,
            **config.chat_params(0.4, _WEB_MAX_OUT),
            messages=[
                {
                    "role": "system",
                    "content": prompt_context.build_system_prompt(
                        "You are the coach's pre-match briefing. Produce EXACTLY 3 items, "
                        "each item = one action line + one supporting number. "
                        "Sources: form_alerts (slumping players), banpick (map score/delta/badge — "
                        "PICK maps are strong, BAN maps are weak), "
                        "role spectrum (composition skew), open_notes (unresolved action items). "
                        "Be DIRECT and prescriptive (the coach acts on this) — unlike player-facing map advice, "
                        "you MAY give concrete directives ('Focus X', 'Ban Y'). "
                        "Format strictly: 3 lines, each '1. <conclusion> — <number>'. "
                        "Label each number with what it is, plus n when the data gives a sample size "
                        "(e.g. 'Takeoff score -50.6, n=15') — a bare number means nothing to the coach. "
                        "No preamble, no closing remarks. "
                        "Grounded only in the provided data; no fabrication.",
                        lang,
                        domains=["principles", "mechanics-core", "team", "mechanics-meta"],
                        rules=_web_rules("exactly 3 lines, about 150-250 characters in total",
                                         numbered=True),
                    ),
                },
                {"role": "user", "content": json.dumps(data, ensure_ascii=False, default=str)},
            ],
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        import traceback
        print(f"[briefing_insight] ERROR: {e}\n{traceback.format_exc()}", flush=True)
        return ""
