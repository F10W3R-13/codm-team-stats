# 버그·품질 감사 보고서 (2026-07-11)

범위: 정확성 버그 + 코드 품질. 8개 핵심 모듈 + 주요 템플릿 4개. **픽스 없이 보고만.**

심각도: 🔴 크리티컬(고장/데이터 손상) · 🟡 주의(잠재적 오작동/보안) · ⚪ 품질(유지보수)

---

## 핵심 요약

- 🔴 **2건** — `id` 키 재사용 함정 (데이터 정합성)
- 🟡 **15건** — 보안 5 / 정확성 6 / 가용성·UI 4
- ⚪ **10건** — 데드 코드, 로그, 타입 힌트, N+1

**가장 시급한 3가지:**
1. **기본 관리자 비밀번호 "3717" + SECRET_KEY 파생** → 쿠키 위조 가능 (config.py)
2. **`id` 키를 impact delta 메트릭으로 재사용** → 자료구조 전체에 함정, 정규화 땜질 코드 강제 (queries.py)
3. **인사이트 API `/api/insight/*` 전체 인증 없음** → GPT 비용 남용, 브리핑(코치 전용) 노출 (web_api.py)

---

## 🔴 크리티컬 (2)

### 🔴-1 `id` 키를 impact delta 메트릭 용도로 재사용 — player_id와 충돌
- **위치:** `queries.py:140` (`all_hp_metrics` 반환 dict의 `"id"` 키) → `queries.py:93-100`, `queries.py:917`
- **증상:** `metrics.all_hp_metrics()`가 impact delta를 `"id"` 키로 반환. 이게 `team_averages`(`queries.py:147-161`)에서 평균되어 `team_hp["id"]` = impact delta 평균이 됨. `map_trend`의 `block["id"]`(`:917`)도 동일.
- **영향:** 자료구조 전체에서 `["id"]`가 player_id인지 impact delta인지 알 수 없음. `web_api.py:131-137`이 이를 땜질하려 `team_hp["impact_delta"] = team_hp["id"]` 별칭 복사 코드를 강제. 향후 `team_hp.get("id")`로 player_id 찾는 코드가 생기면 잘못된 값 사용.
- **제안:** `all_hp_metrics`의 반환 키를 `"impact_delta"`로改名. `id` 키는 메트릭용으로 쓰지 말 것.

### 🔴-2 `player_overall_stats` HP 메트릭 중복 계산 + `id` 잔류
- **위치:** `queries.py:93-100` (첫 update) + `queries.py:129-142` (두 번째 계산)
- **증상:** 같은 HP 블록에서 `metrics.all_hp_metrics(...)`를 **두 번** 호출. 첫 update(95-100)가 `id`, `impact`, `dpd`, `dpk` 등을 넣고, 두 번째(130-142)가 `dpd/dpk/impact_delta/ap_pct/zcs`를 다시 계산해 덮어씀. 첫 호출의 `id` 키는 제거되지 않고 잔류.
- **영향:** 동일 비싼 계산 2회 실행(성능 낭비) + `result["hp"]["id"]` = impact delta 잔류로 🔴-1과 같은 함정. `web_api.py:95` 주석이 이미 이를 경고.
- **제안:** 95-100 첫 `.update(m)` 제거, 132-142의 명시적 매핑만 유지. `h.pop("id", None)` 후 `impact_delta`로만 노출.

---

## 🟡 주의 — 보안 (5)

### 🟡-3 기본 관리자 비밀번호 "3717" + SECRET_KEY가 비밀번호에서 파생
- **위치:** `config.py:31,33` (사용: `auth.py:14,20`)
- **증상:** `ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "3717")`. 더 심각한 건 `SECRET_KEY = os.environ.get("SECRET_KEY") or f"codm-admin-{ADMIN_PASSWORD}"` — 환경변수 미설정 시 서명 키가 비밀번호에서 파생.
- **영향:** 환경변수 미설정 배포 시 공격자가 `"codm-admin-3717"`을 알아내어 유효한 `admin_session` 쿠키 **위조 가능** → 관리자 권한 완전 탈취.
- **제안:** SECRET_KEY를 ADMIN_PASSWORD와 독립된 **필수** 환경변수로 강제, 미설정 시 서버 시작 거부.

### 🟡-4 인사이트 API `/api/insight/*` 전체 인증 없음
- **위치:** `web_api.py:247-330` (미들웨어 `web_api.py:67-76`은 `/admin` 접두사만 검사)
- **증상:** `/api/insight/player`, `/match`, `/map`, **`/api/insight/briefing`**(코치 전용 주석)이 인증 검사 없이 노출.
- **영향:** 누구나(선수/외부인) URL 직접 호출로 GPT 비용 발생 엔드포인트 남용 → 비용 폭주. 브리핑은 민감 팀 분석 노출.
- **제안:** 미들웨어에서 `/api/insight/`도 보호 대상 포함, 또는 각 엔드포인트에 인증 쿠키 검사.

### 🟡-5 비밀번호 비교가 상수시간이 아님 (타이밍 공격)
- **위치:** `auth.py:20` — `return password == config.ADMIN_PASSWORD`
- **증상:** Python `==`는 첫 바이트 차이로 조기 반환 → 응답 시간 차이로 비밀번호 한 글자씩 추론 가능.
- **영향:** 로컬은 낮지만 Railway 배포 시 네트워크 타이밍 공격 이론적 가능.
- **제안:** `hmac.compare_digest(password, config.ADMIN_PASSWORD)`.

### 🟡-6 Discord `/addalias`, `/removealias` 권한 검증 없음
- **위치:** `commands_cog.py:404-421`
- **증상:** 누구나 실행 가능. alias(IGN→선수 매핑) 즉시 DB 반영. `@app_commands.default_permissions` 또는 역할 검사 없음.
- **영향:** 임의 멤버가 선수 식별 정규화 데이터 조작 → 이후 OCR/GPT 매치 분석 선수 매핑 꼬임. 웹 `/admin/alias`는 인증됨 — 불일치.
- **제안:** 코치/관리자 역할 권한 검증 추가.

### 🟡-7 인증 쿠키 `secure=False`
- **위치:** `web_api.py:381`
- **증상:** `secure=False` 명시. 주석은 "Railway는 HTTPS termination"이라 정당화하나 HTTP 링크로 쿠키 평문 전송 가능.
- **영향:** MITM 환경에서 세션 쿠키 탈취 가능성.
- **제안:** `secure=(request.url.scheme == "https")` 또는 환경변수 토글.

---

## 🟡 주의 — 정확성 (6)

### 🟡-8 `compute_id`가 score=0인 정상 데이터를 None 처리
- **위치:** `metrics.py:39` — `if impact is None or not score: return None`
- **증상:** `not score`는 `score == 0`을 걸러냄. 공식 `ID = Impact − Score/34`에서 score=0이면 `ID = Impact`이 정답. 34는 분모라 0으로 나눌 위험 자체가 없음.
- **영향:** score 0점 경기의 모든 선수 ID가 None으로 누락. 리더보드/비교 표 ID 행 빈칸.
- **제안:** `if impact is None: return None`만 남기고 score는 `0`일 때 그대로 `impact - 0` 계산.

### 🟡-9 `compute_dpd`/`compute_dpk`가 total_damage=0인 유효 데이터를 None 처리
- **위치:** `metrics.py:25` (`compute_dpd`), `metrics.py:32` (`compute_dpk`)
- **증상:** `if not total_damage or not deaths` — 분자(total_damage=0)까지 None 처리. `0/deaths = 0`은 유효값.
- **영향:** 데미지 0짜리 경기(OCR/마이그레이션 누락)의 DPD/DPK 누락. 분모 보호는 `or not deaths`/`or not kills`로 정확히 되어 있으나 분자까지 가드하는 게 논리 오류.
- **제안:** `if not deaths:` (DPD) / `if not kills:` (DPK)로 분모만 가드.

### 🟡-10 SND 리더보드 `avg_dmg`가 실제로는 AVG(score) 반환 (라벨 드리프트)
- **위치:** `queries.py:193` — `"avg_dmg": "AVG(score)"  # SND는 total_damage 없음 → score로 대체`
- **증상:** SND에서 `leaderboard(metric="avg_dmg")`는 value=AVG(score)이지만 라벨/키는 `avg_dmg`.
- **영향:** `/leaderboard?mode=SND&metric=avg_dmg`가 "딜량" 라벨 아래 점수 평균 표시. 사용자 오인.
- **제안:** SND에선 `avg_dmg`를 valid 집합(`:170`)에서 제외하고 폴백을 `avg_kd`로, 또는 SND 전용 `avg_score` 별도 노출.

### 🟡-11 player_trend 데스 delta "낮을수록 좋음" 방향 처리 누락
- **위치:** `analytics.py:282-287`
- **증상:** `delta["d_pct"] = (recent_d - overall_d)/overall_d*100`. 데스는 lower-better지만 부호 안 뒤집음. K/KD와 같은 양수=좋음 체계 공유.
- **영향:** `trend_insight()`(GPT)에 넘겨지는 `d_pct: +20%`가 "데스 20% 증가=나쁨"인데 K처럼 해석될 여지. 폼 진단이 데스 증가를 "상승"으로 오독.
- **제안:** 데스 delta 부호 반전, 또는 `delta["lower_is_better"] = True` 플래그 추가, 또는 프롬프트에 방향 명시.

### 🟡-12 `bot.py` result 키 이중 사용 폴백 — 엣지 케이스 버그
- **위치:** `bot.py:219-220` — `players = result.get("players") or result.get("result", [])`
- **증상:** 구버전 호환용 `"result"` 키가 선수 배열이었다고 가정. 신규 프롬프트에선 `"result"`가 승패 문자열("WIN"/"LOSS"). `players`가 빈 배열이고 `result`가 문자열이면, `players`가 문자열을 받아 `len(players)`가 문자열 길이, 이후 `for p in players`가 문자열을 한 글자씩 순회.
- **영향:** 신규 프롬프트에서 `players` 비어있는 예외적 경우에만 발현. 현실적 발현 낮으나 잠재적 데이터 손상.
- **제안:** 구버전 폴백 제거 또는 `result.get("result", [])`에 `isinstance(..., list)` 가드 추가.

### 🟡-13 GPT 응답 `result` 키가 빈 배열/문자열 혼동 — `bot.py` 연쇄
- **위치:** `bot.py:219-220` (위 🟡-12와 동일 위치, 별개 증상)
- **증상:** `or` 폴백으로 인해 GPT가 `{"result": "WIN", "players": []}`를 반환하면 `players` 변수가 `"WIN"` 문자열에 바인딩.
- **제안:** 🟡-12 해결로 동일 처리.

> 🟡-12와 🟡-13은 동일 라인의 두 가지 증상이므로 한 번에 수정 가능.

---

## 🟡 주의 — 가용성·UI (4)

### 🟡-14 `/admin/day/{date}/transcript` 동기 GPT 호출이 이벤트 루프 블록
- **위치:** `web_api.py:481`
- **증상:** `summarize_transcript(...)`를 `await` 없이 동기 직접 호출. 다른 인사이트 엔드포인트(`:266,282,299,326`)는 모두 `run_in_executor`로 비동기 처리하지만 여기만 동기.
- **영향:** 전사 요약 GPT 호출(수 초~수십 초) 동안 FastAPI 워커 이벤트 루프 전체 블록 → 다른 모든 요청 멈춤.
- **제안:** `await loop.run_in_executor(None, lambda: analytics_insights.summarize_transcript(...))`로 래핑.

### 🟡-15 7개 GPT 인사이트 함수가 예외 삼킴 (로깅 없음)
- **위치:** `analytics_insights.py:75-76, 109-110, 145-146, 188-189, 224-225, 287-288, 346-347`
- **증상:** `except Exception: return ""` — API 타임아웃/키 오류/직렬화 실패/KeyError든 빈 문자열로 변환, 스택트레이스 없음. `briefing_insight`(`:411-414`)만 유일하게 `as e` + traceback.
- **영향:** API 키 만료/할트 초과/프롬프트 버그가 조용히 빈칸으로 떠서 원인 진단 불가. "왜 인사이트가 안 뜨나" 디버깅 비용 큼.
- **제안:** 모든 `except Exception:`을 `except Exception as e:` + `traceback.print_exc()`로 통일. `briefing_insight` 패턴 적용.

### 🟡-16 GPT 비전 API 호출(bot.py) 타임아웃 없음
- **위치:** `bot.py:75-106` (`analyze_images`)
- **증상:** `openai_client.chat.completions.create(...)`에 `timeout=` 미지정. OpenAI 기본값(600s)에 의존.
- **영향:** API 지연/멈춤 시 `on_message` 핸들러가 `async with message.channel.typing()` 블록에서 장시간 대기 → 후속 스크린샷 무시.
- **제안:** `timeout=60` 명시.

### 🟡-17 `_learn_alias`/`add_alias`/`_has_column` 모든 예외 삼킴
- **위치:** `db.py:442-457` (`_learn_alias`), `db.py:487-488` (`add_alias`), `db.py:357-358` (`_has_column`)
- **증상:** `except Exception: pass` — UNIQUE 충돌 외에도 connection 오류, 문법 오류, NOT NULL 위반을 전부 조용히 무시.
- **영향:** alias 자가학습 조용히 실패 → 다음 매치부터 매칭 비용 증가. `_has_column`이 거짓 False 반환하면 upsert RETURNING 생략 부작용.
- **제안:** 최소한 UNIQUE/IntegrityError만 잡고, 다른 예외는 로깅 후 재발생.

---

## 🟡 주의 — SQL/Postgres 호환성 (3)

### 🟡-18 `recent_ids` 서브쿼리 파라미터화 안 됨 (정수 캐스팅으로 완화됨)
- **위치:** `queries.py:704, 752` (+ `:618-620, :868-871` 날짜 보간)
- **증상:** `f"SELECT id FROM matches WHERE mode='{mode}' ORDER BY id DESC LIMIT {int(recent_matches)}"`. `mode`를 f-string 직접 삽입, `recent_matches`/`days`는 `int()` 캐스트 후 삽입.
- **영향:** 현재는 화이트리스트(`"HP"/"SND"`, 정수)라 안전. 그러나 파라미터화 패턴이 아니라 향후 `mode` 검증 빠지면 SQL 인젝션.
- **제안:** `mode`, `recent_matches`, `days` 모두 placeholder(`?`/`%s`)로 바인드.

### 🟡-19 `match_history_grouped` 두 번째 SELECT — ORDER BY 표현식 일관성
- **위치:** `queries.py:555` — `ORDER BY (m.match_date IS NULL), m.match_date DESC, m.id DESC`
- **증상:** 첫 쿼리(`:521-523`)는 `(match_date IS NULL) is_null`을 SELECT 리스트에 넣음(AGENTS.md §8 권장 패턴). 두 번째(`:555`)는 SELECT 리스트 없이 ORDER BY에 직접.
- **영향:** 현재 일반 SELECT라 Postgres에서 작동. 그러나 DISTINCT/집계로 리팩터링 시 즉시 에러. AGENTS.md 명시 경고 패턴과 불일치.
- **제안:** 첫 쿼리와 동일하게 `(m.match_date IS NULL) is_null`을 SELECT 리스트에 추가.

### 🟡-20 `match_history_grouped` 날짜 그룹핑 None 블록 데드 조건
- **위치:** `queries.py:583-588`
- **증상:** 584-585 루프의 복잡한 조건식이 None 그룹에서는 587-588이 항상 이겨 데드 코드.
- **영향:** 동작은 올바르나 가독성 저하, 유지보수 시 585 조건 잘못 손댈 위험.
- **제안:** `if d is None: ... else: ...` 명시적 분기.

---

## ⚪ 품질 (10)

### ⚪-21 compare 레이더 차트 축 라벨이 번역 안 된 원시 i18n 키로 표시
- **위치:** `compare.html:123, 133` — `labels = chartData.map(d => d.metric)`
- **증상:** `d.metric`이 i18n 키(`"zcs_label"`, `"m_dpd"` 등). 표 헤더(`:82`)는 `t[row.label_key]`로 번역하지만 차트는 미번역.
- **영향:** 레이더 7~10개 축이 원시 키로 표시. 언어 불문.
- **제안:** JS에 `t` 사전 주입해 매핑, 또는 서버에서 번역 라벨 추가 제공.

### ⚪-22 다크모드 토글 시 차트 채우기색(backgroundColor) 갱신 안 됨
- **위치:** `compare.html:139, 145, 157-160` (레이더), `coaching_hub.html:342-351` (ZCS 스파크)
- **증상:** dataset `backgroundColor` 하드코딩. `_onThemeChange`가 `borderColor`만 갱신. ZCS 차트는 콜백 자체 미정의.
- **영향:** 다크 배경 위에 라이트용 진한 색 블롭. AGENTS.md §8 Chart.js 규칙 위반.
- **제안:** `_onThemeChange`에서 `backgroundColor`도 `tds.accent`/`tds.danger` 기반 rgba로 갱신.

### ⚪-23 HP 인사이트 카드 숨김 상태에서 fetch 결과 안 보임
- **위치:** `player_detail.html:113, 117-131`
- **증상:** 카드 숨김 조건 `{% if not insight and not stats.hp and not stats.snd %}`인데 fetch 스크립트는 항상 렌더. 숨겨진 카드에서 fetch 성공해도 `display:none`이라 안 보임.
- **영향:** HP/SND 없는 선수의 캐시된 인사이트가 사용자에게 미표시.
- **제안:** 숨김 시 fetch 스크립트도 `{% if stats.hp or stats.snd %}`로 감쌈.

### ⚪-24 compare 델타(Δ) 색상이 lower-better 지표 잘못 표시
- **위치:** `compare.html:90-95`
- **증상:** `d > 0`이면 `.delta-up`(녹색). `avg_d`(데스)에서 A가 더 많이 죽으면 녹색. 같은 행 `winner-cell`(`:83-88`)은 정확히 분류 — 모순.
- **영향:** 데스 행에서 더 많이 죽은 선수 Δ가 녹색(긍정). 사용자 혼란.
- **제안:** `row.higher_better` 템플릿에 노출, `is_good = (higher_better and d>0) or (not higher_better and d<0)`로 색 결정.

### ⚪-25 `[DIAG]` 진단 로그 + `print()` 잔류 (bot.py)
- **위치:** `bot.py:150-163, 169-171, 179-181, 190-192` (`[DIAG]`), `bot.py:231` (`print`)
- **증상:** "원인 파악 후 제거 예정" 주석과 함께 진단 로그가 매 메시지/서버 접속마다 INFO 출력. `print()`도 1곳.
- **영향:** 로그 노이즈, 서버 ID 등 메타데이터 과다 기록.
- **제안:** 진단 로그 제거 또는 DEBUG 강등. `print` → `log.warning`.

### ⚪-26 `team_insight`/`team_insights_data` 데드 코드 + i18n 드리프트
- **위치:** `analytics_insights.py:192-225`, `analytics.py:321-345` (+ i18n 키 `team_insights_*`)
- **증상:** 어디서도 import/호출 안 됨(grep 확인). AGENTS.md:93은 "coaching_hub 호환성 위해 잔존"이라 적혀 있으나 실제 의존 없음.
- **영향:** i18n 키 3개까지 3중 드리프트. AGENTS.md §8 경고와 정확히 같은 패턴.
- **제안:** 함수 + i18n 키 3개 + AGENTS.md 문구 함께 삭제.

### ⚪-27 `li` 미사용 변수 6곳
- **위치:** `analytics_insights.py:55, 89, 164, 201, 260, 301`
- **증상:** `li = _lang_instruction(lang)` 할당 후 사용 안 함. `trend_insight`(`:127`)만 사용.
- **제안:** 미사용 6개 라인 삭제.

### ⚪-28 `asyncio.get_event_loop()` deprecated (Python 3.10+)
- **위치:** `web_api.py:265, 281, 298, 325`
- **증상:** 러닝 루프 안에서 `get_event_loop()` 호출. 3.10부터 deprecation 경고.
- **제안:** `asyncio.get_running_loop()`로 교체.

### ⚪-29 N+1 쿼리 2건
- **위치:** `web_api.py:96-101` (허브 players_list — 선수마다 `get_player_id`), `db.py:547-581` (`list_unmatched_players` — 선수마다 COUNT 3회)
- **영향:** 현재 선수 6명이라 미미. 미매칭 선수 누적 시 `/unmatched` 지연.
- **제안:** 일괄 조회 / `LEFT JOIN ... GROUP BY` 통합.

### ⚪-30 기타 소소한 품질
- `db.py:203-205` `_adapt_params` no-op (docstring 거짓) — 구현 채우거나 제거
- `queries.py:1000-1003` `win_loss_summary` 재귀 호출 mode=None 시 커넥션 3개 오픈 — 단일 GROUP BY 쿼리로 통합
- `bot.py:77-78` OpenAI `temperature=0` + `top_p=0` 동시 설정 — `top_p` 제거
- `analytics.py:505` `coaching_hub` 타입 힌트 `recent_matches: int` 거짓(실제 `None` 허용) — `int | None`로 수정
- `web_api.py:587-588` `/admin/notes` `int()` 변환 예외 미처리 — try/except 또는 regex 제약
- `player_detail.html:138` 미정의 CSS 클래스 `.mode-toggle-group` — 정의 추가 또는 클래스명 제거
- `templates/admin_unmatched.html:28,38` 헤더-값 라벨 불일치 (헤더 "소스" / 값 alias 개수)
- `commands_cog.py` 슬래시 명령 핸들러 일반 예외 처리 부재 — `cog_app_command_error` 리스너 권장

---

## 긍정적 발견 (문제 없음)

- **ZCS 공식 정확** — `metrics.py:60` `1.1*obj + 8*ck + 4.1*k - 5*d` + `max(0,...)`. HP 전용 가드 정상. SND에 억지 적용 없음.
- **Impact/DPD/DPK/ID/AP% 공식** 모두 AGENTS.md와 일치.
- **`classify_role`** HP 전용으로 일관 (`web_api.py:113`, `queries.py:1148`, `prompt_context.py:143` 모드 가드).
- **`_adapt_sql`** 핵심 변환(`?`→`%s`, `MAX(0,x)`→`GREATEST`, `AVG()`→`::numeric`) 현재 쿼리셋에 대해 정상 동작 (인터프리터 검증).
- **라우트 오타/누락 없음** — 템플릿 18개가 참조하는 모든 URL이 `web_api.py`에 정의됨.
- **Jinja2 `{{ }}` 안 JS 연산자 충돌 없음** — 모든 `||`/`&&`가 순수 JS 컨텍스트 내.
- **미정의 CSS 토큰 참조 없음** — 세 템플릿의 `var(--*)`가 base.html `:root`에 모두 정의됨.
- **`flash()` 중복 정의 없음** (base.html:649 단일).

---

## 우선순위 권장

| 우선순위 | 항목 | 이유 |
|---|---|---|
| **P0 (즉시)** | 🟡-3 (비밀번호/SECRET_KEY), 🟡-4 (인사이트 API 인증) | 보안 — 외부 공격에 직결 |
| **P1 (다음)** | 🔴-1, 🔴-2 (`id` 키 함정), 🟡-8/9 (분자=0 가드 오류), 🟡-14 (동기 GPT 블록) | 데이터 정확성/가용성 — 사용자에게 직접 보이는 오작동 |
| **P2 (여유)** | 🟡-10~13, 🟡-15~20 | 잠재적 오작동, 디버깅 비용 |
| **P3 (정리)** | ⚪-21~30 | 품질 — 기능엔 영향 없으나 유지보수 부채 |

---

*감사 방식: 4개 병렬 서브에이전트(데이터층/분석층/API·봇/템플릿)가 독립 조사. 파일 수정 일절 없음. 모든 line 번호는 감사 시점 기준.*
