# RDS (Round Domination Score) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SND 모드에 ZCS와 대칭되는 종합 커스텀 지표 RDS를 도입하여, 모든 SND 컨텍스트(선수표, 상세, 리더보드, 비교, 맵, 매치)에 노출한다.

**Architecture:** ZCS 처리 패턴(3계층: `metrics.py` 함수 + `queries.py` 헬퍼/SQL 인라인 + 템플릿 마크업)을 그대로 복제. `_adapt_sql`의 `MAX(0,...)`→`GREATEST` 변환 재사용으로 Postgres 호환 자동 확보. 단일 선형 공식 `RDS = max(0, 4.1·K + 3.5·A + 14·FK + 20·LWW + 0.12·ADR − 5·D)`.

**Tech Stack:** Python (FastAPI), Jinja2 templates, SQLite/Postgres (dual), i18n (3-lang).

**Spec:** `docs/superpowers/specs/2026-07-11-snd-rds-metric-design.md`

## Global Constraints

- RDS 공식 (절대 변경 금지, 출처 고정): `max(0, 4.1·K + 3.5·A + 14·FK + 20·LWW + 0.12·ADR − 5·D)`.
- SQL 인라인: `MAX(0, 4.1*kills + 3.5*assists + 14*first_kill + 20*lone_wolf_win + 0.12*adr - 5*deaths)` — `_adapt_sql`이 Postgres용 `GREATEST(0, ...)`로 자동 변환.
- `metrics.py`의 GPT 프롬프트(`prompt.py`)와 커스텀 지표 공식(`metrics.py`)은 출처가 정해져 있어 **함부로 수정 금지** (새 함수 추가만).
- 인라인 스타일 금지 — 클래스 기반. SND 색 토큰: `--snd`/`--snd-weak`, 카드 변형 `.card--snd`, 강조 `.text-snd`.
- i18n 키 추가 시 3개국어(`_ko.py`/`_en.py`/`_es.py`) 동일 키 강제 — `pytest test_i18n.py` 검증 필수.
- ZCS가 HP 컨텍스트에 나오는 모든 곳의 SND 대응점에 RDS를 깐다 (완전 대칭 원칙).

---

### Task 1: metrics.py — compute_rds + all_snd_metrics 함수 추가

**Files:**
- Modify: `metrics.py:63` (compute_zcs 이후, all_hp_metrics 이전)

**Interfaces:**
- Produces: `compute_rds(kills, assists, first_kill, lone_wolf_win, adr, deaths) -> float|None`
- Produces: `all_snd_metrics(kills, assists, first_kill, lone_wolf_win, adr, deaths) -> dict` (키: `{"rds"}`)

- [ ] **Step 1: compute_rds 함수 추가 (compute_zcs 닫는 `}` 이후)**

`metrics.py`의 `compute_zcs` 함수 끝(`return round(max(0, val), 2)` 다음 줄, `def all_hp_metrics` 이전)에 추가:

```python
def compute_rds(kills, assists, first_kill, lone_wolf_win, adr, deaths) -> float:
    """Round Domination Score = max(0, 4.1·K + 3.5·A + 14·FK + 20·LWW + 0.12·ADR − 5·D).

    SND 전용 제1 지표 — ZCS와 대칭. 라운드 장악력(오프닝·듀얼·클러치 종합).
    ⚠️ SND 전용 — HP 데이터로 호출 금지.
    가중치는 경험적 매그니튜드 (승패 데이터 충분 시 로지스틱 회귀로 재튜닝 TODO).
    """
    if any(v is None for v in (kills, assists, first_kill, lone_wolf_win, adr, deaths)):
        return None
    val = (4.1 * kills + 3.5 * assists + 14 * first_kill
           + 20 * lone_wolf_win + 0.12 * adr - 5 * deaths)
    return round(max(0, val), 2)
```

- [ ] **Step 2: all_snd_metrics 헬퍼 추가 (all_hp_metrics 함수 이후, classify_role 이전)**

`metrics.py`의 `all_hp_metrics` 함수 끝(`return {...}` 다음, `# ── 역할(Role) 분류` 주석 이전)에 추가:

```python
def all_snd_metrics(kills, assists, first_kill, lone_wolf_win, adr, deaths) -> dict:
    """SND 매치 한 선수분의 커스텀 지표를 한 번에 계산.

    ⚠️ SND 전용 — HP 스탯으로 호출하지 말 것.
    현재는 RDS만 포함 (향후 SND 보조 지표 추가 시 여기에 확장).
    """
    return {
        "rds": compute_rds(kills, assists, first_kill, lone_wolf_win, adr, deaths),
    }
```

- [ ] **Step 3: 데이터 대입 검증 (현재 선수 평균으로 RDS 계산)**

실행:
```bash
cd "C:\Users\0616y\Downloads\Team management app" && python -c "
import metrics
# 스펙 검증값: Maozyn K12.5 D6.7 A1.2 FK2.33 LWW0.17 ADR109 → RDS ~71
r = metrics.compute_rds(12.5, 1.2, 2.33, 0.17, 109, 6.7)
print('Maozyn RDS:', r, '(예상 ~71)')
assert 70 <= r <= 72, f'RDS 범위 이상: {r}'
# Cartels K9.8 D8.5 A1.7 FK2.0 LWW0 ADR82 → RDS ~41.5
r2 = metrics.compute_rds(9.8, 1.7, 2.0, 0, 82, 8.5)
print('Cartels RDS:', r2, '(예상 ~41.5)')
assert 40 <= r2 <= 43, f'RDS 범위 이상: {r2}'
# None 처리 검증
assert metrics.compute_rds(None, 1, 1, 1, 100, 5) is None
print('all_snd_metrics:', metrics.all_snd_metrics(12.5, 1.2, 2.33, 0.17, 109, 6.7))
print('OK')
"
```
Expected: `Maozyn RDS: 71.xx`, `Cartels RDS: 41.xx`, `OK`

- [ ] **Step 4: 커밋**

```bash
git add metrics.py
git commit -m "feat: SND 제1 지표 RDS — metrics.py 함수 추가

compute_rds(k,a,fk,lww,adr,d) + all_snd_metrics() 헬퍼.
공식: max(0, 4.1·K + 3.5·A + 14·FK + 20·LWW + 0.12·ADR − 5·D)
ZCS(compute_zcs)와 대칭되는 SND 종합 지표."
```

---

### Task 2: queries.py — player_overall_stats SND에 RDS 추가

**Files:**
- Modify: `queries.py:110-120` (SND 평균 계산 후 RDS 추가 블록)

**Interfaces:**
- Consumes: `metrics.all_snd_metrics(kills, assists, first_kill, lone_wolf_win, adr, deaths)` (Task 1)
- Produces: `result["snd"]["rds"]` — player_overall_stats 반환값 SND 블록에 rds 키 추가

- [ ] **Step 1: SND 커스텀 지표(RDS) 계산 블록 추가**

`queries.py`의 `player_overall_stats` 함수에서, HP 커스텀 지표 계산 블록(`h["zcs"] = m["zcs"]` 등) 이후, `return result` 이전에 SND 블록 추가. 현재 120줄 부근:

```python
    # SND 커스텀 지표(RDS) 계산 추가
    if result["snd"]:
        s = result["snd"]
        m = metrics.all_snd_metrics(
            s["avg_k"], s["avg_a"], s["avg_fk"], s["avg_lww"],
            s["avg_adr"], s["avg_d"],
        )
        s["rds"] = m["rds"]

    return result
```

참고: `result["snd"]`는 이미 105-106줄에서 `avg_fk`/`avg_lww`를 `ROUND(AVG(first_kill),2)`/`ROUND(AVG(lone_wolf_win),2)`로 계산하고 있음.

- [ ] **Step 2: 검증 — player_overall_stats SND에 rds 키 확인**

실행:
```bash
cd "C:\Users\0616y\Downloads\Team management app" && python -c "
import queries
# Maozyn (FK 폭발 선수) — SND RDS 있어야 함
pid = queries.get_player_id('Maozyn')
stats = queries.player_overall_stats(pid)
print('SND rds:', stats['snd'].get('rds') if stats['snd'] else None)
assert stats['snd'] and stats['snd'].get('rds') is not None, 'rds 없음'
# HP 블록엔 rds 없어야 함 (ZCS만)
assert 'rds' not in (stats['hp'] or {}), 'HP에 rds 섞임'
print('OK')
"
```
Expected: `SND rds: 70.x ~ 71.x`, `OK`

- [ ] **Step 3: 커밋**

```bash
git add queries.py
git commit -m "feat: player_overall_stats SND 블록에 RDS 계산 추가"
```

---

### Task 3: queries.py — all_players_overview SND에 RDS 추가

**Files:**
- Modify: `queries.py:353-383` (SND 쿼리 + 커스텀 지표 계산)

**Interfaces:**
- Consumes: `metrics.all_snd_metrics(...)` (Task 1)
- Produces: SND 모드 `all_players_overview` 반환값에 `avg_fk`, `avg_lww`, `rds` 키 추가

- [ ] **Step 1: SND 쿼리에 first_kill/lone_wolf_win 컬럼 추가**

`queries.py`의 `all_players_overview` 함수, SND 분기(`else:` 블록, 353-364줄)의 SQL에 `first_kill`/`lone_wolf_win` AVG 추가. 현재:

```python
    else:
        sql = """SELECT p.id, p.name,
                        COUNT(*) matches,
                        ROUND(AVG(s.kills),1) avg_k,
                        ROUND(AVG(s.deaths),1) avg_d,
                        ROUND(AVG(s.assists),1) avg_a,
                        ROUND(AVG(s.kd_ratio),2) avg_kd,
                        ROUND(AVG(s.score),0) avg_score,
                        ROUND(AVG(s.adr),0) avg_adr,
                        ROUND(AVG(s.impact),0) avg_impact
                 FROM player_stats_snd s JOIN players p ON p.id=s.player_id
                 GROUP BY p.id ORDER BY avg_kd DESC"""
```

변경 후:

```python
    else:
        sql = """SELECT p.id, p.name,
                        COUNT(*) matches,
                        ROUND(AVG(s.kills),1) avg_k,
                        ROUND(AVG(s.deaths),1) avg_d,
                        ROUND(AVG(s.assists),1) avg_a,
                        ROUND(AVG(s.kd_ratio),2) avg_kd,
                        ROUND(AVG(s.score),0) avg_score,
                        ROUND(AVG(s.adr),0) avg_adr,
                        ROUND(AVG(s.impact),0) avg_impact,
                        ROUND(AVG(s.first_kill),2) avg_fk,
                        ROUND(AVG(s.lone_wolf_win),2) avg_lww
                 FROM player_stats_snd s JOIN players p ON p.id=s.player_id
                 GROUP BY p.id ORDER BY avg_kd DESC"""
```

- [ ] **Step 2: SND 커스텀 지표(RDS) 계산 블록 추가**

같은 함수에서 HP 커스텀 지표 계산 블록(`if mode == "HP":` 375-382줄) 이후, `return rows` 이전에 SND 블록 추가:

```python
    # SND는 커스텀 지표(RDS)를 평균 raw 값으로부터 계산해 추가
    if mode == "SND":
        for p in rows:
            m = metrics.all_snd_metrics(
                p["avg_k"], p["avg_a"], p["avg_fk"], p["avg_lww"],
                p["avg_adr"], p["avg_d"],
            )
            p.update(m)
    return rows
```

- [ ] **Step 3: 검증**

실행:
```bash
cd "C:\Users\0616y\Downloads\Team management app" && python -c "
import queries
players = queries.all_players_overview('SND')
assert players, 'SND 선수 없음'
p0 = players[0]
print('keys:', sorted([k for k in p0.keys() if 'rds' in k or 'fk' in k or 'lww' in k]))
assert 'rds' in p0, 'rds 키 없음'
assert 'avg_fk' in p0 and 'avg_lww' in p0, 'fk/lww 없음'
# HP 모드엔 rds 없어야 함
hp = queries.all_players_overview('HP')
assert hp and 'rds' not in hp[0], 'HP에 rds 섞임'
print('OK — SND RDS:', [f\"{p['name']}:{p['rds']}\" for p in players[:3]])
"
```
Expected: `keys: ['avg_fk', 'avg_lww', 'rds']`, `OK — SND RDS: ['Maozyn:7x.x', ...]`

- [ ] **Step 4: 커밋**

```bash
git add queries.py
git commit -m "feat: all_players_overview SND에 RDS + avg_fk/avg_lww 추가"
```

---

### Task 4: queries.py — leaderboard SND에 rds 메트릭 추가

**Files:**
- Modify: `queries.py:157-197` (leaderboard 함수 SND 분기)
- Modify: `queries.py:386-401` (advanced_leaderboard 함수 — SND rds 지원)
- Modify: `web_api.py:188` (custom_metrics 집합에 rds 추가)

**Interfaces:**
- Produces: `leaderboard("SND", "rds")` 및 `advanced_leaderboard("rds")` 동작
- Produces: `valid_snd` 집합에 `"rds"` 추가

- [ ] **Step 1: leaderboard 함수 SND에 rds 메트릭 추가**

`queries.py`의 `leaderboard` 함수 (157-197줄). SND 분기의 `valid_snd`와 `expr` 딕셔너리 수정.

현재 (163줄):
```python
    valid_snd = {"avg_kd", "avg_k", "avg_score", "avg_adr"}
```
변경 후:
```python
    valid_snd = {"avg_kd", "avg_k", "avg_score", "avg_adr", "rds"}
```

현재 SND expr 딕셔너리 (186-191줄):
```python
        expr = {
            "avg_kd": "AVG(kd_ratio)",
            "avg_k": "AVG(kills)",
            "avg_score": "AVG(score)",
            "avg_adr": "AVG(adr)",
        }[metric]
```
변경 후 (rds는 인라인 공식):
```python
        expr = {
            "avg_kd": "AVG(kd_ratio)",
            "avg_k": "AVG(kills)",
            "avg_score": "AVG(score)",
            "avg_adr": "AVG(adr)",
            "rds": "MAX(0, 4.1*kills + 3.5*assists + 14*first_kill + 20*lone_wolf_win + 0.12*adr - 5*deaths)",
        }[metric]
```

- [ ] **Step 2: advanced_leaderboard 함수 — SND rds 지원**

`queries.py`의 `advanced_leaderboard` (386-401줄). 현재 HP 전용(`metric in {"dpd","dpk","impact_delta","ap_pct","zcs"}`).

현재:
```python
def advanced_leaderboard(metric: str = "dpd", limit: int = 20) -> list:
    """HP 커스텀 지표 기준 리더보드. metric: dpd/dpk/impact_delta/ap_pct/zcs.

    반환: [{name, matches, value}, ...] (내림차순)
    """
    players = all_players_overview("HP")
    if metric not in {"dpd", "dpk", "impact_delta", "ap_pct", "zcs"}:
        metric = "dpd"
    # 값이 있는 선수만, 해당 지표 기준 정렬
    ranked = [
        {"name": p["name"], "matches": p["matches"], "value": p.get(metric)}
        for p in players
    if p.get(metric) is not None
    ]
    # DPK는 낮을수록 좋음(적은 딜로 킬) → 오름차순. 나머지는 높을수록 좋음 → 내림차순.
    reverse = (metric != "dpk")
    ranked.sort(key=lambda x: x["value"], reverse=reverse)
    return ranked[:limit]
```

변경 후 (rds → SND, 나머지 → HP):
```python
def advanced_leaderboard(metric: str = "dpd", limit: int = 20) -> list:
    """커스텀 지표 기준 리더보드. metric: dpd/dpk/impact_delta/ap_pct/zcs(HP), rds(SND).

    반환: [{name, matches, value}, ...] (rds는 내림차순, dpk는 오름차순)
    """
    # rds는 SND, 나머지는 HP
    if metric == "rds":
        players = all_players_overview("SND")
    else:
        players = all_players_overview("HP")
        if metric not in {"dpd", "dpk", "impact_delta", "ap_pct", "zcs"}:
            metric = "dpd"
    # 값이 있는 선수만, 해당 지표 기준 정렬
    ranked = [
        {"name": p["name"], "matches": p["matches"], "value": p.get(metric)}
        for p in players
        if p.get(metric) is not None
    ]
    # DPK는 낮을수록 좋음(적은 딜로 킬) → 오름차순. 나머지는 높을수록 좋음 → 내림차순.
    reverse = (metric != "dpk")
    ranked.sort(key=lambda x: x["value"], reverse=reverse)
    return ranked[:limit]
```

- [ ] **Step 3: web_api.py — custom_metrics 집합에 rds 추가**

`web_api.py`의 `leaderboard_page` (188줄). 현재:
```python
    custom_metrics = {"dpd", "dpk", "impact_delta", "ap_pct", "zcs"}
```
변경 후:
```python
    custom_metrics = {"dpd", "dpk", "impact_delta", "ap_pct", "zcs", "rds"}
```

- [ ] **Step 4: 검증**

실행:
```bash
cd "C:\Users\0616y\Downloads\Team management app" && python -c "
import queries
# advanced_leaderboard rds
rows = queries.advanced_leaderboard('rds', 20)
print('RDS 리더보드:', [(r['name'], r['value']) for r in rows[:3]])
assert rows, 'rds 리더보드 비어있음'
assert all(r['value'] is not None for r in rows)
# leaderboard SND rds (SQL 인라인)
rows2 = queries.leaderboard('SND', 'rds', 20)
print('leaderboard SND rds:', [(r['name'], r['value']) for r in rows2[:3]])
assert rows2, 'leaderboard SND rds 비어있음'
print('OK')
"
```
Expected: 두 쿼리 모두 선수+값 반환, Maozyn이 1위 근처.

- [ ] **Step 5: 커밋**

```bash
git add queries.py web_api.py
git commit -m "feat: 리더보드 SND에 RDS 메트릭 추가 (leaderboard + advanced)"
```

---

### Task 5: queries.py — player_metric_timeseries SND에 RDS 추가

**Files:**
- Modify: `queries.py:403-456` (player_metric_timeseries 함수)

**Interfaces:**
- Produces: SND timeseries 반환값에 `rds` 키 추가 (선수 상세 차트용)

- [ ] **Step 1: SND timeseries에 RDS 계산 추가**

`queries.py`의 `player_metric_timeseries` 함수 (403-456줄). HP 분기 후, `rows.reverse()` 이후, `return rows` 이전에 SND 분기 추가.

현재 (452-456줄):
```python
    # 시간순(과거→최신)으로 뒤집기 + HP는 커스텀 지표 계산 추가
    rows.reverse()
    if mode == "HP":
        for r in rows:
            m = metrics.all_hp_metrics(
                r.get("kills"), r.get("deaths"), r.get("obj"),
                r.get("score"), r.get("impact"), r.get("dmg"), r.get("cap"),
            )
            # id 키 충돌 주의: dict의 'id' 대신 'impact_delta' 사용
            r["dpd"] = m["dpd"]
            r["dpk"] = m["dpk"]
            r["impact_delta"] = m["impact_delta"]
            r["ap_pct"] = m["ap_pct"]
            r["zcs"] = m["zcs"]
    return rows
```

변경 후 (SND 블록 추가):
```python
    # 시간순(과거→최신)으로 뒤집기 + HP는 커스텀 지표 계산 추가
    rows.reverse()
    if mode == "HP":
        for r in rows:
            m = metrics.all_hp_metrics(
                r.get("kills"), r.get("deaths"), r.get("obj"),
                r.get("score"), r.get("impact"), r.get("dmg"), r.get("cap"),
            )
            # id 키 충돌 주의: dict의 'id' 대신 'impact_delta' 사용
            r["dpd"] = m["dpd"]
            r["dpk"] = m["dpk"]
            r["impact_delta"] = m["impact_delta"]
            r["ap_pct"] = m["ap_pct"]
            r["zcs"] = m["zcs"]
    else:  # SND: RDS 계산 추가
        for r in rows:
            m = metrics.all_snd_metrics(
                r.get("kills"), r.get("assists"), r.get("fk"),
                r.get("lww"), r.get("adr"), r.get("deaths"),
            )
            r["rds"] = m["rds"]
    return rows
```

- [ ] **Step 2: 검증**

실행:
```bash
cd "C:\Users\0616y\Downloads\Team management app" && python -c "
import queries
pid = queries.get_player_id('Maozyn')
ts = queries.player_metric_timeseries(pid, 'SND', 10)
assert ts, 'timeseries 비어있음'
print('SND ts keys:', sorted(ts[0].keys()))
assert 'rds' in ts[0], 'rds 키 없음'
assert all('rds' in r for r in ts), '일부 행에 rds 없음'
print('OK — RDS 추이:', [r['rds'] for r in ts])
"
```
Expected: `SND ts keys: [..., 'rds', ...]`, 각 행에 rds 값.

- [ ] **Step 3: 커밋**

```bash
git add queries.py
git commit -m "feat: player_metric_timeseries SND에 RDS 계산 추가"
```

---

### Task 6: queries.py — match_history / match_history_grouped SND에 RDS 추가

**Files:**
- Modify: `queries.py:467-485` (match_history 매치 dict)
- Modify: `queries.py:538-569` (match_history_grouped 매치 dict + SQL)

**Interfaces:**
- Produces: 매치 히스토리의 SND 매치에 `avg_rds` 키 추가 (matches.html 표용)

- [ ] **Step 1: match_history — SND avg_rds 서브쿼리 + dict 키 추가**

`queries.py`의 `match_history` 함수. SQL(470-482줄)에 SND avg_rds 서브쿼리 추가 후, 매치 dict(485-495줄)에 매핑.

현재 SQL (avg_zcs 서브쿼리 직후):
```sql
                       (SELECT ROUND(AVG(MAX(0, 1.1*obj_time + 8*capture_kill + 4.1*kills - 5*deaths)),1)
                        FROM player_stats_hp WHERE match_id=m.id) avg_zcs
                FROM matches m {where}
```
변경 후 (avg_rds 서브쿼리 추가):
```sql
                       (SELECT ROUND(AVG(MAX(0, 1.1*obj_time + 8*capture_kill + 4.1*kills - 5*deaths)),1)
                        FROM player_stats_hp WHERE match_id=m.id) avg_zcs,
                       (SELECT ROUND(AVG(MAX(0, 4.1*kills + 3.5*assists + 14*first_kill + 20*lone_wolf_win + 0.12*adr - 5*deaths)),1)
                        FROM player_stats_snd WHERE match_id=m.id) avg_rds
                FROM matches m {where}
```

매치 dict 매핑 (492-495줄). 현재:
```python
                    "avg_zcs": r["avg_zcs"],
```
변경 후:
```python
                    "avg_zcs": r["avg_zcs"],
                    "avg_rds": r["avg_rds"],
```

- [ ] **Step 2: match_history_grouped — 동일하게 avg_rds 추가**

`queries.py`의 `match_history_grouped` 함수. SQL(549-553줄)에 avg_rds 서브쿼리 추가 후, 매치 dict(565-569줄)에 매핑.

현재 SQL (avg_zcs 서브쿼리 직후):
```sql
                         (SELECT ROUND(AVG(MAX(0, 1.1*obj_time + 8*capture_kill + 4.1*kills - 5*deaths)),1)
                          FROM player_stats_hp WHERE match_id=m.id) avg_zcs,
                         (m.match_date IS NULL) is_null
```
변경 후 (avg_rds 추가):
```sql
                         (SELECT ROUND(AVG(MAX(0, 1.1*obj_time + 8*capture_kill + 4.1*kills - 5*deaths)),1)
                          FROM player_stats_hp WHERE match_id=m.id) avg_zcs,
                         (SELECT ROUND(AVG(MAX(0, 4.1*kills + 3.5*assists + 14*first_kill + 20*lone_wolf_win + 0.12*adr - 5*deaths)),1)
                          FROM player_stats_snd WHERE match_id=m.id) avg_rds,
                         (m.match_date IS NULL) is_null
```

매치 dict 매핑 (569줄 부근). 현재:
```python
            "avg_zcs": r["avg_zcs"],
```
변경 후:
```python
            "avg_zcs": r["avg_zcs"],
            "avg_rds": r["avg_rds"],
```

- [ ] **Step 3: 검증**

실행:
```bash
cd "C:\Users\0616y\Downloads\Team management app" && python -c "
import queries
hist = queries.match_history(limit=20, mode='SND')
assert hist['matches'], 'SND 매치 없음'
m = hist['matches'][0]
print('SND 매치 keys:', sorted([k for k in m.keys() if 'rds' in k or 'zcs' in k]))
assert 'avg_rds' in m, 'avg_rds 키 없음'
# grouped
grp = queries.match_history_grouped(mode='SND')
gm = grp['groups'][0]['matches'][0] if grp['groups'] else {}
if gm:
    print('grouped 매치 avg_rds:', gm.get('avg_rds'))
    assert 'avg_rds' in gm, 'grouped avg_rds 없음'
print('OK')
"
```
Expected: `avg_rds` 키 존재, 값 있음.

- [ ] **Step 4: 커밋**

```bash
git add queries.py
git commit -m "feat: match_history/grouped SND 매치에 avg_rds 추가"
```

---

### Task 7: queries.py — 맵 쿼리들 SND에 RDS 추가

**Files:**
- Modify: `queries.py:655-685` (map_team_stats SND)
- Modify: `queries.py:725-745` (map_team_stats_recent SND)
- Modify: `queries.py:798-815` (map_player_stats SND)

**Interfaces:**
- Produces: SND 맵 쿼리들에 `avg_rds` 컬럼 추가 (maps.html / map_detail.html / map_trend용)

- [ ] **Step 1: map_team_stats SND에 avg_rds 추가**

`queries.py`의 `map_team_stats` SND 분기(670-685줄). 현재:
```sql
                 FROM player_stats_snd s JOIN matches m ON m.id=s.match_id
                 WHERE m.map_name IS NOT NULL AND m.map_name != '' AND m.mode='SND'
                 GROUP BY LOWER(m.map_name)
                 HAVING COUNT(*) >= ?
                 ORDER BY avg_kd DESC"""
```
이 SELECT 절에 avg_rds 인라인 공식 추가. SND SELECT 전체(670-678줄):
```sql
        sql = """SELECT LOWER(m.map_name) map_name,
                        COUNT(*) n_matches,
                        ROUND(AVG(s.kd_ratio),2) avg_kd,
                        ROUND(AVG(s.kills),1) avg_k,
                        ROUND(AVG(s.adr),0) avg_adr,
                        ROUND(AVG(MAX(0, 4.1*s.kills + 3.5*s.assists + 14*s.first_kill + 20*s.lone_wolf_win + 0.12*s.adr - 5*s.deaths)),1) avg_rds
                 FROM player_stats_snd s JOIN matches m ON m.id=s.match_id
                 WHERE m.map_name IS NOT NULL AND m.map_name != '' AND m.mode='SND'
                 GROUP BY LOWER(m.map_name)
                 HAVING COUNT(*) >= ?
                 ORDER BY avg_kd DESC"""
```

- [ ] **Step 2: map_team_stats_recent SND에 avg_rds 추가**

`queries.py`의 `map_team_stats_recent` SND 분기(734-745줄). 동일하게 SELECT 절에 avg_rds 추가. SND SELECT 전체:
```sql
        sql = f"""SELECT LOWER(m.map_name) map_name,
                        COUNT(*) n_matches,
                        ROUND(AVG(s.kd_ratio),2) avg_kd,
                        ROUND(AVG(s.kills),1) avg_k,
                        ROUND(AVG(s.adr),0) avg_adr,
                        ROUND(AVG(MAX(0, 4.1*s.kills + 3.5*s.assists + 14*s.first_kill + 20*s.lone_wolf_win + 0.12*s.adr - 5*s.deaths)),1) avg_rds
                 FROM player_stats_snd s JOIN matches m ON m.id=s.match_id
                 WHERE m.map_name IS NOT NULL AND m.map_name != '' AND m.mode='SND'
                   AND m.id IN ({recent_ids})
                 GROUP BY LOWER(m.map_name)
                 HAVING COUNT(*) >= ?
                 ORDER BY avg_kd DESC"""
```

- [ ] **Step 3: map_player_stats SND에 avg_rds 추가**

`queries.py`의 `map_player_stats` SND 분기(806-815줄). SELECT 절에 avg_rds 추가. SND SELECT 전체:
```sql
        sql = """SELECT p.name player_name,
                        COUNT(*) matches,
                        ROUND(AVG(s.kd_ratio),2) avg_kd,
                        ROUND(AVG(s.kills),1) avg_k,
                        ROUND(AVG(s.adr),0) avg_adr,
                        ROUND(AVG(MAX(0, 4.1*s.kills + 3.5*s.assists + 14*s.first_kill + 20*s.lone_wolf_win + 0.12*s.adr - 5*s.deaths)),1) avg_rds
                 FROM player_stats_snd s
                 JOIN matches m ON m.id=s.match_id
                 JOIN players p ON p.id=s.player_id
                 WHERE LOWER(m.map_name)=LOWER(?) AND m.mode='SND'
                 GROUP BY p.id, p.name
                 HAVING COUNT(*) >= ?
                 ORDER BY avg_kd DESC"""
```

- [ ] **Step 4: 검증**

실행:
```bash
cd "C:\Users\0616y\Downloads\Team management app" && python -c "
import queries
# map_team_stats SND
mts = queries.map_team_stats('SND', 1)
if mts:
    print('map_team_stats SND keys:', [k for k in mts[0] if 'rds' in k])
    assert 'avg_rds' in mts[0], 'avg_rds 없음'
# map_player_stats SND (맵 이름 필요)
print('OK (SND 맵 데이터 있으면 avg_rds 검증, 없으면 스킵)')
"
```
Expected: `avg_rds` 키 존재 (데이터 있을 경우).

- [ ] **Step 5: 커밋**

```bash
git add queries.py
git commit -m "feat: 맵 쿼리 SND(map_team_stats/recent/player)에 avg_rds 추가"
```

---

### Task 8: queries.py — map_trend SND에 RDS 추가 + _COMPARE_SND에 rds 추가

**Files:**
- Modify: `queries.py:928-968` (map_trend SND 분기 — RDS 계산)
- Modify: `queries.py:1145-1153` (_COMPARE_SND 리스트 — rds 첫 행)

**Interfaces:**
- Produces: `map_trend("...", "SND")` 반환 recent/season 블록에 `rds` 키
- Produces: `compare_players(..., "SND")` rows에 rds 첫 행

- [ ] **Step 1: map_trend SND에 RDS 계산 추가**

`queries.py`의 `map_trend` 함수 (928-968줄). HP 커스텀 지표 계산 블록(`if mode == "HP":`) 이후에 SND 블록 추가.

현재 (959-968줄):
```python
    # HP: 커스텀 지표(ZCS/DPD/DPK/ID/AP%)를 평균 raw 값으로부터 계산해 추가
    if mode == "HP":
        for block in (recent, season):
            if block.get("matches"):
                m = _metrics.all_hp_metrics(
                    block.get("avg_k"), block.get("avg_d"), block.get("avg_obj"),
                    block.get("avg_score"), block.get("avg_impact"),
                    block.get("avg_dmg"), block.get("avg_capture"),
                )
                block["zcs"] = m["zcs"]
                block["dpd"] = m["dpd"]
                block["dpk"] = m["dpk"]
                block["impact_delta"] = m["impact_delta"]
                block["ap_pct"] = m["ap_pct"]
```

변경 후 (else 분기로 SND RDS 추가 — 이 블록 바로 뒤에):
```python
    # HP: 커스텀 지표(ZCS/DPD/DPK/ID/AP%)를 평균 raw 값으로부터 계산해 추가
    if mode == "HP":
        for block in (recent, season):
            if block.get("matches"):
                m = _metrics.all_hp_metrics(
                    block.get("avg_k"), block.get("avg_d"), block.get("avg_obj"),
                    block.get("avg_score"), block.get("avg_impact"),
                    block.get("avg_dmg"), block.get("avg_capture"),
                )
                block["zcs"] = m["zcs"]
                block["dpd"] = m["dpd"]
                block["dpk"] = m["dpk"]
                block["impact_delta"] = m["impact_delta"]
                block["ap_pct"] = m["ap_pct"]
    else:  # SND: RDS 계산 추가
        for block in (recent, season):
            if block.get("matches"):
                m = _metrics.all_snd_metrics(
                    block.get("avg_k"), block.get("avg_a"),
                    block.get("avg_fk", 0), block.get("avg_lww", 0),
                    block.get("avg_adr"), block.get("avg_d"),
                )
                block["rds"] = m["rds"]
```

**주의**: map_trend의 SND `_q()` 함수는 현재 `avg_a`/`avg_adr`만 SELECT하고 `avg_fk`/`avg_lww`가 없음. RDS 계산을 위해 이 컬럼들도 SELECT에 추가해야 함. SND `_q()`의 SELECT 절(947-950줄) 수정:

현재:
```python
            return ("SELECT COUNT(*) matches, "
                    "ROUND(AVG(s.kd_ratio),2) avg_kd, ROUND(AVG(s.kills),1) avg_k, "
                    "ROUND(AVG(s.deaths),1) avg_d, ROUND(AVG(s.assists),1) avg_a, "
                    "ROUND(AVG(s.adr),0) avg_adr, ROUND(AVG(s.score),0) avg_score, "
                    "ROUND(AVG(s.impact),0) avg_impact "
                    f"FROM player_stats_snd s JOIN matches m ON m.id=s.match_id {wh}")
```
변경 후 (avg_fk, avg_lww 추가):
```python
            return ("SELECT COUNT(*) matches, "
                    "ROUND(AVG(s.kd_ratio),2) avg_kd, ROUND(AVG(s.kills),1) avg_k, "
                    "ROUND(AVG(s.deaths),1) avg_d, ROUND(AVG(s.assists),1) avg_a, "
                    "ROUND(AVG(s.adr),0) avg_adr, ROUND(AVG(s.score),0) avg_score, "
                    "ROUND(AVG(s.impact),0) avg_impact, "
                    "ROUND(AVG(s.first_kill),2) avg_fk, ROUND(AVG(s.lone_wolf_win),2) avg_lww "
                    f"FROM player_stats_snd s JOIN matches m ON m.id=s.match_id {wh}")
```

- [ ] **Step 2: _COMPARE_SND에 rds 첫 행 추가**

`queries.py`의 `_COMPARE_SND` (1145-1153줄). 현재:
```python
_COMPARE_SND = [
    ("avg_kd", "kd", True),
    ("avg_k", "avg_k", True),
    ("avg_d", "avg_d", False),
    ("avg_a", "avg_a", True),
    ("avg_adr", "avg_adr", True),
    ("avg_score", "avg_score", True),
    ("avg_impact", "avg_impact", True),
]
```
변경 후 (rds를 첫 행으로 — ZCS가 HP 첫 행인 것과 대칭):
```python
_COMPARE_SND = [
    ("rds", "rds_label", True),
    ("avg_kd", "kd", True),
    ("avg_k", "avg_k", True),
    ("avg_d", "avg_d", False),
    ("avg_a", "avg_a", True),
    ("avg_adr", "avg_adr", True),
    ("avg_score", "avg_score", True),
    ("avg_impact", "avg_impact", True),
]
```

- [ ] **Step 3: 검증**

실행:
```bash
cd "C:\Users\0616y\Downloads\Team management app" && python -c "
import queries
# compare_players SND — rds 첫 행
data = queries.compare_players('Maozyn', 'Cartels', 'SND')
assert data, 'compare 데이터 없음'
first_row = data['rows'][0]
print('compare SND 첫 행:', first_row['key'], first_row['label_key'])
assert first_row['key'] == 'rds', f'첫 행이 rds 아님: {first_row[\"key\"]}'
# map_trend SND (맵 데이터 있을 경우)
print('OK')
"
```
Expected: `compare SND 첫 행: rds rds_label`, `OK`.

- [ ] **Step 4: 커밋**

```bash
git add queries.py
git commit -m "feat: map_trend SND RDS + _COMPARE_SND rds 첫 행 추가"
```

---

### Task 9: analytics.py — match_report SND에 RDS 추가

**Files:**
- Modify: `analytics.py:83-118` (match_report SND 분기)

**Interfaces:**
- Produces: `match_report` SND 결과의 각 player dict에 `rds` 키 추가 + `team_totals`에 `rds` 추가

- [ ] **Step 1: SND player dict에 rds 추가**

`analytics.py`의 `match_report` SND 분기(91-98줄). 각 player dict에 rds 계산 추가.

현재 (91-98줄):
```python
            for r in rows:
                result["players"].append({
                    "name": r["name"], "k": r["kills"] or 0, "d": r["deaths"] or 0,
                    "a": r["assists"] or 0, "kd": r["kd_ratio"] or 0,
                    "score": r["score"] or 0, "impact": r["impact"] or 0,
                    "adr": r["adr"] or 0, "fk": r["first_kill"] or 0,
                    "lww": r["lone_wolf_win"] or 0,
                })
```

변경 후 (rds 추가 — metrics 임포트 후):
```python
            import metrics as _metrics
            for r in rows:
                rds = _metrics.compute_rds(
                    r["kills"] or 0, r["assists"] or 0,
                    r["first_kill"] or 0, r["lone_wolf_win"] or 0,
                    r["adr"] or 0, r["deaths"] or 0,
                )
                result["players"].append({
                    "name": r["name"], "k": r["kills"] or 0, "d": r["deaths"] or 0,
                    "a": r["assists"] or 0, "kd": r["kd_ratio"] or 0,
                    "score": r["score"] or 0, "impact": r["impact"] or 0,
                    "adr": r["adr"] or 0, "fk": r["first_kill"] or 0,
                    "lww": r["lone_wolf_win"] or 0, "rds": rds,
                })
```

- [ ] **Step 2: team_totals에 rds 추가**

같은 SND 분기의 `team_totals` (99-104줄). 현재:
```python
            result["team_totals"] = {
                "kills": sum(p["k"] for p in result["players"]),
                "deaths": sum(p["d"] for p in result["players"]),
                "assists": sum(p["a"] for p in result["players"]),
                "fk": sum(p["fk"] for p in result["players"]),
            }
```
변경 후 (rds 추가 — 팀 RDS는 선수 RDS의 평균):
```python
            rds_vals = [p["rds"] for p in result["players"] if p["rds"] is not None]
            result["team_totals"] = {
                "kills": sum(p["k"] for p in result["players"]),
                "deaths": sum(p["d"] for p in result["players"]),
                "assists": sum(p["a"] for p in result["players"]),
                "fk": sum(p["fk"] for p in result["players"]),
                "rds": round(sum(rds_vals) / len(rds_vals), 1) if rds_vals else None,
            }
```

- [ ] **Step 3: 검증**

실행:
```bash
cd "C:\Users\0616y\Downloads\Team management app" && python -c "
import analytics, queries
# SND 매치 하나 찾기
hist = queries.match_history(limit=5, mode='SND')
if hist['matches']:
    mid = hist['matches'][0]['id']
    rep = analytics.match_report(mid)
    assert rep['mode'] == 'SND'
    p0 = rep['players'][0]
    print('SND player keys:', sorted([k for k in p0 if 'rds' in k]))
    assert 'rds' in p0, 'player에 rds 없음'
    print('team_totals rds:', rep['team_totals'].get('rds'))
    assert 'rds' in rep['team_totals'], 'team_totals에 rds 없음'
    print('OK')
else:
    print('SND 매치 없음 — 스킵')
"
```
Expected: player dict와 team_totals에 `rds` 키 존재.

- [ ] **Step 4: 커밋**

```bash
git add analytics.py
git commit -m "feat: match_report SND에 RDS (선수별 + 팀 평균) 추가"
```

---

### Task 10: i18n — rds 키 3개국어 추가

**Files:**
- Modify: `i18n/_ko.py`, `i18n/_en.py`, `i18n/_es.py`
- Test: `test_i18n.py` (이미 존재, 실행만)

**Interfaces:**
- Produces: `t.rds_label`, `t.m_rds`, `t.rds_full`, `t.rds_team`, `t.avg_rds_col` (ZCS 대칭 키)

- [ ] **Step 1: _ko.py — rds 키 추가**

`i18n/_ko.py`의 ZCS 키 근처(`m_zcs`, `zcs_label` 등이 있는 영역)에 대칭 키 추가. `m_zcs` 근처에 `m_rds` 추가, `zcs_label` 근처에 `rds_label`/`rds_full`/`avg_rds_col` 추가.

ZCS 키 패턴 참조 (이미 확인됨):
```python
        "m_zcs": "ZCS (존 컨트롤)",
```
이 줄 직후에 추가:
```python
        "m_rds": "RDS (라운드 장악력)",
```

그리고 `zcs_label`/`zcs_full`/`avg_zcs_col` 근처:
```python
        "zcs_label": "ZCS",
        "zcs_full": "존 컨트롤 점수",
        "zcs_team": "팀 평균 ZCS",
        "zcs_trend_title": "팀 ZCS 추이",
        "avg_zcs_col": "평균 ZCS",
```
이 블록 직후에 추가:
```python
        "rds_label": "RDS",
        "rds_full": "라운드 장악력 점수",
        "rds_team": "팀 평균 RDS",
        "avg_rds_col": "평균 RDS",
```

- [ ] **Step 2: _en.py — 동일 키 영문 추가**

`i18n/_en.py`의 동일 위치에 추가:
```python
        "m_rds": "RDS (Round Domination)",
```
그리고:
```python
        "rds_label": "RDS",
        "rds_full": "Round Domination Score",
        "rds_team": "Team Avg RDS",
        "avg_rds_col": "Avg RDS",
```

- [ ] **Step 3: _es.py — 동일 키 스페인어 추가**

`i18n/_es.py`의 동일 위치에 추가:
```python
        "m_rds": "RDS (Dominio de Ronda)",
```
그리고:
```python
        "rds_label": "RDS",
        "rds_full": "Puntuación de Dominio de Ronda",
        "rds_team": "RDS Promedio del Equipo",
        "avg_rds_col": "RDS Promedio",
```

- [ ] **Step 4: i18n 키 동일성 검증**

실행:
```bash
cd "C:\Users\0616y\Downloads\Team management app" && python -m pytest test_i18n.py -v
```
Expected: PASS (3개국어 키 집합 동일). 실패 시 누락된 키가 어느 언어인지 출력에서 확인 후 추가.

- [ ] **Step 5: 커밋**

```bash
git add i18n/_ko.py i18n/_en.py i18n/_es.py
git commit -m "feat: i18n — RDS 키 3개국어(ko/en/es) 추가"
```

---

### Task 11: 템플릿 — players.html SND 카드에 RDS 추가

**Files:**
- Modify: `templates/players.html:39-40` (SND 카드 값/서브)

**Interfaces:**
- Consumes: `p.rds` (Task 3 all_players_overview SND에서 추가)

- [ ] **Step 1: SND 카드에 RDS 값 노출**

`templates/players.html`의 SND 카드(39-40줄). 현재:
```html
        <div class="player-card__value player-card__value--snd">{{ p.avg_kd }}</div>
        <div class="muted player-card__sub">{{ t.m_kills }} {{ p.avg_k }} · {{ t.avg_adr }} {{ p.avg_adr }}</div>
```
변경 후 (RDS를 강조 값으로, K/D는 서브로 이동 — HP 카드가 ZCS 강조인 것과 대칭):
```html
        <div class="player-card__value player-card__value--snd">{{ p.rds if p.rds is not none else '-' }}</div>
        <div class="muted player-card__sub">{{ t.kd }} {{ p.avg_kd }} · {{ t.m_kills }} {{ p.avg_k }}</div>
```

- [ ] **Step 2: 검증 — /players?mode=SND 렌더링**

실행 (웹 서버를 띄우지 않고 템플릿 렌더만 확인):
```bash
cd "C:\Users\0616y\Downloads\Team management app" && python -c "
import queries, i18n
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates'))
tpl = env.get_template('players.html')
players = queries.all_players_overview('SND')
html = tpl.render(players=players, mode='SND', lang='ko', t=i18n.get_dict('ko'))
assert 'RDS' in html or 'rds' in html.lower() or 'player-card__value--snd' in html
print('OK — players.html SND 렌더링 정상')
"
```
Expected: `OK`.

- [ ] **Step 3: 커밋**

```bash
git add templates/players.html
git commit -m "feat: players.html SND 카드 — RDS 강조 값 + K/D 서브"
```

---

### Task 12: 템플릿 — player_detail.html SND 섹션에 RDS 추가

**Files:**
- Modify: `templates/player_detail.html:86-98` (SND 상세표)
- Modify: `templates/player_detail.html:260-270` (timeseries 차트 metric 옵션)

**Interfaces:**
- Consumes: `stats.snd.rds` (Task 2), timeseries `rds` (Task 5)

- [ ] **Step 1: SND 상세표에 RDS 행 추가**

`templates/player_detail.html`의 SND 상세표(86-98줄). 현재 avg_lww 행(97줄) 다음에 RDS 행 추가.

현재 (91-97줄):
```html
        <tr><td>{{ t.avg_kda }}</td><td class="num"><strong>{{ stats.snd.avg_k }} / {{ stats.snd.avg_d }} / {{ stats.snd.avg_a }}</strong></td></tr>
        <tr><td>{{ t.kd }}</td><td class="num delta-up"><strong>{{ stats.snd.avg_kd }}</strong></td></tr>
        <tr><td>{{ t.avg_adr }}</td><td class="num">{{ stats.snd.avg_adr }}</td></tr>
        <tr><td>{{ t.avg_score }}</td><td class="num">{{ stats.snd.avg_score }}</td></tr>
        <tr><td>{{ t.avg_impact }}</td><td class="num">{{ stats.snd.avg_impact }}</td></tr>
        <tr><td>{{ t.avg_fk }}</td><td class="num">{{ stats.snd.avg_fk }}</td></tr>
        <tr><td>{{ t.avg_lww }}</td><td class="num">{{ stats.snd.avg_lww }}</td></tr>
```

변경 후 (RDS 행을 표 상단에 강조 — ZCS가 HP 표에 첫 강조 행인 것과 대칭. `avg_kda` 행 앞에 추가):
```html
        <tr><td>{{ t.rds_label }}</td><td class="num"><strong class="rds-strong">{{ stats.snd.rds if stats.snd.rds is not none else '-' }}</strong></td></tr>
        <tr><td>{{ t.avg_kda }}</td><td class="num"><strong>{{ stats.snd.avg_k }} / {{ stats.snd.avg_d }} / {{ stats.snd.avg_a }}</strong></td></tr>
        <tr><td>{{ t.kd }}</td><td class="num delta-up"><strong>{{ stats.snd.avg_kd }}</strong></td></tr>
        <tr><td>{{ t.avg_adr }}</td><td class="num">{{ stats.snd.avg_adr }}</td></tr>
        <tr><td>{{ t.avg_score }}</td><td class="num">{{ stats.snd.avg_score }}</td></tr>
        <tr><td>{{ t.avg_impact }}</td><td class="num">{{ stats.snd.avg_impact }}</td></tr>
        <tr><td>{{ t.avg_fk }}</td><td class="num">{{ stats.snd.avg_fk }}</td></tr>
        <tr><td>{{ t.avg_lww }}</td><td class="num">{{ stats.snd.avg_lww }}</td></tr>
```

- [ ] **Step 2: .rds-strong CSS 클래스 추가 (SND 색)**

`templates/player_detail.html`의 인라인 `<style>`에서 `.zcs-strong` 정의(197줄) 근처에 추가:
```css
.rds-strong { color: var(--snd); }
```

- [ ] **Step 3: timeseries 차트 metric 옵션에 rds 추가**

`templates/player_detail.html`의 JS metric 옵션(260-270줄). SND 배열에 rds 추가.

현재 SND 배열(263-266줄):
```javascript
    SND: [
        {v:'kd', g:'SND'}, {v:'kills', g:'SND'}, {v:'deaths', g:'SND'},
        {v:'assists', g:'SND'}, {v:'adr', g:'SND'}, {v:'fk', g:'SND'}, {v:'lww', g:'SND'},
    ],
```
변경 후 (rds를 첫 항목으로):
```javascript
    SND: [
        {v:'rds', g:'SND'}, {v:'kd', g:'SND'}, {v:'kills', g:'SND'}, {v:'deaths', g:'SND'},
        {v:'assists', g:'SND'}, {v:'adr', g:'SND'}, {v:'fk', g:'SND'}, {v:'lww', g:'SND'},
    ],
```

그리고 metric label 매핑(240/244/248줄 부근의 JS 객체)에 rds 라벨 추가. HP/SND label 객체에 추가:
```javascript
          impact_delta:"ID", ap_pct:"AP%", zcs:"ZCS",
```
이 줄들을 찾아, SND용 라벨 객체(또는 공통)에 `rds:"RDS"` 추가. 정확한 위치는 label 객체 구조 확인 후 — 보통 3개 언어별 객체가 있음. 각 객체에 `rds:"RDS"` 키 추가.

- [ ] **Step 4: 검증**

실행:
```bash
cd "C:\Users\0616y\Downloads\Team management app" && python -c "
import queries, i18n
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates'))
tpl = env.get_template('player_detail.html')
pid = queries.get_player_id('Maozyn')
stats = queries.player_overall_stats(pid)
html = tpl.render(stats=stats, team_hp={}, insight=None, player_maps=[], lang='ko', t=i18n.get_dict('ko'))
assert 'rds-strong' in html or 'RDS' in html
print('OK — player_detail SND RDS 행 렌더링')
"
```
Expected: `OK`.

- [ ] **Step 5: 커밋**

```bash
git add templates/player_detail.html
git commit -m "feat: player_detail.html SND 섹션 — RDS 강조 행 + 차트 metric"
```

---

### Task 13: 템플릿 — leaderboard.html SND에 RDS 옵션 추가

**Files:**
- Modify: `templates/leaderboard.html:9` (metric_opts_snd)

**Interfaces:**
- Consumes: SND rds metric (Task 4)

- [ ] **Step 1: metric_opts_snd에 rds 옵션 추가**

`templates/leaderboard.html` 9줄. 현재:
```python
{% set metric_opts_snd = [('avg_kd', t.kd), ('avg_k', t.avg_k), ('avg_score', t.avg_score), ('avg_adr', t.avg_impact)] %}
```
변경 후 (rds를 첫 옵션으로 — HP가 zcs 첫 옵션인 것과 대칭. metric_opts_hp 확인: 8줄에서 zcs가 마지막이므로, SND도 rds를 마지막에 추가하여 패턴 일치):
```python
{% set metric_opts_snd = [('avg_kd', t.kd), ('avg_k', t.avg_k), ('avg_score', t.avg_score), ('avg_adr', t.avg_impact), ('rds', t.m_rds)] %}
```

- [ ] **Step 2: 검증**

실행:
```bash
cd "C:\Users\0616y\Downloads\Team management app" && python -c "
import queries, i18n
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates'))
tpl = env.get_template('leaderboard.html')
rows = queries.advanced_leaderboard('rds', 20)
html = tpl.render(rows=rows, mode='SND', metric='rds', avg_value=None, higher_better=True, lang='ko', t=i18n.get_dict('ko'))
assert 'RDS' in html or 'rds' in html
print('OK — leaderboard SND RDS 옵션 렌더링')
"
```
Expected: `OK`.

- [ ] **Step 3: 커밋**

```bash
git add templates/leaderboard.html
git commit -m "feat: leaderboard.html SND metric 옵션에 RDS 추가"
```

---

### Task 14: 템플릿 — compare.html SND 레이더에 RDS 반영

**Files:**
- Read: `templates/compare.html` (SND rows/chart 처리 확인)

**Interfaces:**
- Consumes: `compare_players(..., "SND")` rows 첫 행 rds (Task 8)

- [ ] **Step 1: compare.html 확인 — rows/chart가 데이터 기반이라 템플릿 변경 불필요한지 검증**

`compare.html`은 `data.rows`와 `data.chart`를 반복하므로, `_COMPARE_SND`에 rds를 추가하면 자동 반영됨. 단, 라벨 키 `rds_label`이 i18n에 존재해야 함 (Task 10에서 추가).

검증 실행:
```bash
cd "C:\Users\0616y\Downloads\Team management app" && python -c "
import queries, i18n
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates'))
tpl = env.get_template('compare.html')
data = queries.compare_players('Maozyn', 'Cartels', 'SND')
html = tpl.render(players=queries.list_players(), a='Maozyn', b='Cartels', mode='SND', data=data, lang='ko', t=i18n.get_dict('ko'))
# rds_label이 렌더링되는지
assert 'RDS' in html, 'compare SND에 RDS 미노출'
print('compare SND 첫 row label:', data['rows'][0]['label_key'])
print('OK — compare SND RDS 자동 반영 확인')
"
```

Expected: `compare SND 첫 row label: rds_label`, `OK`.

- [ ] **Step 2: 라벨 렌더링 확인 — t[row.label_key] 패턴이면 통과, 아니면 수정**

compare.html이 `{{ t[row.label_key] }}` 형태로 라벨을 렌더링하는지 확인. Step 1 검증이 통과하면 변경 불필요. rds_label 키가 i18n에 있으므로 정상 렌더링됨.

- [ ] **Step 3: 커밋 (변경 있을 경우만)**

```bash
git add templates/compare.html
git commit -m "feat: compare.html SND RDS 라벨 반영 (필요 시)"
```
변경이 없으면 스킵 (Step 1에서 OK 나오면 커밋 없이 다음 Task로).

---

### Task 15: 템플릿 — matches.html / match_detail.html SND에 RDS 추가

**Files:**
- Modify: `templates/matches.html:32,50` (매치 표 — SND avg_rds)
- Modify: `templates/match_detail.html:169,195,209` (매치 상세 — SND player rds + team_totals)

**Interfaces:**
- Consumes: `m.avg_rds` (Task 6), `p.rds`/`report.team_totals.rds` (Task 9)

- [ ] **Step 1: matches.html — SND 매치 avg_rds 노출**

`templates/matches.html`의 매치 표(50줄). 현재 ZCS 컬럼이 HP-only:
```html
                <td class="num">{% if m.mode == 'HP' and m.avg_zcs is not none %}<strong class="zcs-strong">{{ m.avg_zcs }}</strong>{% else %}-{% endif %}</td>
```
변경 후 (HP면 ZCS, SND면 RDS):
```html
                <td class="num">{% if m.mode == 'HP' and m.avg_zcs is not none %}<strong class="zcs-strong">{{ m.avg_zcs }}</strong>{% elif m.mode == 'SND' and m.avg_rds is not none %}<strong class="rds-strong">{{ m.avg_rds }}</strong>{% else %}-{% endif %}</td>
```

그리고 표 헤더(32줄) 확인 — 현재 `{{ t.zcs_label }}`인데, 모드에 따라 ZCS/RDS 라벨 전환:
```html
                <th class="num">{{ t.zcs_label }}</th>
```
변경 후:
```html
                <th class="num">{% if mode == 'SND' %}{{ t.rds_label }}{% else %}{{ t.zcs_label }}{% endif %}</th>
```

그리고 `.rds-strong` CSS 추가(79줄 `.zcs-strong` 근처):
```css
.rds-strong { color: var(--snd); }
```

- [ ] **Step 2: match_detail.html — SND player rds + team_totals rds 노출**

`templates/match_detail.html`:

(a) team_totals(169줄). 현재 ZCS만:
```html
        <span class="team-avg-item"><span class="team-avg-label">{{ t.zcs_label }}</span> <strong class="zcs-strong">{{ report.team_totals.zcs }}</strong></span>
```
변경 후 (모드에 따라 ZCS/RDS):
```html
        {% if report.mode == 'SND' %}
        <span class="team-avg-item"><span class="team-avg-label">{{ t.rds_label }}</span> <strong class="rds-strong">{{ report.team_totals.rds }}</strong></span>
        {% else %}
        <span class="team-avg-item"><span class="team-avg-label">{{ t.zcs_label }}</span> <strong class="zcs-strong">{{ report.team_totals.zcs }}</strong></span>
        {% endif %}
```

(b) 선수 표 헤더(195줄). 현재 ZCS:
```html
                <th class="num">{{ t.zcs_label }}</th>
```
변경 후:
```html
                <th class="num">{% if report.mode == 'SND' %}{{ t.rds_label }}{% else %}{{ t.zcs_label }}{% endif %}</th>
```

(c) 선수 표 값(209줄). 현재 ZCS:
```html
                <td class="num"><strong class="zcs-strong">{{ p.zcs }}</strong></td>
```
변경 후 (HP: zcs, SND: rds):
```html
                <td class="num">{% if report.mode == 'SND' %}<strong class="rds-strong">{{ p.rds }}</strong>{% else %}<strong class="zcs-strong">{{ p.zcs }}</strong>{% endif %}</td>
```

(d) `.rds-strong` CSS 추가(23줄 `.zcs-strong` 근처):
```css
.rds-strong { color: var(--snd); }
```

- [ ] **Step 3: 검증**

실행:
```bash
cd "C:\Users\0616y\Downloads\Team management app" && python -c "
import queries, analytics, i18n
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates'))
# matches.html (SND)
hist = queries.match_history(limit=10, mode='SND')
tpl = env.get_template('matches.html')
html = tpl.render(matches_data=hist, mode='SND', lang='ko', t=i18n.get_dict('ko'))
assert 'rds-strong' in html or 'RDS' in html
# match_detail.html (SND 매치)
if hist['matches']:
    mid = hist['matches'][0]['id']
    rep = analytics.match_report(mid)
    tpl2 = env.get_template('match_detail.html')
    html2 = tpl2.render(report=rep, insight=None, is_admin=False, day_notes={}, match_notes=[], match_players=[], lang='ko', t=i18n.get_dict('ko'))
    assert 'rds-strong' in html2 or 'RDS' in html2
print('OK — matches/match_detail SND RDS 렌더링')
"
```
Expected: `OK`.

- [ ] **Step 4: 커밋**

```bash
git add templates/matches.html templates/match_detail.html
git commit -m "feat: matches/match_detail — SND 매치 RDS 노출 (ZCS 대칭)"
```

---

### Task 16: 템플릿 — maps.html / map_detail.html SND에 RDS 추가

**Files:**
- Modify: `templates/maps.html:22-23` (맵 카드 — SND avg_rds)
- Modify: `templates/map_detail.html:26-29,106,122` (맵 상세 — SND rds)

**Interfaces:**
- Consumes: `m.avg_rds` (Task 7 맵 쿼리)

- [ ] **Step 1: maps.html — 맵 카드에 모드별 ZCS/RDS**

`templates/maps.html` 22-23줄. 현재:
```html
        <div class="stat-label">{{ t.zcs_label }}</div>
        <div class="entity-card__value entity-card__value--hp">{{ m.avg_zcs or '-' }}</div>
```
변경 후 (모드에 따라 ZCS/RDS):
```html
        <div class="stat-label">{% if mode == 'SND' %}{{ t.rds_label }}{% else %}{{ t.zcs_label }}{% endif %}</div>
        <div class="entity-card__value entity-card__value--hp">{% if mode == 'SND' %}{{ m.avg_rds or '-' }}{% else %}{{ m.avg_zcs or '-' }}{% endif %}</div>
```

- [ ] **Step 2: map_detail.html — 맵 상세 ZCS 카드/표에 SND RDS**

`templates/map_detail.html`:

(a) 시즌 카드(26-29줄). 현재 ZCS 카드:
```html
    {% if data.trend.season.zcs is not none %}
    <div class="value text-accent">{{ data.trend.season.zcs }}</div>
    <div class="label">{{ t.zcs_label }} ({{ t.hub_season }})</div>
```
변경 후 (모드에 따라 ZCS/RDS — trend 블록에 zcs/rds 키 모두 대응):
```html
    {% set season_metric = data.trend.season.rds if data.mode == 'SND' else data.trend.season.zcs %}
    {% if season_metric is not none %}
    <div class="value text-accent">{{ season_metric }}</div>
    <div class="label">{% if data.mode == 'SND' %}{{ t.rds_label }}{% else %}{{ t.zcs_label }}{% endif %} ({{ t.hub_season }})</div>
```

(b) 선수 표 헤더(106줄). 현재 ZCS:
```html
                <th class="num">{{ t.zcs_label }}</th>
```
변경 후:
```html
                <th class="num">{% if data.mode == 'SND' %}{{ t.rds_label }}{% else %}{{ t.zcs_label }}{% endif %}</th>
```

(c) 선수 표 값(122줄). 현재 ZCS:
```html
                <td class="num"><strong class="zcs-strong">{{ p.avg_zcs or '-' }}</strong></td>
```
변경 후:
```html
                <td class="num"><strong class="{% if data.mode == 'SND' %}rds-strong{% else %}zcs-strong{% endif %}">{% if data.mode == 'SND' %}{{ p.avg_rds or '-' }}{% else %}{{ p.avg_zcs or '-' }}{% endif %}</strong></td>
```

(d) `.rds-strong` CSS 추가(141줄 `.zcs-strong` 근처):
```css
.rds-strong { color: var(--snd); }
```

- [ ] **Step 3: 검증**

실행:
```bash
cd "C:\Users\0616y\Downloads\Team management app" && python -c "
import queries, i18n
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates'))
# maps.html (SND)
mts = queries.map_team_stats('SND', 1)
tpl = env.get_template('maps.html')
html = tpl.render(maps_data=mts, mode='SND', lang='ko', t=i18n.get_dict('ko'))
assert 'rds-strong' in html or 'RDS' in html or 'avg_rds' in html
print('OK — maps.html SND RDS 렌더링 (데이터 있을 경우)')
"
```
Expected: `OK` (SND 맵 데이터 있을 경우 rds 렌더링).

- [ ] **Step 4: 커밋**

```bash
git add templates/maps.html templates/map_detail.html
git commit -m "feat: maps/map_detail — SND 맵 RDS 노출 (ZCS 대칭)"
```

---

### Task 17: AGENTS.md — RDS 문서화

**Files:**
- Modify: `AGENTS.md` (커스텀 지표 섹션 + 핵심 지표 섹션)

**Interfaces:**
- N/A (문서만)

- [ ] **Step 1: "핵심 지표: ZCS" 섹션 아래에 RDS 섹션 추가**

`AGENTS.md`의 `### 핵심 지표: ZCS (Zone Control Score)` 섹션 이후에 대칭 섹션 추가:

```markdown
### 핵심 지표: RDS (Round Domination Score)
- **RDS는 SND 모드의 ZCS 대응 지표다.** HP에서 ZCS를 제1 강조 지표로 다루듯, SND 컨텍스트에서는 RDS를 제1 강조 지표로 다룬다.
- 공식: `RDS = max(0, 4.1·K + 3.5·A + 14·FK + 20·LWW + 0.12·ADR − 5·D)` (SND 전용).
- 가중치는 경험적 매그니튜드 (FK≈3.4×K, LWW≈4.9×K). 승패 데이터 충분 시 로지스틱 회귀로 재튜닝 TODO.
- 진실 공식은 `metrics.py`의 `compute_rds()`. SQL에서도 동일 공식(`MAX(0, 4.1*kills + 3.5*assists + 14*first_kill + 20*lone_wolf_win + 0.12*adr - 5*deaths)`)을 쓰며, `_adapt_sql`이 Postgres용으로 `GREATEST(0, ...)`로 변환.
- HP 컨텍스트에 ZCS가 나오는 모든 곳의 SND 대응점에 RDS를 깐다 (선수표/상세/리더보드/비교/맵/매치).
```

- [ ] **Step 2: "커스텀 지표 전체 (metrics.py)" 섹션에 RDS 추가**

`AGENTS.md`의 커스텀 지표 목록에 RDS를 ZCS 다음에 추가:

```markdown
- **RDS** ⭐ — 라운드 장악력 (SND 제1 지표). ZCS의 SND 대응. 위 공식 참조.
```

- [ ] **Step 3: 커밋**

```bash
git add AGENTS.md
git commit -m "docs: AGENTS.md — RDS 핵심 지표 + 커스텀 지표 섹션 추가"
```

---

### Task 18: 통합 검증 — 전체 SND 컨텍스트 RDS 노출 확인

**Files:**
- N/A (검증만)

- [ ] **Step 1: 웹 서버 기동 후 SND 페이지들 렌더링 확인**

```bash
cd "C:\Users\0616y\Downloads\Team management app"
python -c "
import queries, analytics, i18n
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates'))
t = i18n.get_dict('ko')
errors = []

# 1. players SND
try:
    players = queries.all_players_overview('SND')
    html = env.get_template('players.html').render(players=players, mode='SND', lang='ko', t=t)
    assert players[0].get('rds') is not None
except Exception as e: errors.append(f'players SND: {e}')

# 2. player_detail SND
try:
    pid = queries.get_player_id('Maozyn')
    stats = queries.player_overall_stats(pid)
    assert stats['snd']['rds'] is not None
    ts = queries.player_metric_timeseries(pid, 'SND', 10)
    assert 'rds' in ts[0]
except Exception as e: errors.append(f'player_detail SND: {e}')

# 3. leaderboard SND rds
try:
    rows = queries.advanced_leaderboard('rds', 20)
    assert rows and rows[0]['value'] is not None
except Exception as e: errors.append(f'leaderboard SND rds: {e}')

# 4. compare SND
try:
    data = queries.compare_players('Maozyn', 'Cartels', 'SND')
    assert data['rows'][0]['key'] == 'rds'
except Exception as e: errors.append(f'compare SND: {e}')

# 5. match SND
try:
    hist = queries.match_history(limit=5, mode='SND')
    if hist['matches']:
        assert 'avg_rds' in hist['matches'][0]
        rep = analytics.match_report(hist['matches'][0]['id'])
        assert 'rds' in rep['players'][0]
        assert 'rds' in rep['team_totals']
except Exception as e: errors.append(f'match SND: {e}')

# 6. map SND
try:
    mts = queries.map_team_stats('SND', 1)
    if mts:
        assert 'avg_rds' in mts[0]
except Exception as e: errors.append(f'map SND: {e}')

if errors:
    print('FAIL:')
    for e in errors: print(f'  - {e}')
    exit(1)
else:
    print('ALL OK — RDS 모든 SND 컨텍스트 노출 확인')
"
```
Expected: `ALL OK`.

- [ ] **Step 2: i18n 키 동일성 최종 확인**

```bash
cd "C:\Users\0616y\Downloads\Team management app" && python -m pytest test_i18n.py -v
```
Expected: PASS.

- [ ] **Step 3: 최종 커밋 (미커밋 변경분이 있을 경우)**

```bash
git status
# 변경 있으면 커밋, 없으면 스킵
```

---

## Self-Review 결과

**1. 스펙 커버리지:**
- ✅ 공식 (spec §3) → Task 1
- ✅ 표시 위치 (spec §4): /players → Task 11, /players/{name} → Task 12, /leaderboard → Tasks 4+13, /compare → Tasks 8+14, /maps → Task 16, /matches → Task 15
- ✅ 구현 스코프 (spec §5): metrics.py → Task 1, queries.py → Tasks 2-8, analytics.py → Task 9, templates → Tasks 11-16, i18n → Task 10, AGENTS.md → Task 17
- ✅ TODO (가중치 재튜닝) → spec에 기록됨 (구현 아님, 연구 TODO)

**2. 플레이스홀더 스캔:** TBD/TODO 없음 (TODO는 스펙의 연구 메모이지 플랜 단계 아님). ✅

**3. 타입 일관성:**
- `compute_rds(kills, assists, first_kill, lone_wolf_win, adr, deaths)` — Task 1 정의, Tasks 2/3/5/8/9에서 동일 시그니처 사용. ✅
- `all_snd_metrics(kills, assists, first_kill, lone_wolf_win, adr, deaths)` — Task 1 정의, Tasks 2/3/5/8에서 동일 사용. ✅
- `rds` 키 — 모든 데이터 계층(queries/analytics)과 템플릿에서 일관. ✅
- `avg_rds` 키 — match_history(Task 6)와 맵 쿼리(Task 7)에서 일관. ✅

**4. 모호성 점검:** Task 14(complete.html)와 Task 12(player_detail JS 라벨)는 기존 코드 구조 확인 단계를 포함 — 정확한 줄 위치는 렌더링 시점에 확인하도록 가드 추가됨. ✅
