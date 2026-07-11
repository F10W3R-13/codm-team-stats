# P3 품질 수정 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 버그 감사 보고서의 P3(⚪) 품질 항목 수정. 기능 영향 없는 유지보수 부채 정리.

**Architecture:** 템플릿/차트 그룹, 데드 코드 그룹, API 현대화 그룹으로 분리. 각 그룹 끝에 검증. systematic-debugging은 정확성 버그가 아닌 품질 항목이므로, 근인 분석보다는 "회귀 없음" 검증에 중점.

**Tech Stack:** Python, Jinja2, Chart.js, SQLite/Postgres.

## Global Constraints
- AGENTS.md §8: 인라인 스타일 금지, Chart.js는 TDS 객체 + `_onThemeChange` 콜백, `_chartRegistry` 등록.
- i18n: 키 삭제 시 세 언어(_ko/_en/_es) 동기화, `pytest test_i18n.py`로 검증.
- AGENTS.md 자체도 문서 드리프트 수정 대상(⚪-26).

---

### Task 1: ⚪-21 + ⚪-24 compare 차트 라벨 번역 + 델타 색상 방향

**Files:**
- Modify: `queries.py:1117-1120` (compare_players chart 데이터에 번역 라벨 추가)
- Modify: `templates/compare.html:89-95` (델타 색상 higher_better 반영), `:123,133` (차트 라벨)

**문제:**
- ⚪-21: 레이더 차트 축이 i18n 키(`zcs_label`, `m_dpd` 등)로 표시. 표 헤더는 번역하나 차트는 미번역.
- ⚪-24: 델타(Δ) 색상이 `d > 0` → 녹색. 데스(lower-better)에서 더 많이 죽은 선수가 녹색. `winner-cell`과 모순.

**근인:**
- 21: `chart.append({"metric": label_key, ...})` — label_key(i18n 키)를 그대로 사용. JS에서 번역 사전 접근 불가.
- 24: 델타 색상 로직이 `higher_better`를 무시.

**패턴 분석:**
- 21: 서버에서 `label`(번역된 텍스트)을 추가로 제공. `compare_players`는 i18n에 접근 불가하므로, `web_api.py`의 render 시점에서 `t` 사전으로 chart의 label_key를 번역해 chart에 `label` 필드 추가. 또는 더 간단: compare_players가 이미 `label_key`를 반환하므로, 템플릿의 `t` 사전을 JS에 주입.
  - **선택**: JS에 `t` 사전을 JSON으로 주입하고, `labels = chartData.map(d => t[d.metric] || d.metric)`. 이게 서버 변경 최소.
- 24: `row.higher_better`가 이미 rows에 있음. 델타 색상을 `higher_better` 기반으로: `(higher_better and d>0) or (not higher_better and d<0)` → up(녹색).

**Interfaces:**
- Consumes: `data.rows` (higher_better 포함), `data.chart` (metric=label_key), `t` (i18n 사전)
- Produces: 번역된 차트 라벨, 방향 일관된 델타 색상

- [ ] **Step 1: compare.html 델타 색상 higher_better 반영**

`compare.html:89-95` 수정:
```html
<!-- 수정 전: -->
<td class="num muted">
    {% if row.a is not none and row.b is not none %}
        {% set d = (row.a - row.b) | round(1) %}
        <span class="delta-{{ 'up' if d > 0 else ('down' if d < 0 else 'flat') }}">
            {{ '+' if d > 0 }}{{ d }}
        </span>
    {% else %}-{% endif %}
</td>

<!-- 수정 후: -->
<td class="num muted">
    {% if row.a is not none and row.b is not none %}
        {% set d = (row.a - row.b) | round(1) %}
        {% set is_good = (row.higher_better and d > 0) or (not row.higher_better and d < 0) %}
        <span class="delta-{{ 'up' if is_good else ('down' if d != 0 else 'flat') }}">
            {{ '+' if d > 0 }}{{ d }}
        </span>
    {% else %}-{% endif %}
</td>
```

- [ ] **Step 2: compare.html 차트 라벨 번역 — JS에 t 사전 주입**

`compare.html:121-123` 수정:
```javascript
// 수정 전:
const chartData = {{ data.chart | tojson }};
const labels = chartData.map(d => d.metric);

// 수정 후:
const chartData = {{ data.chart | tojson }};
const i18nT = {{ t | tojson }};
const labels = chartData.map(d => i18nT[d.metric] || d.metric);
```

- [ ] **Step 3: 검증 — 템플릿 파싱 + chart label_key 확인**

```bash
python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates'))
t = env.get_template('compare.html')
src = t.environment.loader.get_source(env, 'compare.html')[0]
assert 'i18nT' in src, 'FAIL: i18nT not in compare.html'
assert 'higher_better' in src, 'FAIL: higher_better not in delta logic'
assert 'is_good' in src, 'FAIL: is_good logic missing'
print('compare.html: PASS')
"
```
Expected: 템플릿 파싱 성공, i18nT/higher_better/is_good 포함.

- [ ] **Step 4: Commit**

```bash
git add queries.py templates/compare.html
git commit -m "fix: compare 차트 라벨 번역 + 델타 색상 lower-better 반영"
```

---

### Task 2: ⚪-22 다크모드 차트 채우기색 갱신

**Files:**
- Modify: `templates/compare.html:157-160` (레이더 `_onThemeChange`), `templates/coaching_hub.html:342-351` (ZCS 차트 `_onThemeChange` 추가)

**문제:** dataset `backgroundColor` 하드코딩. `_onThemeChange`가 `borderColor`만 갱신. ZCS 차트는 콜백 미정의. AGENTS.md §8 위반.

**근인:** 테마 토글 시 채우기색 갱신 누락.

**패턴 분석:** `_onThemeChange`에서 `backgroundColor`도 토큰 기반 rgba로 갱신. `hexToRgba` 헬퍼가 있는지 확인(base.html).

- [ ] **Step 1: compare.html _onThemeChange에 backgroundColor 갱신 추가**

`compare.html:157-160` 수정:
```javascript
// 수정 전:
radarChart._onThemeChange = function(chart, tds) {
    if (chart.data.datasets[0]) chart.data.datasets[0].borderColor = tds.accent;
    if (chart.data.datasets[1]) chart.data.datasets[1].borderColor = tds.danger;
};

// 수정 후:
radarChart._onThemeChange = function(chart, tds) {
    if (chart.data.datasets[0]) {
        chart.data.datasets[0].borderColor = tds.accent;
        chart.data.datasets[0].backgroundColor = hexToRgba(tds.accent, 0.12);
    }
    if (chart.data.datasets[1]) {
        chart.data.datasets[1].borderColor = tds.danger;
        chart.data.datasets[1].backgroundColor = hexToRgba(tds.danger, 0.12);
    }
};
```
(주의: `hexToRgba`가 base.html에 정의되어 있는지 먼저 확인. 없으면 rgba 변환 로직을 인라인으로.)

- [ ] **Step 2: hexToRgba 존재 확인**

```bash
grep -n "hexToRgba\|function hexToRgba" templates/base.html templates/coaching_hub.html templates/player_detail.html
```
존재하면 재사용. 없으면 base.html에 추가하거나 인라인 구현.

- [ ] **Step 3: coaching_hub.html ZCS 차트에 _onThemeChange 추가**

`coaching_hub.html`의 ZCS 차트(zcsChart) 등록 후 콜백 추가:
```javascript
// zcsChart 생성 후:
zcsChart._onThemeChange = function(chart, tds) {
    chart.data.datasets[0].backgroundColor = hexToRgba(tds.accent, 0.08);
};
_chartRegistry.set('zcsChart', zcsChart);  // 이미 있으면 유지
```

- [ ] **Step 4: 검증 — 템플릿 파싱 + _onThemeChange 포함 확인**

```bash
python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates'))
for name in ['compare.html', 'coaching_hub.html']:
    src = env.get_template(name).environment.loader.get_source(env, name)[0]
    print(f'{name}: parsed OK')
# compare backgroundColor 갱신
src_c = env.get_template('compare.html').environment.loader.get_source(env, 'compare.html')[0]
assert 'backgroundColor = hexToRgba' in src_c, 'FAIL: compare backgroundColor not updated'
# coaching_hub zcsChart callback
src_h = env.get_template('coaching_hub.html').environment.loader.get_source(env, 'coaching_hub.html')[0]
assert 'zcsChart._onThemeChange' in src_h, 'FAIL: zcsChart callback missing'
print('PASS')
"
```

- [ ] **Step 5: Commit**

```bash
git add templates/compare.html templates/coaching_hub.html
git commit -m "fix: 다크모드 차트 채우기색 갱신 — _onThemeChange backgroundColor 추가"
```

---

### Task 3: ⚪-23 player_detail 인사이트 카드 숨김 시 fetch 차단

**Files:**
- Modify: `templates/player_detail.html:113, 117-131`

**문제:** 카드 숨김 조건 `{% if not insight and not stats.hp and not stats.snd %}`인데 fetch 스크립트는 항상 렌더. 숨겨진 카드에서 fetch 성공해도 display:none이라 안 보임.

**근인:** 카드 숨김과 fetch 스크립트 렌더링 조건이 독립적.

**수정:** fetch 스크립트를 `{% if stats.hp or stats.snd %}`로 감싸 HP/SND 있는 선수만 fetch.

- [ ] **Step 1: fetch 스크립트 조건부 렌더링**

`player_detail.html:117-131` — `{% else %}` 블록의 fetch 스크립트를 `{% if stats.hp or stats.snd %}`로 감쌈:
```html
{% else %}
  {% if stats.hp or stats.snd %}
  <p class="insight-loading">...</p>
  <script>
    // fetch 로직
  </script>
  {% endif %}
{% endif %}
```
정확한 구조는 Read로 확인 후 적용.

- [ ] **Step 2: 검증**

```bash
python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates'))
src = env.get_template('player_detail.html').environment.loader.get_source(env, 'player_detail.html')[0]
print('player_detail.html: parsed OK')
"
```

- [ ] **Step 3: Commit**

```bash
git add templates/player_detail.html
git commit -m "fix: player_detail 인사이트 카드 숨김 시 fetch 차단 — 불필요한 API 호출 제거"
```

---

### Task 4: ⚪-26 team_insight/team_insights_data 데드 코드 + i18n + AGENTS.md

**Files:**
- Modify: `analytics_insights.py:200-235` (team_insight 함수 삭제), `analytics.py:324-345` (team_insights_data 함수 삭제)
- Modify: `i18n/_ko.py:106-108`, `i18n/_en.py:98-100`, `i18n/_es.py:98-100` (team_insights_* 키 3개 삭제)
- Modify: `AGENTS.md` (team_insight 잔존 문구 수정)

**문제:** 두 함수 어디서도 호출 안 됨. i18n 키 3개×3언어 잔류. AGENTS.md:93에 "coaching_hub 호환성 위해 잔존"이라 적혀있으나 실제 의존 없음.

**근인:** `/insights` 탭 삭제 시 함수/키를 안 지움.

**Phase 1 (근인 재확인):** 삭제 전 다시 grep으로 호출처 0건 확인.

- [ ] **Step 1: 호출처 재확인 (0건이어야 삭제)**

```bash
grep -rn "team_insight\b\|team_insights_data" --include="*.py" --include="*.html" | grep -v "^test_\|def team_insight"
# def 라인만 나와야 함 (호출처 0건)
```

- [ ] **Step 2: analytics_insights.py에서 team_insight 함수 삭제**

`team_insight` 함수 전체(200-235 부근) 삭제.

- [ ] **Step 3: analytics.py에서 team_insights_data 함수 삭제**

`team_insights_data` 함수 전체(324-345 부근) 삭제.

- [ ] **Step 4: i18n 3언어에서 team_insights_* 키 3개 삭제**

`_ko.py:106-108`, `_en.py:98-100`, `_es.py:98-100` — 각각 3개 키 삭제.

- [ ] **Step 5: AGENTS.md team_insight 문구 수정**

`AGENTS.md`의 `team_insights_data()`/`team_insight()` 관련 문구(§6 데이터 현황 메모 등)를 찾아 "삭제됨"으로 수정 또는 제거.

- [ ] **Step 6: 검증**

```bash
pytest test_i18n.py -q
# 5 passed 나와야 (키 동기화 OK)
python -c "import analytics, analytics_insights; print('import OK')"
grep -rn "team_insight" --include="*.py" --include="*.html"
# def 라인 0건 (완전 삭제)
```

- [ ] **Step 7: Commit**

```bash
git add analytics_insights.py analytics.py i18n/ AGENTS.md
git commit -m "refactor: team_insight/team_insights_data 데드 코드 + i18n 키 삭제"
```

---

### Task 5: ⚪-27 li 미사용 변수 6곳 + ⚪-30 소소한 (top_p, 타입힌트)

**Files:**
- Modify: `analytics_insights.py` (li 할당 6곳 중 미사용 삭제 — trend_insight만 사용)
- Modify: `bot.py:78` (top_p=0 제거)
- Modify: `analytics.py:508` (coaching_hub 타입힌트 int → int|None)

**문제:**
- 27: `li = _lang_instruction(lang)` 6곳에서 할당 후 미사용. trend_insight만 사용.
- 30: `top_p=0`가 `temperature=0`과 중복(OpenAI 권장: 둘 중 하나만). coaching_hub 타입힌트 거짓.

- [ ] **Step 1: li 사용처 정확히 파악**

```bash
grep -n "li = _lang_instruction\|{li}\|li}" analytics_insights.py
# trend_insight만 li를 실제 사용하는지 확인
```

- [ ] **Step 2: 미사용 li 할당 6곳 삭제**

trend_insight 외 6개 함수에서 `li = _lang_instruction(lang)` 라인 삭제.

- [ ] **Step 3: bot.py top_p=0 제거**

`bot.py:78`의 `top_p=0,` 라인 삭제.

- [ ] **Step 4: analytics.py coaching_hub 타입힌트 수정**

`analytics.py:508`: `recent_matches: int = 10` → `recent_matches: "int | None" = 10` (Python 3.9 호환성 위해 문자열 어노테이션).

- [ ] **Step 5: 검증**

```bash
DISCORD_BOT_TOKEN=dummy OPENAI_API_KEY=dummy python -c "import bot, analytics, analytics_insights; print('import OK')"
grep -c "li = _lang_instruction" analytics_insights.py
# 1이어야 함 (trend_insight만)
grep -c "top_p" bot.py
# 0이어야 함 (주석 제외)
```

- [ ] **Step 6: Commit**

```bash
git add analytics_insights.py bot.py analytics.py
git commit -m "refactor: li 미사용 변수 제거 + top_p 중복 제거 + 타입힌트 정정"
```

---

### Task 6: ⚪-28 asyncio.get_event_loop → get_running_loop

**Files:**
- Modify: `web_api.py:261, 277, 294, 321, 477`

**문제:** Python 3.10+ deprecated. 러닝 루프 안이므로 `get_running_loop()`가 안전.

- [ ] **Step 1: 모든 get_event_loop → get_running_loop 교체**

```bash
# replace_all로 일괄 교체
```

- [ ] **Step 2: 검증**

```bash
DISCORD_BOT_TOKEN=dummy OPENAI_API_KEY=dummy python -c "import web_api; print('import OK')"
grep -c "get_event_loop" web_api.py
# 0이어야 함
```

- [ ] **Step 3: Commit**

```bash
git add web_api.py
git commit -m "refactor: asyncio.get_event_loop → get_running_loop (Python 3.10+ deprecated)"
```

---

### Task 7: ⚪-29 N+1 쿼리 — 허브 players_list + ⚪-30 잔류 주석 정리

**Files:**
- Modify: `web_api.py:94-101` (players_list N+1)
- Modify: `db.py:203-205` (_adapt_params — 이미 import OK라면 현상 유지 또는 docstring 수정)

**문제:**
- 29: 허브에서 선수마다 `get_player_id` 개별 호출. 게다가 `web_api.py:95` 주석이 P1 수정 전 잔재("all_players_overview의 id는 metrics ID")로 거짓.
- 30: `_adapt_params` no-op (docstring 거짓).

**근인 (29):** `all_players_overview`가 player DB id를 안 반환해서 개별 조회 필요했음.

**Phase 2 (패턴):** P1에서 `all_hp_metrics`의 `id` 키를 제거했으므로, 이제 `all_players_overview`에 `id` 컬럼(players 테이블 PK)을 추가하면 개별 조회 불필요.

- [ ] **Step 1: all_players_overview에 players.id 추가**

`queries.py`의 `all_players_overview` SQL에 `p.id`를 SELECT 추가:
```sql
SELECT p.id, p.name, ...
```
정확한 위치는 Read로 확인 (342-353, 355-365 부근).

- [ ] **Step 2: web_api.py players_list N+1 제거 + 거짓 주석 정리**

`web_api.py:94-101` 수정:
```python
# 수정 전:
data["players_list"] = [
    {"id": pid, "name": p["name"]}
    for p in queries.all_players_overview("HP")
    for pid in [queries.get_player_id(p["name"])]
    if pid
] if is_admin else []

# 수정 후:
data["players_list"] = [
    {"id": p["id"], "name": p["name"]}
    for p in queries.all_players_overview("HP")
] if is_admin else []
```
주석도 제거(P1로 id 키 함정 해결됨).

- [ ] **Step 3: _adapt_params docstring 정정 또는 제거**

`db.py:206` — `_adapt_params`가 no-op. docstring이 거짓("psycopg2는 단일 param을 튜플로..."). 실제로 필요 없다면 주석만 정정:
```python
def _adapt_params(params):
    """현재는 변환 불필요 (SQLite/Postgres 양쪽 같은 params 형식 사용). 향후方言 차이 시 확장 지점."""
    return params
```

- [ ] **Step 4: 검증**

```bash
DISCORD_BOT_TOKEN=dummy OPENAI_API_KEY=dummy python -c "
import queries, web_api
# all_players_overview에 id 포함 확인
players = queries.all_players_overview('HP')
assert 'id' in players[0], f'FAIL: id missing. keys: {list(players[0].keys())}'
print(f'players[0] id: {players[0][\"id\"]}, name: {players[0][\"name\"]}')
print('PASS')
"
```

- [ ] **Step 5: Commit**

```bash
git add queries.py web_api.py db.py
git commit -m "perf: 허브 players_list N+1 제거 + _adapt_params docstring 정정"
```

---

### Task 8: ⚪-30 나머지 — win_loss_summary 재귀, admin/notes int, mode-toggle-group

**Files:**
- Modify: `queries.py:999-1003` (win_loss_summary 재귀 → 단일 GROUP BY)
- Modify: `web_api.py` (admin/notes int 변환 — 위치 확인 필요)
- Modify: `templates/player_detail.html:138` (mode-toggle-group 클래스 제거 또는 정의)

**문제:**
- win_loss_summary: mode=None 시 HP/SND 각각 재귀 호출 → 커넥션 3개.
- admin/notes: int() 변환 예외 미처리 (보고서에선 :587-588 이었으나 현재 위치 확인 필요).
- mode-toggle-group: 미정의 CSS 클래스.

- [ ] **Step 1: win_loss_summary 단일 쿼리 통합**

`queries.py:963-1003` — `by_mode` 부분을 재귀 대신 단일 `GROUP BY mode` 쿼리로:
```python
# 수정 전: mode=None일 때 HP, SND 각각 재귀 호출
# 수정 후: mode=None일 때 GROUP BY mode 단일 쿼리
```
정확한 구조는 Read로 확인 후 적용.

- [ ] **Step 2: admin/notes int 변환 처리**

`web_api.py`의 `/admin/notes` 라우트 찾아 int() 변환에 try/except 추가 (또는 이미 처리되어 있으면 스킵).

- [ ] **Step 3: mode-toggle-group 클래스 정리**

`player_detail.html:138` — 클래스가 미사용이면 제거, 또는 base.html에 정의 추가. 더 단순한 건 클래스명 제거.

- [ ] **Step 4: 검증**

```bash
DISCORD_BOT_TOKEN=dummy OPENAI_API_KEY=dummy python -c "
import queries
# win_loss_summary mode=None 정상 작동
r = queries.win_loss_summary(None)
print(f'mode=None result keys: {list(r.keys()) if isinstance(r, dict) else type(r)}')
print('PASS')
"
```

- [ ] **Step 5: Commit**

```bash
git add queries.py web_api.py templates/player_detail.html
git commit -m "refactor: win_loss_summary 재귀→단일쿼리 + admin/notes int 처리 + mode-toggle-group 정리"
```

---

## Self-Review

**1. Spec coverage:** P3 ⚪-21~30全覆盖. ⚪-25는 이미 해결됨(진단 로그 제거됨). ✅

**2. Placeholder scan:** 각 Step은 실제 코드 기반. "Read로 확인" 부분은 줄번호 밀림 대비 — placeholder 아님. ✅

**3. Type consistency:**
- compare chart: `metric` = label_key(i18n 키), JS에서 `i18nT[d.metric]`로 번역. `t` 사전이 이미 render에 주입됨.
- win_loss_summary: 반환 구조 동일 유지 필요 (재귀 결과와 단일 쿼리 결과가 같은 형식).
- ✅

**리스크:**
- Task 2: hexToRgba 존재 여부 미확인 — Step 2에서 확인.
- Task 7: all_players_overview에 id 추가 시 다른 소비자(team_averages 등)에 영향 — team_averages는 id를 평균에 포함하므로, id 컬럼 추가 시 집계에서 제외 처리 필요 확인.
- Task 8: win_loss_summary 반환 구조 변경 시 web_api 호출처 확인 필요.
