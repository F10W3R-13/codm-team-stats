# 선수 맵별 성적 HP/SND 토글 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 선수 상세 페이지의 맵별 성적 히트맵을 HP 5개 맵에서 SND 맵까지 확장 — 카드 내 모드 토글로 HP/SND 전환, SND는 RDS ±% 기반.

**Architecture:** `queries.player_map_breakdown`에 `mode` 파라미터를 추가해 HP(ZCS)/SND(RDS) 쿼리를 분기. 반환 키를 `zcs`/`zcs_pct`에서 `metric`/`metric_pct`로 통일해 템플릿이 mode 무관하게 동작. `web_api.py`는 HP/SND 두 번 호출 + `_heat_class` 헬퍼로 색 등급 적용. 템플릿은 카드 내 토글 버튼 + HP/SND 패널 전환(JS).

**Tech Stack:** Python (FastAPI, SQLite/Postgres), Jinja2, vanilla JS (토글), CSS 토큰(base.html). 의존성 추가 없음.

## Global Constraints

- **RDS 공식 고정** (AGENTS.md): `max(0, 4.1·K + 3.5·A + 14·FK + 20·LWW + 0.12·ADR − 5·D)`. metrics.py `compute_rds`와 정확히 일치.
- **ZCS 공식 고정**: `max(0, 1.1·OBJ + 8·CapKill + 4.1·K − 5·D)`.
- **DB mode 값**: `"HP"`, `"SND"`. SND 맵 데이터: Meltdown(2), Firing Range(1), Coastal(1).
- **SND min_matches = 2** (HP는 기존 5 유지).
- **Postgres 호환**: `_adapt_sql`이 `MAX(0,...)` → `GREATEST`, `?` → `%s` 변환. `AVG(MAX(0,...))` 중첩 괄호는 이미 검증된 패턴.
- **인라인 스타일 금지** (AGENTS.md): `style="display:none"` (Jinja 조건부)만 예외 허용. 색/레이아웃은 클래스.
- **i18n 3개국어 키 동일성**: `test_i18n.py`가 ko/en/es 키셋 강제. 신규 키는 3개 언어 모두 추가.
- **Jinja2 vs JS 충돌 주의**: `{{ }}` 안에 JS 연산자 금지. 토글 JS는 순수 `<script>` 블록.

**Spec:** `docs/superpowers/specs/2026-07-12-player-map-breakdown-snd-design.md`

---

## File Structure

| 파일 | 유형 | 책임 |
|---|---|---|
| `queries.py` | 수정 | `player_map_breakdown`에 `mode` 파라미터, 쿼리 분기, `_player_overall_rds()` 신규, 반환 키 `metric`/`metric_pct` 통일 |
| `web_api.py` | 수정 | player_detail 라우트: SND 호출 추가, `_heat_class` 헬퍼, `player_maps_snd` 렌더 전달 |
| `templates/player_detail.html` | 수정 | 맵 카드 HP/SND 토글 구조 재구성, `metric`/`metric_pct` 키, 토글 JS |
| `templates/base.html` | 수정 | `.mode-toggle`/`.mode-toggle__btn` CSS 클래스 |
| `i18n/_ko.py`, `_en.py`, `_es.py` | 수정 | 신규 3키 (player_maps_help_snd, player_maps_no_data_hp/snd) |
| `test_player_maps.py` | 신규 | `player_map_breakdown` HP/SND 분기 + `_heat_class` 단위테스트 |

---

## Task 1: `queries.py` — `player_map_breakdown` mode 확장 + `_player_overall_rds`

**Files:**
- Modify: `queries.py:868-912` (`player_map_breakdown`) + `queries.py:914-922` (`_player_overall_zcs` 근처에 `_player_overall_rds` 추가)
- Test: `test_player_maps.py` (신규)

**Interfaces:**
- Consumes: 없음 (DB만)
- Produces:
  - `player_map_breakdown(player_id: int, mode: str = "HP", min_matches: int = 5) -> list` — 시그니처 변경. 반환 dict 키: `map_name`, `matches`, `metric`, `metric_pct` (기존 `zcs`/`zcs_pct` 대체).
  - `_player_overall_rds(player_id: int) -> float | None` — 신규. `_player_overall_zcs`와 대칭.

- [ ] **Step 1: Write the failing test**

`test_player_maps.py`:

```python
# player_map_breakdown mode 확장 + _heat_class 단위테스트
#
# 실행: pytest test_player_maps.py -v
#
# 검증:
#  - player_map_breakdown HP 모드: 기존 동작, metric/metric_pct 키
#  - player_map_breakdown SND 모드: RDS 기반, metric/metric_pct 키
#  - mode 기본값 "HP" (하위 호환)
#  - 빈 결과 (데이터 없는 선수) → 빈 리스트
#  - _player_overall_rds 존재 + 정상 동작

import queries


def _any_player_with_hp():
    """HP 데이터 있는 임의 선수 ID."""
    import db
    with db.get_conn() as conn:
        r = conn.execute("SELECT DISTINCT player_id FROM player_stats_hp LIMIT 1").fetchone()
    return r["player_id"] if r else None


def _any_player_with_snd():
    """SND 데이터 있는 임의 선수 ID."""
    import db
    with db.get_conn() as conn:
        r = conn.execute("SELECT DISTINCT player_id FROM player_stats_snd LIMIT 1").fetchone()
    return r["player_id"] if r else None


def test_hp_mode_returns_metric_keys():
    """HP 모드가 metric/metric_pct 키를 반환 (zcs/zcs_pct 아님)."""
    pid = _any_player_with_hp()
    if pid is None:
        return  # 로컬 DB에 HP 데이터 없음 — 스킵
    result = queries.player_map_breakdown(pid, mode="HP", min_matches=1)
    if not result:
        return  # min_matches 커버 데이터 없음
    assert "metric" in result[0]
    assert "metric_pct" in result[0]
    assert "zcs" not in result[0]  # 구 키 제거
    assert "zcs_pct" not in result[0]


def test_default_mode_is_hp():
    """mode 생략 시 HP (하위 호환)."""
    pid = _any_player_with_hp()
    if pid is None:
        return
    explicit = queries.player_map_breakdown(pid, mode="HP", min_matches=1)
    default = queries.player_map_breakdown(pid, min_matches=1)
    assert explicit == default


def test_snd_mode_returns_metric_keys():
    """SND 모드가 metric/metric_pct 키를 반환."""
    pid = _any_player_with_snd()
    if pid is None:
        return
    result = queries.player_map_breakdown(pid, mode="SND", min_matches=1)
    if not result:
        return
    assert "metric" in result[0]
    assert "metric_pct" in result[0]
    # SND 맵 이름 포함 확인 (Meltdown 등)
    map_names = [r["map_name"] for r in result]
    assert any(m for m in map_names)


def test_empty_result_for_nonexistent_player():
    """존재하지 않는 선수 → 빈 리스트 (예외 X)."""
    result = queries.player_map_breakdown(999999, mode="HP", min_matches=1)
    assert result == []
    result_snd = queries.player_map_breakdown(999999, mode="SND", min_matches=1)
    assert result_snd == []


def test_player_overall_rds_exists():
    """_player_overall_rds 함수 존재 + SND 선수에 대해 숫자 반환."""
    assert hasattr(queries, "_player_overall_rds")
    pid = _any_player_with_snd()
    if pid is None:
        return
    val = queries._player_overall_rds(pid)
    # SND 데이터 있으면 숫자 (데이터 부족 시 None도 허용)
    if val is not None:
        assert isinstance(val, (int, float))
        assert val >= 0  # RDS는 max(0,...)라 음수 불가


def test_heat_class_thresholds():
    """_heat_class (web_api에 추가 예정) 임계값 — 이 테스트는 Task 2에서 web_api 가져와야.
    여기서는 queries에 국한. 대신 player_map_breakdown 결과에 heat_class 없음 확인."""
    pid = _any_player_with_hp()
    if pid is None:
        return
    result = queries.player_map_breakdown(pid, mode="HP", min_matches=1)
    if result:
        assert "heat_class" not in result[0]  # heat_class는 web_api에서 부여
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest test_player_maps.py -v
```
Expected: FAIL — `TypeError: player_map_breakdown() got an unexpected keyword argument 'mode'` 및 `AttributeError: _player_overall_rds`.

- [ ] **Step 3: Rewrite `player_map_breakdown` + add `_player_overall_rds`**

`queries.py:868-912` (기존 `player_map_breakdown`)을 아래로 교체:

```python
def player_map_breakdown(player_id: int, mode: str = "HP", min_matches: int = 5) -> list:
    """특정 선수의 맵별 성적 — 본인 전체 평균 대비 ±%.

    mode="HP": ZCS(=max(0, 1.1·obj_time + 8·capture_kill + 4.1·kills - 5·deaths)) 기준.
    mode="SND": RDS(=max(0, 4.1·kills + 3.5·assists + 14·first_kill + 20·lone_wolf_win
                        + 0.12·adr - 5·deaths)) 기준.
    반환: [{map_name, matches, metric, metric_pct}, ...]
      metric: 그 맵에서의 평균 ZCS(HP) 또는 RDS(SND)
      metric_pct: 본인 전체 평균 대비 % (양수=강함, 음수=약함)
    min_matches 미만 맵은 신뢰도 낮아 제외.
    히트맵 색은 web_api의 _heat_class()가 metric_pct 크기로 부여.
    """
    if mode == "SND":
        sql = """SELECT LOWER(m.map_name) map_name,
                        COUNT(*) matches,
                        ROUND(AVG(MAX(0, 4.1*s.kills + 3.5*s.assists + 14*s.first_kill
                                    + 20*s.lone_wolf_win + 0.12*s.adr - 5*s.deaths)),1) metric
                 FROM player_stats_snd s
                 JOIN matches m ON m.id=s.match_id
                 WHERE s.player_id=? AND m.map_name IS NOT NULL AND m.map_name != ''
                   AND m.mode='SND'
                 GROUP BY LOWER(m.map_name)
                 HAVING COUNT(*) >= ?
                 ORDER BY metric DESC"""
        overall = _player_overall_rds(player_id)
    else:  # HP (기본)
        sql = """SELECT LOWER(m.map_name) map_name,
                        COUNT(*) matches,
                        ROUND(AVG(MAX(0, 1.1*s.obj_time + 8*s.capture_kill + 4.1*s.kills - 5*s.deaths)),1) metric
                 FROM player_stats_hp s
                 JOIN matches m ON m.id=s.match_id
                 WHERE s.player_id=? AND m.map_name IS NOT NULL AND m.map_name != ''
                   AND m.mode='HP'
                 GROUP BY LOWER(m.map_name)
                 HAVING COUNT(*) >= ?
                 ORDER BY metric DESC"""
        overall = _player_overall_zcs(player_id)

    with db.get_conn() as conn:
        rows = [dict(r) for r in conn.execute(db._adapt_sql(sql), (player_id, min_matches)).fetchall()]
    # Postgres Decimal → float
    for r in rows:
        for k, v in list(r.items()):
            if hasattr(v, "as_tuple"):
                r[k] = float(v)
    if not rows:
        return []
    if not overall:
        return []
    out = []
    for r in rows:
        pct = round((r["metric"] - overall) / overall * 100, 1) if overall else 0
        out.append({
            "map_name": r["map_name"].strip().title(),
            "matches": r["matches"], "metric": r["metric"],
            "metric_pct": pct,
        })
    # ±% 내림차순 (강한 맵이 위로)
    out.sort(key=lambda x: x["metric_pct"], reverse=True)
    return out
```

그리고 `_player_overall_zcs`(`queries.py:914-922`) 바로 뒤에 `_player_overall_rds` 추가:

```python
def _player_overall_rds(player_id: int) -> float:
    """선수의 전체 평균 RDS (player_map_breakdown SND 내부용).

    RDS = max(0, 4.1·kills + 3.5·assists + 14·first_kill + 20·lone_wolf_win
              + 0.12·adr - 5·deaths)
    """
    sql = ("SELECT ROUND(AVG(MAX(0, 4.1*kills + 3.5*assists + 14*first_kill "
           "+ 20*lone_wolf_win + 0.12*adr - 5*deaths)),1) rds "
           "FROM player_stats_snd WHERE player_id=?")
    with db.get_conn() as conn:
        r = conn.execute(db._adapt_sql(sql), (player_id,)).fetchone()
    if r and r["rds"] is not None:
        v = r["rds"]
        return float(v) if hasattr(v, "as_tuple") else v
    return None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest test_player_maps.py -v
```
Expected: PASS (6개 테스트). 단 로컬 DB에 player_stats_hp/snd 데이터가 있어야 일부 테스트가 의미 있음 — 데이터 없는 테스트는 early return으로 스킵.

- [ ] **Step 5: Commit**

```bash
git add queries.py test_player_maps.py
git commit -m "feat: player_map_breakdown mode 확장 (SND RDS) + _player_overall_rds"
```

---

## Task 2: `web_api.py` — SND 호출 + `_heat_class` 헬퍼

**Files:**
- Modify: `web_api.py:147-160` (player_detail 라우트 맵 호출부 + render)

**Interfaces:**
- Consumes: `queries.player_map_breakdown(player_id, mode, min_matches)` (Task 1)
- Produces:
  - `_heat_class(pct: float) -> str` — 모듈 헬퍼 (HP/SND 공용).
  - player_detail 라우트가 `player_maps_snd` 컨텍스트 변수 전달.

- [ ] **Step 1: Add `_heat_class` helper**

`web_api.py`의 import/상수 영역 (함수 정의 시작 전, `BASE_DIR` 근처 또는 라우트 함수들 직전)에 추가. 위치: `db.init_db()` (37 라인) 이후, 첫 `@app` 라우트 전. 적절한 위치를 찾기 위해 `BASE_DIR` 정의 직후에 배치:

```python
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
```

- [ ] **Step 2: Rewrite player_detail 맵 호출부**

`web_api.py:147-151` (기존 `player_maps` 호출 + heat_class 인라인 루프)을 아래로 교체:

**변경 전:**
```python
    # 맵별 성적 (HP 전용) — 본인 평균 대비 강한/약한 맵
    player_maps = queries.player_map_breakdown(pid, min_matches=5) if stats["hp"] else []
    # 히트맵 색 클래스 — zcs_pct 크기에 비례한 5단계 (절대 임계값 아님, 맵 간 상대 차이 표현)
    for m in player_maps:
        p = m["zcs_pct"]
        m["heat_class"] = ("heat-2" if p >= 15 else "heat-1" if p >= 5
                           else "heat--2" if p <= -15 else "heat--1" if p <= -5 else "heat-0")
```

**변경 후:**
```python
    # 맵별 성적 — HP(ZCS)/SND(RDS) 본인 평균 대비 강한/약은 맵
    player_maps = queries.player_map_breakdown(pid, mode="HP", min_matches=5) if stats["hp"] else []
    player_maps_snd = queries.player_map_breakdown(pid, mode="SND", min_matches=2) if stats["snd"] else []
    # 히트맵 색 클래스 — metric_pct 크기에 비례한 5단계 (HP/SND 공용)
    for m in player_maps:
        m["heat_class"] = _heat_class(m["metric_pct"])
    for m in player_maps_snd:
        m["heat_class"] = _heat_class(m["metric_pct"])
```

- [ ] **Step 3: Add `player_maps_snd` to render call**

`web_api.py:155-160` (render 호출)에 `player_maps_snd` 추가:

**변경 전:**
```python
    return render(
        "player_detail.html", lang=lang,
        stats=stats, team_hp=team_hp,
        insight=insight, player_maps=player_maps,
    )
```

**변경 후:**
```python
    return render(
        "player_detail.html", lang=lang,
        stats=stats, team_hp=team_hp,
        insight=insight, player_maps=player_maps, player_maps_snd=player_maps_snd,
    )
```

- [ ] **Step 4: Verify import + 회귀**

```bash
DISCORD_BOT_TOKEN=dummy OPENAI_API_KEY=dummy python -c "
import web_api
print('_heat_class(20):', web_api._heat_class(20))
print('_heat_class(-20):', web_api._heat_class(-20))
print('_heat_class(0):', web_api._heat_class(0))
print('_heat_class(10):', web_api._heat_class(10))
print('_heat_class(-10):', web_api._heat_class(-10))
print('web_api import OK')
"
```
Expected: `_heat_class(20): heat-2`, `_heat_class(-20): heat--2`, `_heat_class(0): heat-0`, `_heat_class(10): heat-1`, `_heat_class(-10): heat--1`, `web_api import OK`.

- [ ] **Step 5: Commit**

```bash
git add web_api.py
git commit -m "feat: player_detail SND 맵 호출 + _heat_class 헬퍼 (HP/SND 공용)"
```

---

## Task 3: `i18n` — 신규 3키 (3개 언어)

**Files:**
- Modify: `i18n/_ko.py`, `i18n/_en.py`, `i18n/_es.py` (각 `player_maps_help` 근처)

**Interfaces:**
- Produces: 3개 신규 키 (`player_maps_help_snd`, `player_maps_no_data_hp`, `player_maps_no_data_snd`)가 3개 언어 모두에 추가.

- [ ] **Step 1: Add keys to `i18n/_ko.py`**

`player_maps_help` 키가 있는 위치(`i18n/_ko.py:81` 근처) 다음에 추가. 기존 키 사전에 같은 딕셔너리 블록 내에 3줄 추가:

```python
        "player_maps_help_snd": "이 선수의 SND 맵별 RDS (본인 평균 대비)",
        "player_maps_no_data_hp": "이 선수의 HP 맵 데이터가 부족합니다",
        "player_maps_no_data_snd": "이 선수의 SND 맵 데이터가 부족합니다",
```

(정확한 들여쓰기는 주변 키에 맞출 것 — 8-space 들여쓰기 패턴 확인.)

- [ ] **Step 2: Add same keys to `i18n/_en.py`**

동일 위치에:

```python
        "player_maps_help_snd": "This player's RDS by SND map (vs own average)",
        "player_maps_no_data_hp": "Not enough HP map data for this player",
        "player_maps_no_data_snd": "Not enough SND map data for this player",
```

- [ ] **Step 3: Add same keys to `i18n/_es.py`**

동일 위치에:

```python
        "player_maps_help_snd": "RDS por mapa SND (vs propio promedio)",
        "player_maps_no_data_hp": "Datos insuficientes de mapas HP",
        "player_maps_no_data_snd": "Datos insuficientes de mapas SND",
```

- [ ] **Step 4: Run i18n key equality test**

```bash
pytest test_i18n.py -v
```
Expected: PASS — 3개 언어 키셋 동일 (신규 3키 포함).

- [ ] **Step 5: Commit**

```bash
git add i18n/_ko.py i18n/_en.py i18n/_es.py
git commit -m "feat: i18n — player_maps SND/no_data 키 3개 (ko/en/es)"
```

---

## Task 4: `templates/player_detail.html` — 토글 카드 + JS

**Files:**
- Modify: `templates/player_detail.html:63-84` (기존 HP 맵 블록 교체) + 하단 `<script>` 추가

**Interfaces:**
- Consumes: `player_maps`, `player_maps_snd` 컨텍스트 변수 (Task 2), `metric`/`metric_pct`/`heat_class` 키, i18n 키 (Task 3)

- [ ] **Step 1: Replace map block with toggle structure**

`templates/player_detail.html:63-84` (기존 `{# ── 맵별 성적 히트맵 (HP 전용) ── #}` 블록 전체)을 아래로 교체:

**먼저 기존 블록 정확히 확인:**
```bash
sed -n '63,84p' templates/player_detail.html
```

**교체할 새 블록:**
```html
{# ── 맵별 성적 히트맵 (HP/SND 토글) ── #}
{% if player_maps or player_maps_snd %}
<div class="card section">
    <h2>🗺️ {{ t.player_maps_title }}</h2>

    {# 모드 토글 — HP/SND 둘 다 데이터 있을 때만 노출 #}
    {% if player_maps and player_maps_snd %}
    <div class="mode-toggle" data-mode-toggle>
        <button class="mode-toggle__btn active" data-mode="hp">
            <span class="badge hp">{{ t.mode_hp }}</span>
        </button>
        <button class="mode-toggle__btn" data-mode="snd">
            <span class="badge snd">{{ t.mode_snd }}</span>
        </button>
    </div>
    {% endif %}

    {# HP 패널 #}
    <div class="map-panel" data-map-panel="hp" {% if not player_maps %}style="display:none"{% endif %}>
        {% if player_maps %}
        <p class="muted stat-label">{{ t.player_maps_help }} ({{ t.zcs_label }} {{ stats.hp.zcs }})</p>
        <div class="map-heatmap">
            <div class="map-heatmap__bar">
                <span class="text-danger">{{ t.player_maps_weak }}</span>
                <span class="muted">{{ t.player_maps_avg }}</span>
                <span class="text-success">{{ t.player_maps_strong }}</span>
            </div>
            {% for m in player_maps %}
            <a href="/maps/{{ m.map_name }}?lang={{ lang }}" class="map-heat-row {{ m.heat_class }}">
                <span class="map-heat-row__name">{{ m.map_name }}</span>
                <span class="map-heat-row__zcs">{{ m.metric }}</span>
                <span class="map-heat-row__pct">{{ '+' if m.metric_pct > 0 }}{{ m.metric_pct }}%</span>
                <span class="muted map-heat-row__matches">{{ m.matches }} {{ t.matches }}</span>
            </a>
            {% endfor %}
        </div>
        {% else %}
        <p class="muted stat-label">{{ t.player_maps_no_data_hp }}</p>
        {% endif %}
    </div>

    {# SND 패널 #}
    <div class="map-panel" data-map-panel="snd" {% if not player_maps_snd %}style="display:none"{% endif %}>
        {% if player_maps_snd %}
        <p class="muted stat-label">{{ t.player_maps_help_snd }} ({{ t.rds_label }} {{ stats.snd.rds if stats.snd else '-' }})</p>
        <div class="map-heatmap">
            <div class="map-heatmap__bar">
                <span class="text-danger">{{ t.player_maps_weak }}</span>
                <span class="muted">{{ t.player_maps_avg }}</span>
                <span class="text-success">{{ t.player_maps_strong }}</span>
            </div>
            {% for m in player_maps_snd %}
            <a href="/maps/{{ m.map_name }}?mode=SND&lang={{ lang }}" class="map-heat-row {{ m.heat_class }}">
                <span class="map-heat-row__name">{{ m.map_name }}</span>
                <span class="map-heat-row__zcs">{{ m.metric }}</span>
                <span class="map-heat-row__pct">{{ '+' if m.metric_pct > 0 }}{{ m.metric_pct }}%</span>
                <span class="muted map-heat-row__matches">{{ m.matches }} {{ t.matches }}</span>
            </a>
            {% endfor %}
        </div>
        {% else %}
        <p class="muted stat-label">{{ t.player_maps_no_data_snd }}</p>
        {% endif %}
    </div>
</div>
{% endif %}
```

**주의**: SND 패널의 `stats.snd.rds` 참조 — `stats.snd`가 None일 수 있어 `stats.snd.rds if stats.snd else '-'` 로 안전 처리.

- [ ] **Step 2: Add toggle JS**

`templates/player_detail.html` 하단 (기존 `<script>` 블록이 있으면 그 안에, 없으면 `{% endblock %}` 또는 `</body>` 직전에 새 `<script>` 추가):

```html
<script>
// 맵 히트맵 HP/SND 모드 토글
document.querySelectorAll('[data-mode-toggle]').forEach(function(toggle) {
    toggle.addEventListener('click', function(e) {
        var btn = e.target.closest('[data-mode]');
        if (!btn) return;
        var mode = btn.dataset.mode;
        toggle.querySelectorAll('.mode-toggle__btn').forEach(function(b) {
            b.classList.toggle('active', b === btn);
        });
        var card = toggle.closest('.card');
        card.querySelectorAll('[data-map-panel]').forEach(function(panel) {
            panel.style.display = (panel.dataset.mapPanel === mode) ? '' : 'none';
        });
    });
});
</script>
```

- [ ] **Step 3: 렌더 smoke test (서버 기동 없이 템플릿 파싱만)**

```bash
DISCORD_BOT_TOKEN=dummy OPENAI_API_KEY=dummy python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates'))
t = env.get_template('player_detail.html')
# 최소 컨텍스트로 파싱 에러 없는지 확인
ctx = {
    't': {'player_maps_title': 'M', 'player_maps_help': 'h', 'player_maps_help_snd': 'hs',
          'player_maps_no_data_hp': 'nh', 'player_maps_no_data_snd': 'ns',
          'player_maps_weak': 'W', 'player_maps_avg': 'A', 'player_maps_strong': 'S',
          'mode_hp': 'HP', 'mode_snd': 'SND', 'zcs_label': 'Z', 'rds_label': 'R', 'matches': 'm'},
    'lang': 'ko', 'stats': {}, 'player_maps': [], 'player_maps_snd': [],
}
out = t.render(**ctx)
print('player_detail.html 파싱 OK, 길이:', len(out))
"
```
Expected: `player_detail.html 파싱 OK, 길이: <양수>` — TemplateSyntaxError 없음.

- [ ] **Step 4: Commit**

```bash
git add templates/player_detail.html
git commit -m "feat: player_detail 맵 히트맵 HP/SND 토글 + JS"
```

---

## Task 5: `templates/base.html` — CSS 클래스

**Files:**
- Modify: `templates/base.html` (`<style>` 블록 내, 기존 `.map-heat-row` 근처)

**Interfaces:**
- 없음 (스타일만)

- [ ] **Step 1: Locate insertion point**

```bash
grep -n "map-heat-row\|map-heatmap" templates/base.html | head -5
```
기존 `.map-heat-row` 정의 근처에 새 클래스 추가.

- [ ] **Step 2: Add CSS classes**

`templates/base.html`의 `<style>` 블록에서 `.map-heatmap`/`.map-heat-row` 정의 근처에 추가:

```css
.mode-toggle {
    display: inline-flex;
    gap: var(--space-1);
    margin-bottom: var(--space-3);
    border: 1px solid var(--border);
    border-radius: var(--radius-full);
    padding: var(--space-1);
    background: var(--surface);
}
.mode-toggle__btn {
    border: none;
    background: transparent;
    padding: var(--space-1) var(--space-3);
    border-radius: var(--radius-full);
    cursor: pointer;
    font: inherit;
    color: var(--muted);
    transition: background 0.15s, color 0.15s;
}
.mode-toggle__btn.active {
    background: var(--accent);
    color: var(--on-accent);
}
```

**토큰 사용 확인**: `--space-1`, `--space-3`, `--border`, `--radius-full`, `--surface`, `--muted`, `--accent`, `--on-accent` — 전부 AGENTS.md에 정의된 토큰. 인라인 값 금지 규칙 준수.

- [ ] **Step 3: Commit**

```bash
git add templates/base.html
git commit -m "feat: base.html — mode-toggle CSS 클래스 (HP/SND 토글 버튼)"
```

---

## Task 6: 최종 통합 검증

**Files:**
- 없음 (검증만)

- [ ] **Step 1: 전체 테스트 스위트**

```bash
pytest test_player_maps.py test_coaching_brain_loader.py test_prompt_context_domains.py test_insight_cache_fingerprint.py test_i18n.py -v
```
Expected: 전부 PASS.

- [ ] **Step 2: 엔드투엔드 — SND 데이터 있는 선수 페이지 렌더**

```bash
DISCORD_BOT_TOKEN=dummy OPENAI_API_KEY=dummy python -c "
import queries, db
# SND 데이터 있는 선수 찾기
with db.get_conn() as conn:
    r = conn.execute('SELECT DISTINCT player_id FROM player_stats_snd LIMIT 1').fetchone()
if not r:
    print('SND 데이터 없음 — 스킵')
else:
    pid = r['player_id']
    snd_maps = queries.player_map_breakdown(pid, mode='SND', min_matches=2)
    print('SND 맵 (min=2):', snd_maps)
    hp_maps = queries.player_map_breakdown(pid, mode='HP', min_matches=5)
    print('HP 맵 (min=5):', len(hp_maps), '개')
"
```
Expected: SND 맵 리스트(Meltdown 등) + HP 맵 개수. 예외 없음.

- [ ] **Step 3: 템플릿 렌더 — HP+SND 둘 다 있는 시나리오**

```bash
DISCORD_BOT_TOKEN=dummy OPENAI_API_KEY=dummy python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates'))
t = env.get_template('player_detail.html')
ctx = {
    't': {'player_maps_title': '맵별 성적', 'player_maps_help': '본인 평균 대비',
          'player_maps_help_snd': 'SND RDS', 'player_maps_no_data_hp': 'HP 없음',
          'player_maps_no_data_snd': 'SND 없음', 'player_maps_weak': '약함',
          'player_maps_avg': '평균', 'player_maps_strong': '강함',
          'mode_hp': 'HP', 'mode_snd': 'SND', 'zcs_label': 'ZCS', 'rds_label': 'RDS', 'matches': '매치'},
    'lang': 'ko',
    'stats': {'hp': {'zcs': 200}, 'snd': {'rds': 150}},
    'player_maps': [{'map_name': 'Combine', 'matches': 10, 'metric': 220, 'metric_pct': 10, 'heat_class': 'heat-1'}],
    'player_maps_snd': [{'map_name': 'Meltdown', 'matches': 2, 'metric': 140, 'metric_pct': -7, 'heat_class': 'heat--1'}],
}
out = t.render(**ctx)
assert 'data-mode-toggle' in out, '토글 버튼 없음 (둘 다 데이터 있는데)'
assert 'Meltdown' in out
assert 'Combine' in out
print('HP+SND 토글 시나리오 렌더 OK')
"
```
Expected: `HP+SND 토글 시나리오 렌더 OK` — 토글 버튼 + 두 패널 모두 렌더됨.

- [ ] **Step 4: git 상태 최종 확인**

```bash
git status
git log --oneline -6
```
Expected: clean working tree + 커밋 5개 (Task 1-5).

---

## 배포 후 확인 (로컬 불가 — AGENTS.md §3)

- Railway Postgres에서 SND 쿼리(`AVG(MAX(0, 4.1·K + ...))` 중첩 괄호) 정상 동작 — `_adapt_sql` 파서가 `GREATEST` 변환 처리 (이미 검증된 패턴).
- 실제 선수 페이지에서 HP/SND 토글 클릭 시 패널 전환 확인 (수동).

---

## Self-Review (작성자 점검)

**Spec coverage:**
- ✅ RDS ±% SND 맵 히트맵 → Task 1 (쿼리) + Task 4 (템플릿)
- ✅ 카드 내 모드 토글 → Task 4 (토글 버튼 + JS) + Task 5 (CSS)
- ✅ SND min_matches=2 → Task 2 (`player_map_breakdown(pid, mode="SND", min_matches=2)`)
- ✅ A안 기존 함수 확장 → Task 1 (`mode` 파라미터)
- ✅ metric/metric_pct 키 통일 → Task 1 (반환) + Task 4 (템플릿 참조)
- ✅ _heat_class 헬퍼 → Task 2
- ✅ i18n 3키 → Task 3
- ✅ 검증 → Task 6

**Placeholder scan:** 없음. 모든 step에 실제 코드/명령.

**Type consistency:**
- `player_map_breakdown(player_id, mode="HP", min_matches=5) -> list` — Task 1 정의, Task 2 호출 일관
- 반환 키 `metric`/`metric_pct` — Task 1 정의, Task 2 (heat_class 적용), Task 4 (템플릿 `m.metric`/`m.metric_pct`) 일관
- `_heat_class(pct) -> str` — Task 2 정의 후 player_detail 라우트에서 사용
- `_player_overall_rds(player_id) -> float | None` — Task 1 정의 후 `player_map_breakdown` SND 분기에서 호출
