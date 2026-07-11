# P2 정확성·예외처리 수정 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 버그 감사 보고서의 P2(🟡) 항목 8건 중 정확성·예외처리·SQL 안전성 수정. UI 차트 품질(⚪)은 제외.

**Architecture:** 각 항목은 독립적 — 순서대로 적용하되, 한 항목이 끝날 때마다 검증 게이트 통과 후 다음으로. 모든 수정은 systematic-debugging 4단계(근인→패턴→가설→검증)를 적용한다.

**Tech Stack:** Python (FastAPI, discord.py), SQLite/Postgres 호환 SQL, Jinja2.

## Global Constraints
- DB는 환경변수 `DATABASE_URL` 있으면 Postgres, 없으면 SQLite. SQL은 양쪽 호환 (`_adapt_sql`이 `?`→`%s`, `MAX(0,x)`→`GREATEST` 변환).
- GPT 프롬프트(`prompt.py`)와 지표 공식(`metrics.py`)은 출처 고정. 단, 이 계획의 metrics.py 수정은 공식이 아니라 **가드 조건** 수정이므로 허용.
- 커스텀 지표 공식 자체 변경 금지 (ZCS/Impact/DPD/DPK/ID/AP%).
- 커밋은 각 태스크 단위.

---

### Task 1: 🟡-10 SND 리더보드 avg_dmg 라벨 드리프트 수정

**Files:**
- Modify: `queries.py:181-189` (SND metric 매핑)

**문제:** SND 모드에서 `leaderboard(metric="avg_dmg")`가 실제로는 `AVG(score)`를 반환. URL/라벨은 "딜량(avg_dmg)"인데 값은 점수. 사용자 오인.

**근인:** SND 테이블에 `total_damage` 컬럼이 없어 `score`로 폼백했으나, metric 키를 그대로 `avg_dmg`로 유지. HP와 SND가 같은 metric 문자열을 공유하지만 의미가 다름.

**패턴 분석:** HP의 `avg_dmg`는 진짜 딜량. SND는 딜량 데이터 자체가 없음. 따라서 SND에서 `avg_dmg`를 valid 집합에서 제외하고 폴백(`avg_kd`)시키는 게 정확. SND에서 딜량 순위는 애초에 불가능한 요청.

**Interfaces:**
- Consumes: `queries.leaderboard(mode, metric, limit)` — `web_api.py:182`, `commands_cog.py:295`에서 호출
- Produces: SND에서 `avg_dmg` 요청 시 `avg_kd`로 폴백 (사용자가 의도한 것과 다른 데이터를 조용히 보여주지 않음)

- [ ] **Step 1: SND valid 집합과 expr 매핑에서 avg_dmg 제거**

`queries.py:181-189` 수정:
```python
# 수정 전 (181-189):
if metric not in valid_snd:
    metric = "avg_kd"
expr = {
    "avg_kd": "AVG(kd_ratio)",
    "avg_k": "AVG(kills)",
    "avg_dmg": "AVG(score)",  # SND는 total_damage 없음 → score로 대체
    "avg_score": "AVG(score)",
    "avg_adr": "AVG(adr)",
}[metric]

# 수정 후:
if metric not in valid_snd:
    metric = "avg_kd"
expr = {
    "avg_kd": "AVG(kd_ratio)",
    "avg_k": "AVG(kills)",
    "avg_score": "AVG(score)",
    "avg_adr": "AVG(adr)",
}[metric]
```

`avg_dmg`를 expr 매핑에서 제거하면, SND에서 `metric="avg_dmg"`가 valid_snd에 있어도 `expr[metric]`이 `KeyError`. 따라서 valid_snd에서도 `avg_dmg`를 제거해야 폴백(`avg_kd`)이 작동.

- [ ] **Step 2: valid_snd 정의에서 avg_dmg 제거**

`queries.py`의 `valid_snd` 정의 찾아서 수정 (grep으로 위치 확인 필요 — 보통 160-163 부근):
```python
# 수정 전:
valid_snd = {"avg_kd", "avg_k", "avg_dmg", "avg_score", "avg_adr"}

# 수정 후:
valid_snd = {"avg_kd", "avg_k", "avg_score", "avg_adr"}
```

- [ ] **Step 3: leaderboard.html SND 옵션에서 avg_dmg 제거 확인**

`templates/leaderboard.html`의 `metric_opts_snd`를 확인:
```python
{% set metric_opts_snd = [('avg_kd', t.kd), ('avg_k', t.avg_k), ('avg_dmg', t.m_dmg), ('avg_score', t.avg_score), ('avg_adr', t.avg_impact)] %}
```
SND 옵션에 `avg_dmg`가 있으면 제거 (SND는 딜량 없음):
```python
{% set metric_opts_snd = [('avg_kd', t.kd), ('avg_k', t.avg_k), ('avg_score', t.avg_score), ('avg_adr', t.avg_impact)] %}
```

- [ ] **Step 4: 검증**

```bash
python -c "
import queries
# SND avg_dmg → 폴백으로 avg_kd 행 반환
rows = queries.leaderboard('SND', 'avg_dmg', 5)
print(f'SND avg_dmg fallback rows: {len(rows)}')
assert len(rows) > 0, 'FAIL: no rows'
# SND avg_kd 정상 작동
rows2 = queries.leaderboard('SND', 'avg_kd', 5)
assert len(rows2) > 0
print('PASS')
"
```
Expected: SND avg_dmg 요청이 에러 없이 avg_kd 결과 반환.

- [ ] **Step 5: Commit**

```bash
git add queries.py templates/leaderboard.html
git commit -m "fix: SND 리더보드 avg_dmg 라벨 드리프트 — score 폼백 제거, avg_kd로 폴백"
```

---

### Task 2: 🟡-11 player_trend 데스 delta 방향 처리

**Files:**
- Modify: `analytics.py:281-287`

**문제:** `delta["d_pct"]`가 데스 증가를 양수로 표시. 데스는 "낮을수록 좋음"이므로, GPT 트렌드 인사이트가 데스 증가를 "상승(긍정)"으로 오독할 수 있음.

**근인:** 데스 delta를 K/KD와 같은 부호 체계(양수=좋음)로 처리. lower-better 지표의 방향 반전 누락.

**패턴 분석:** 보고서의 3가지 제안 중 — ① 부호 반전은 GPT가 "음수=나쁨" 해석을 전제로 해서 혼란 유발. ② `lower_is_better` 플래그가 가장 명시적. ③ 프롬프트 명시는 GPT가 무시할 수 있어 불안정. **② 플래그 + 트렌드 GPT 데이터에 메타 정보 추가** 선택.

**Interfaces:**
- Consumes: `analytics.player_trend()` 반환 dict → `analytics_insights.trend_insight()` GPT 호출
- Produces: `delta` dict에 `lower_is_better` 메타 추가, `d_pct`는 원시 부호 유지(GPT가 메타로 판단)

- [ ] **Step 1: 데스 delta에 메타 플래그 추가**

`analytics.py:281-287` 수정:
```python
# 수정 전:
delta = {}
for key in ["kd", "k", "d"]:
    ov = overall[key] or 0
    if ov > 0:
        delta[key + "_pct"] = round((recent[key] - ov) / ov * 100, 1)
    else:
        delta[key + "_pct"] = 0

# 수정 후:
delta = {}
for key in ["kd", "k", "d"]:
    ov = overall[key] or 0
    if ov > 0:
        delta[key + "_pct"] = round((recent[key] - ov) / ov * 100, 1)
    else:
        delta[key + "_pct"] = 0
# 데스는 "낮을수록 좋음" — GPT 트렌드 인사이트가 방향을 오독하지 않도록 메타 명시.
# (d_pct > 0 = 데스 증가 = 나쁨. K/KD는 양수=좋음.)
delta["meta"] = {"d": "lower_is_better"}
```

- [ ] **Step 2: 검증**

```bash
python -c "
import analytics
trend = analytics.player_trend(1)
if trend and 'delta' in trend:
    d = trend['delta']
    assert 'meta' in d, 'FAIL: meta missing'
    assert d['meta'].get('d') == 'lower_is_better', 'FAIL: d not lower_is_better'
    print(f'delta keys: {sorted(d.keys())}')
    print('PASS')
else:
    print('SKIP: player 1 has no trend data')
"
```
Expected: `meta` 키 존재, `d: lower_is_better`.

- [ ] **Step 3: Commit**

```bash
git add analytics.py
git commit -m "fix: player_trend 데스 delta 방향 메타 추가 — GPT 트렌드 오독 방지"
```

---

### Task 3: 🟡-12/13 bot.py result 키 폴백 가드

**Files:**
- Modify: `bot.py:219`

**문제:** `players = result.get("players") or result.get("result", [])` — 구버전 호환 폴백. 신규 프롬프트는 `"result"`가 승패 문자열("WIN"). `players`가 빈 리스트이고 `result`가 문자열이면 `players`가 문자열에 바인딩 → `len(players)`가 문자열 길이, `for p in players`가 문자를 순회 → 데이터 손상.

**근인:** 구버전 프롬프트 호환용 폴백이 `result` 키의 의미 변경(선수 배열 → 승패 문자열)을 반영하지 못함.

**패턴 분석:** 구버전 폴백 제거가 가장 깔끔하나, 구버전 프롬프트 호환이 필요할 수 있음. 안전한 수정: `result.get("result", [])`에 `isinstance(..., list)` 가드 추가. 이렇게 하면 `result`가 문자열일 때 빈 리스트로 평가되어 `players`가 문자열에 바인딩되지 않음.

**Interfaces:**
- Consumes: GPT 비전 응답 dict (`result`)
- Produces: `players` 변수 — 항상 리스트 또는 빈 리스트

- [ ] **Step 1: result 폴백에 isinstance 가드 추가**

`bot.py:219` 수정:
```python
# 수정 전:
players = result.get("players") or result.get("result", [])

# 수정 후:
_result_raw = result.get("result", [])
players = result.get("players") or (_result_raw if isinstance(_result_raw, list) else [])
```

- [ ] **Step 2: 검증 (시나리오 단위)**

```bash
python -c "
# 시나리오 1: 정상 (players 채워짐)
r1 = {'players': [{'name': 'A'}], 'result': 'WIN'}
_rr1 = r1.get('result', [])
p1 = r1.get('players') or (_rr1 if isinstance(_rr1, list) else [])
assert p1 == [{'name': 'A'}], f'FAIL s1: {p1}'

# 시나리오 2: players 빈, result가 문자열 (버그 케이스)
r2 = {'players': [], 'result': 'WIN'}
_rr2 = r2.get('result', [])
p2 = r2.get('players') or (_rr2 if isinstance(_rr2, list) else [])
assert p2 == [], f'FAIL s2: {p2} (should be [], not WIN)'

# 시나리오 3: 구버전 호환 (result가 리스트)
r3 = {'result': [{'name': 'B'}]}
_rr3 = r3.get('result', [])
p3 = r3.get('players') or (_rr3 if isinstance(_rr3, list) else [])
assert p3 == [{'name': 'B'}], f'FAIL s3: {p3}'

print('ALL 3 SCENARIOS PASS')
"
```
Expected: 시나리오 2에서 `p2 == []` (문자열 "WIN"이 아님).

- [ ] **Step 3: Commit**

```bash
git add bot.py
git commit -m "fix: bot.py result 키 폴백 가드 — 승패 문자열을 선수 리스트로 오인 방지"
```

---

### Task 4: 🟡-15 GPT 인사이트 함수 7곳 예외 삼킴 → 로깅 추가

**Files:**
- Modify: `analytics_insights.py:75-76, 109-110, 145-146, 188-189, 224-225, 287-288, 346-347`

**문제:** 7개 GPT 인사이트 함수가 `except Exception: return ""` — API 타임아웃/키 오류/직렬화 실패를 빈 문자열로 변환, 스택트레이스 없음. 원인 진단 불가. `briefing_insight`(`:411-414`)만 `as e` + traceback 패턴.

**근인:** 예외 처리의 단순화. `briefing_insight`만 나중에 추가되면서 로깅 패턴이 도입됨.

**패턴 분석:** `briefing_insight`의 패턴이 정답:
```python
except Exception as e:
    import traceback
    print(f"[함수명] ERROR: {e}\n{traceback.format_exc()}", flush=True)
    return ""
```
각 함수마다 `[함수명]`으로 식별 가능하게. `replace_all` 불가(각각 다른 줄) — 함수명을 매칭해서 7개 개별 수정.

**Interfaces:**
- Consumes: 없음 (내부 예외 처리)
- Produces: 콘솔 로그에 스택트레이스 출력 (기존 반환값 `""` 유지)

- [ ] **Step 1: 각 except 블록의 함수명 파악**

7개 라인이 속한 함수명 (grep으로 확인):
- `:75` → 함수명 확인 필요 (아마 `match_insight`)
- `:109` → `weekly_insight`
- `:145` → `player_profile_insight`
- `:188` → (확인 필요)
- `:224` → (확인 필요)
- `:287` → (확인 필요)
- `:346` → (확인 필요)

실행 시 grep으로 정확한 함수명 추출:
```bash
grep -n "^def \|^    except Exception" analytics_insights.py
```

- [ ] **Step 2: 각 except 블록을 briefing_insight 패턴으로 수정**

각 7개 라인을 개별적으로 수정 (함수명 포함):
```python
# 수정 전 (각 7곳):
    except Exception:
        return ""

# 수정 후 (예시 — match_insight):
    except Exception as e:
        import traceback
        print(f"[match_insight] ERROR: {e}\n{traceback.format_exc()}", flush=True)
        return ""
```
함수명은 Step 1에서 확인한 이름 사용.

- [ ] **Step 3: 검증**

```bash
python -c "
import analytics_insights
# 모든 함수 import 가능한지 (구문 에러 없는지)
funcs = ['match_insight', 'weekly_insight', 'player_profile_insight']
for f in funcs:
    assert hasattr(analytics_insights, f), f'FAIL: {f} not found'
print('import + function presence: OK')
"
# except 라인 수 확인 (as e 없는 except Exception이 0개여야)
grep -c 'except Exception:' analytics_insights.py
# 예상: 0 (모두 as e로 변환됨)
```
Expected: `except Exception:` (as e 없는) 개수 = 0.

- [ ] **Step 4: Commit**

```bash
git add analytics_insights.py
git commit -m "fix: 7개 GPT 인사이트 함수 예외 삼킴 해제 — 스택트레이스 로깅 추가"
```

---

### Task 5: 🟡-16 GPT 비전 API 타임아웃 추가

**Files:**
- Modify: `bot.py:75-106` (`analyze_images` 함수)

**문제:** `openai_client.chat.completions.create(...)`에 `timeout=` 미지정. OpenAI 기본값(600s)에 의존. API 지연 시 봇이 후속 스크린샷 처리 불가.

**근인:** 타임아웃 파라미터 누락.

**패턴 분석:** AGENTS.md §3에 따라 로컬 검증 불가(OpenAI 키 필요). 안전한 수정 — `timeout=60` 추가만. config.py에 타임아웃 상수가 있는지 확인.

**Interfaces:**
- Consumes: `openai_client` (모듈 레벨)
- Produces: 60초 후 타임아웃 예외 → 기존 `except Exception` 블록이 잡아서 사용자에게 에러 메시지

- [ ] **Step 1: config.py에 타임아웃 상수 확인**

```bash
grep -n "timeout\|TIMEOUT\|OPENAI" config.py
```
상수가 있으면 사용, 없으면 직접 `timeout=60` 명시.

- [ ] **Step 2: create 호출에 timeout 추가**

`bot.py`의 `openai_client.chat.completions.create(...)` 호출 찾아서 `timeout=60` 파라미터 추가. (정확한 줄은 grep으로 확인 — 보통 75-78 부근)

- [ ] **Step 3: 검증 (import 레벨)**

```bash
python -c "import bot; print('bot import OK')"
```
Expected: import 성공 (타임아웃 값이 구문적으로 유효한지).

- [ ] **Step 4: Commit**

```bash
git add bot.py
git commit -m "fix: GPT 비전 API 타임아웃 60초 추가 — 봇 블록 방지"
```

---

### Task 6: 🟡-17 db.py 예외 삼킴 3곳 → 로깅/재발생

**Files:**
- Modify: `db.py:357-358` (`_has_column`), `db.py:456-457` (`_learn_alias`), `db.py:487-488` (`add_alias`)

**문제:** 3곳이 `except Exception: pass` 또는 `return False`. UNIQUE 충돌 외에 connection 오류, 문법 오류, NOT NULL 위반을 전부 조용히 무시.

**근인:** 예외 광범위 삼킴. `_learn_alias`의 주석("UNIQUE 충돌 등")이 의도를 보이나, 구현은 모든 예외를 삼킴.

**패턴 분석:** 각 위치별 차별화:
- `_learn_alias`: UNIQUE 충돌은 정상(이미 학습됨). 다른 예외는 로깅 후 삼킴(재발생 시 봇 크래치 위험 — alias 학습은 부수 기능). **로깅만 추가, 삼킴 유지** (부수 기능이라 크래시보단 삼킴이 안전).
- `_has_column`: 스키마 확인 유틸. False 폴백은 안전(있는 컬럼을 없다고 해도 무해). **로깅만 추가**.
- `add_alias`: 수동 alias 등록. 이미 충돌 메시지를 반환하므로, 다른 예외도 사용자에게 전달되어야. **로깅 추가 + 에러 메시지 구체화**.

**Interfaces:**
- Consumes: 없음 (내부 예외 처리)
- Produces: 콘솔 로그에 예외 출력 (기존 반환값/동작 유지)

- [ ] **Step 1: _learn_alias 로깅 추가**

`db.py:456-457` 수정:
```python
# 수정 전:
    except Exception:
        pass  # UNIQUE 충돌 등 — 이미 학습됐거나 다른 선수에게 할당됨

# 수정 후:
    except Exception as e:
        log.warning(f"[_learn_alias] {ign} → player_id={player_id} 학습 실패: {e}")
        # UNIQUE 충돌 등 — 이미 학습됐거나 다른 선수에게 할당됨. 부수 기능이라 삼킴.
```
(모듈에 `log` 로거가 있는지 확인 — `grep -n "^log\|^import logging\|getLogger" db.py`)

- [ ] **Step 2: _has_column 로깅 추가**

`db.py:357-358` 수정:
```python
# 수정 전:
        except Exception:
            return False

# 수정 후:
        except Exception as e:
            log.warning(f"[_has_column] {table}.{column} 확인 실패: {e}")
            return False
```

- [ ] **Step 3: add_alias 에러 메시지 구체화**

`db.py:487-488` 수정:
```python
# 수정 전:
        except Exception:
            return {"ok": False, "message": f"`{ign}` alias 등록 중 충돌 (이미 존재할 수 있음)"}

# 수정 후:
        except Exception as e:
            log.warning(f"[add_alias] {ign} → {player_name} 등록 실패: {e}")
            return {"ok": False, "message": f"`{ign}` alias 등록 중 충돌 (이미 존재하거나 DB 오류): {e}"}
```

- [ ] **Step 4: 검증**

```bash
python -c "import db; print('db import OK')"
```
Expected: import 성공 (로거 변수명 유효).

- [ ] **Step 5: Commit**

```bash
git add db.py
git commit -m "fix: db.py 3곳 예외 삼킴 — 로깅 추가 (UNIQUE 외 에러 가시화)"
```

---

### Task 7: 🟡-18 recent_ids 서브쿼리 mode 화이트리스트 강화

**Files:**
- Modify: `queries.py:688-728` (`map_team_stats_recent`), `queries.py:740-760` (`team_trend_by_matches`), 날짜 보간 `:618-620, :868-871`

**문제:** `f"SELECT id FROM matches WHERE mode='{mode}' ORDER BY id DESC LIMIT {int(recent_matches)}"` — `mode`를 f-string으로 직접 삽입. `recent_matches`/`days`는 `int()` 캐스트로 보호되나, `mode`는 함수 인자라 검증 누락 시 인젝션 벡터.

**근인:** `IN (서브쿼리)` 안의 `mode='{mode}'`를 placeholder로 바꾸면 중첩 placeholder 문제. 현재는 화이트리스트("HP"/"SND") 호출처만 쓰여서 안전하지만, 방어막 부재.

**패턴 분석:** 서브쿼리 안의 placeholder는 SQLite/Postgres 양쪽에서 복잡(서브쿼리의 파라미터가 외부 execute의 params에 추가되어야). 더 단순하고 안전한 수정: **함수 진입점에서 `mode`를 화이트리스트로 강제 검증**. 이중 안전장치 — 이미 호출처가 안전하더라도, 함수 자체가 방어. 날짜 `int()` 캐스트는 이미 안전하므로 유지.

**Interfaces:**
- Consumes: `mode` 파라미터 (호출처: `web_api.py`, `analytics.py`)
- Produces: `mode`가 "HP"/"SND" 외 값이면 `ValueError` (또는 "HP" 폴백)

- [ ] **Step 1: map_team_stats_recent 진입점 mode 검증 추가**

`queries.py:692` (함수 시작부) 수정:
```python
# 수정 전 (692-696):
    if recent_matches is None:
        return map_team_stats(mode, min_matches)
    if recent_matches <= 0:
        recent_matches = 10

# 수정 후:
    if recent_matches is None:
        return map_team_stats(mode, min_matches)
    # mode 화이트리스트 강제 — recent_ids 서브쿼리에 문자열 보간되므로 인젝션 방어.
    if mode not in ("HP", "SND"):
        raise ValueError(f"map_team_stats_recent: invalid mode={mode!r}")
    if recent_matches <= 0:
        recent_matches = 10
```

- [ ] **Step 2: team_trend_by_matches 진입점 mode 검증 추가**

`queries.py`의 `team_trend_by_matches` 함수 시작부에 동일 검증 추가 (grep으로 위치 확인).

- [ ] **Step 3: 날짜 보간 함수들 mode 검증 확인**

`:618-620, :868-871`의 `team_trend`/`map_trend` — 이들은 이미 `mode` 기반 분기(`if mode == "HP"`)를 가지므로, 잘못된 mode는 빈 결과로 떨어짐. 추가 검증 불필요 (이미 안전).

- [ ] **Step 4: 검증**

```bash
python -c "
import queries
# 정상 mode 작동
try:
    queries.map_team_stats_recent('HP', 10)
    print('HP mode: OK')
except Exception as e:
    print(f'FAIL HP: {e}')
# 비정상 mode 차단
try:
    queries.map_team_stats_recent(\"HP' OR '1'='1\", 10)
    print('FAIL: injection not blocked')
except ValueError:
    print('injection blocked: OK')
"
```
Expected: HP mode OK, 인젝션 문자열은 ValueError.

- [ ] **Step 5: Commit**

```bash
git add queries.py
git commit -m "fix: recent_ids 서브쿼리 mode 화이트리스트 강제 — 인젝션 방어"
```

---

### Task 8: 🟡-19/20 match_history_grouped ORDER BY 일관성 + 데드 조건 정리

**Files:**
- Modify: `queries.py:548` (ORDER BY 표현식), `queries.py:576-589` (그룹핑 데드 조건)

**문제 1 (🟡-19):** 두 번째 SELECT의 `ORDER BY (m.match_date IS NULL)`이 SELECT 리스트에 없음. 첫 쿼리(`:521-523`)는 SELECT 리스트에 포함(AGENTS.md 권장). 현재는 일반 SELECT라 작동하나, DISTINCT/집계 리팩터링 시 에러.

**문제 2 (🟡-20):** 날짜 그룹핑 루프의 복잡한 조건식(`:578`)이 None 그룹에서는 데드 코드(`:580-581`가 항상 이김). 가독성 저하, 유지보수 위험.

**근인 1:** 두 쿼리 간 패턴 불일치.
**근인 2:** None 그룹 특수처리를 명시적 분기로 안 빼고 복잡한 조건식으로 처리.

**패턴 분석:**
- 19: 첫 쿼리 패턴(`(match_date IS NULL) is_null` SELECT 포함)에 맞춤.
- 20: `if d is None: ... else: ...` 명시 분기로 단순화.

**Interfaces:**
- Consumes: 없음 (내부 쿼리/로직)
- Produces: 동일 결과, 더 안전한 SQL 패턴 + 가독성

- [ ] **Step 1: ORDER BY 표현식 SELECT 리스트 추가**

`queries.py:548` 부근의 두 번째 SELECT — SELECT 절에 `(m.match_date IS NULL) is_null` 추가, ORDER BY는 `is_null` 참조:
```sql
-- 수정 전:
ORDER BY (m.match_date IS NULL), m.match_date DESC, m.id DESC

-- 수정 후 (SELECT 절에 추가):
SELECT ..., (m.match_date IS NULL) is_null  -- 기존 컬럼들 뒤에 추가
...
ORDER BY is_null, m.match_date DESC, m.id DESC
```
정확한 SELECT 절은 Read로 확인 후 수정.

- [ ] **Step 2: 그룹핑 데드 조건 명시적 분기로 정리**

`queries.py:576-589` 수정:
```python
# 수정 전:
groups = []
for d in page_dates:
    grp_matches = [m for m in matches if m["match_date"] == d and not (d is None and m["match_date"] is not None)]
    # None 그룹은 match_date IS NULL인 행만
    if d is None:
        grp_matches = [m for m in matches if m["match_date"] is None]
    if grp_matches:
        ...

# 수정 후:
groups = []
for d in page_dates:
    if d is None:
        grp_matches = [m for m in matches if m["match_date"] is None]
    else:
        grp_matches = [m for m in matches if m["match_date"] == d]
    if grp_matches:
        ...
```

- [ ] **Step 3: 검증 (실제 호출)**

```bash
python -c "
import queries
# match_history_grouped 정상 호출
result = queries.match_history_grouped()
print(f'groups: {len(result)}')
assert len(result) > 0, 'FAIL: no groups'
# None 날짜 그룹이 있으면 확인
none_groups = [g for g in result if g.get('date') is None]
print(f'None-date groups: {len(none_groups)}')
# 날짜 있는 그룹과 없는 그룹이 중복 없이 분리되었는지
all_m = sum(len(g['matches']) for g in result)
print(f'total matches across groups: {all_m}')
print('PASS')
"
```
Expected: 그룹 정상 반환, None/비-None 분리 정상.

- [ ] **Step 4: Commit**

```bash
git add queries.py
git commit -m "refactor: match_history_grouped ORDER BY 일관성 + 그룹핑 명시 분기"
```

---

## Self-Review (작성자 자체 점검)

**1. Spec coverage:** 보고서 P2 항목 8건(🟡-10,11,12/13,15,16,17,18,19/20) 각각 대응 태스크 존재. 🟡-14는 P1에서 이미 수정. ✅

**2. Placeholder scan:**
- 각 Step의 코드는 실제 파일 내용 기반 (조사 완료).
- "확인 필요" 부분(함수명 등)은 grep 명령으로 해결 — placeholder 아님, 실행 시점 확인 사항.
- ✅

**3. Type consistency:**
- `delta["meta"] = {"d": "lower_is_better"}` — dict 타입. GPT 프롬프트에서 dict를 처리할 수 있는지는 trend_insight 구현에 의존. 부작용 가능성 메모.
- `players` 폴백 — `_result_raw` 임시 변수 도입. 기존 변수명과 충돌 없음.
- ✅

**리스크 메모:**
- Task 4 (예외 삼킴): 7개 함수 각각 수정이라 라인 번호가 어긋날 수 있음 — grep으로 실시간 확인 필수.
- Task 7 (mode 검증): `team_trend_by_matches`의 정확한 함수명/시그니처 확인 필요.
- Task 8 (ORDER BY): SELECT 절 수정 시 기존 컬럼 순서/이름 정확히 파악 필요.
