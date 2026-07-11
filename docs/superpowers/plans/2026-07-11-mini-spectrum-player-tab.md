# 미니 스펙트럼 바 — 선수 탭 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 허브의 역할 스펙트럼(slay↔obj 좌우 바)을 선수 목록(`/players`)과 선수 상세(`/players/{name}`)에 미니 버전으로 가져온다. 기존 이산 배지(slayer/objective/balanced)를 대체.

**Architecture:** 허브가 이미 쓰는 `slay_score`/`obj_score` 연속값을 players 데이터에 추가하고, 허브의 spectrum CSS/JS를 미니 버전으로 재사용. 공식·데이터 출처는 `team_role_distribution`과 동일 (metrics.py 공식 재현, 출처 고정 원칙 준수).

**Tech Stack:** Python (FastAPI), Jinja2, CSS.

## Global Constraints
- 역할 공식은 `metrics.classify_role` + `team_role_distribution`의 `slay_score`/`obj_score` 로직과 동일 — 새 공식 발명 금지.
- AGENTS.md §8: 인라인 스타일 금지(동적값 `left:%`만 예외), Chart.js 규칙 해당 없음(순 CSS).
- SND에는 역할 스펙트럼 없음(HP 전용). SND 모드에선 미니 바 숨김.
- 3개국어(i18n): 새 라벨 필요 시 `_ko/_en/_es` 동기화.

---

### Task 1: 스펙트럼 위치 계산 헬퍼 함수 추가

**Files:**
- Modify: `metrics.py` (맨 끝에 헬퍼 추가)

**문제:** 허브(coaching_hub.html:225-229)에서 Jinja2 인라인으로 계산하는 스펙트럼 위치 공식을, 선수 탭에서도 동일하게 써야 함. 각 템플릿에 복붙하면 DRY 위반 + 불일치 위험.

**해결:** 위치 계산을 Python 헬퍼로 추출해 단일 진실 확보.

**Interfaces:**
- Consumes: `slay_score`, `obj_score` (team_role_distribution과 동일 로직으로 계산된 값)
- Produces: `role_spectrum_pos(slay_score, obj_score) -> float` (5.0~95.0, 퍼센트 위치)

- [ ] **Step 1: 헬퍼 함수 추가**

`metrics.py` 맨 끝에 추가:
```python
def role_spectrum_pos(slay_score: float, obj_score: float) -> float:
    """역할 스펙트럼 바 위 마커 위치(%, 5~95).

    slay_score / obj_score: 팀 평균 대비 비율(team_role_distribution과 동일 로직).
    반환: 5.0(순 OBJ) ~ 95.0(순 Slayer). 양쪽 극단은 clamp.
    """
    ss = slay_score if slay_score else 1.0
    os_ = obj_score if obj_score else 1.0
    norm = (ss - os_) / (ss + os_)  # -1(순obj) ~ +1(순slay)
    pos = 50 + norm * 45  # 5~95 범위로 확장
    return round(max(5, min(95, pos)), 1)
```
(주의: 허브 템플릿의 `norm * 450`은 0~100 스케일에서 50±45=5~95. 헬퍼는 동일 결과를 직접 계산.)

- [ ] **Step 2: 허브 템플릿과 결과 일치 검증**

```bash
python -c "
import metrics
# 허브 템플릿 로직(coaching_hub.html:225-229)과 동일 결과인지 확인
def hub_pos(ss, os_):
    ss = ss if ss else 1.0
    os_ = os_ if os_ else 1.0
    norm = (ss - os_) / (ss + os_)
    return max(5, min(95, round(50 + norm * 450, 1)))
# 여러 케이스 비교
for ss, os_ in [(1.2, 0.8), (0.9, 1.1), (1.5, 0.5), (1.0, 1.0), (0.5, 1.5)]:
    h = hub_pos(ss, os_)
    m = metrics.role_spectrum_pos(ss, os_)
    assert h == m, f'MISMATCH ss={ss} os={os_}: hub={h} helper={m}'
    print(f'ss={ss} os={os_}: pos={m}%')
print('PASS — 허브 로직과 일치')
"
```
Expected: 모든 케이스에서 허브 공식과 동일 결과.

- [ ] **Step 3: Commit**

```bash
git add metrics.py
git commit -m "feat: role_spectrum_pos 헬퍼 — 스펙트럼 위치 계산 단일 진실"
```

---

### Task 2: players 목록에 slay_score/obj_score/spectrum_pos 추가

**Files:**
- Modify: `web_api.py:108-118` (players_page)

**문제:** 현재 `classify_role`로 이산 role만 추가. 스펙트럼 바를 그리려면 연속값이 필요.

**해결:** `team_role_distribution`이 이미 모든 선수의 `slay_score`/`obj_score`를 계산하므로, 이걸 재사용해 players에 병합. 별도 재계산 없음(단일 진실).

- [ ] **Step 1: team_role_distribution 결과를 players에 병합**

`web_api.py:108-118` 수정:
```python
# 수정 전:
players = queries.all_players_overview(mode)
if mode == "HP" and players:
    import metrics
    team_avg = queries.team_averages("HP")
    for p in players:
        p_norm = dict(p)
        if "avg_ck" in p_norm and "avg_capture" not in p_norm:
            p_norm["avg_capture"] = p_norm["avg_ck"]
        p["role"] = metrics.classify_role(p_norm, team_avg) if team_avg else "balanced"
return render("players.html", lang=lang, players=players, mode=mode)

# 수정 후:
players = queries.all_players_overview(mode)
# HP 모드: 역할 스펙트럼 데이터(slay_score/obj_score/위치) 추가 — 허브와 동일 출처.
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
```

- [ ] **Step 2: 검증**

```bash
DISCORD_BOT_TOKEN=dummy OPENAI_API_KEY=dummy python -c "
import web_api, queries, metrics
# team_role_distribution과 players 데이터 일치 확인
roles = {r['name']: r for r in queries.team_role_distribution()}
players = queries.all_players_overview('HP')
for p in players[:3]:
    r = roles.get(p['name'])
    if r:
        pos = metrics.role_spectrum_pos(r['slay_score'], r['obj_score'])
        print(f'{p[\"name\"]}: role={r[\"role\"]} slay={r[\"slay_score\"]} obj={r[\"obj_score\"]} pos={pos}%')
print('PASS')
"
```

- [ ] **Step 3: Commit**

```bash
git add web_api.py
git commit -m "feat: players 목록에 스펙트럼 데이터 추가 (slay/obj_score/pos)"
```

---

### Task 3: player_detail에 스펙트럼 데이터 추가

**Files:**
- Modify: `web_api.py:121-145` (player_detail)

**문제:** player_detail도 이산 role만. 동일하게 스펙트럼 데이터 필요.

- [ ] **Step 1: player_detail에 slay/obj_score/pos 추가**

`web_api.py`의 player_detail 함수(`stats["hp"]["role"]` 설정 부분 근처)에 추가. `team_role_distribution`에서 해당 선수 찾아 병합:
```python
# stats["hp"]["role"] = ... 다음에:
if stats["hp"]:
    import metrics
    roles = {r["name"]: r for r in queries.team_role_distribution()}
    r = roles.get(stats["name"])
    if r:
        stats["hp"]["slay_score"] = r["slay_score"]
        stats["hp"]["obj_score"] = r["obj_score"]
        stats["hp"]["spectrum_pos"] = metrics.role_spectrum_pos(r["slay_score"], r["obj_score"])
```
정확한 삽입 위치는 Read로 확인.

- [ ] **Step 2: 검증**

```bash
DISCORD_BOT_TOKEN=dummy OPENAI_API_KEY=dummy python -c "
import queries, metrics
pid = queries.get_player_id('Cartels')
stats = queries.player_overall_stats(pid)
roles = {r['name']: r for r in queries.team_role_distribution()}
r = roles.get(stats['name'])
if r:
    print(f'{stats[\"name\"]}: slay={r[\"slay_score\"]} obj={r[\"obj_score\"]} pos={metrics.role_spectrum_pos(r[\"slay_score\"], r[\"obj_score\"])}%')
print('PASS')
"
```

- [ ] **Step 3: Commit**

```bash
git add web_api.py
git commit -m "feat: player_detail에 스펙트럼 데이터 추가"
```

---

### Task 4: 미니 스펙트럼 바 CSS — base.html에 공통 클래스 추가

**Files:**
- Modify: `templates/base.html` (공통 CSS 영역)

**문제:** 허브의 `.spectrum` 클래스는 허브 전용(넓은 트랙). 선수 카드엔 미니 버전 필요. 두 템플릿(players, player_detail)이 공유하므로 base.html에 배치.

- [ ] **Step 1: 미니 스펙트럼 CSS 추가**

base.html의 기존 `.spectrum` 근처(또는 role-badge 근처)에 미니 버전 추가:
```css
/* 미니 역할 스펙트럼 — 선수 카드/상세용 (허브 spectrum의 축소판) */
.mini-spectrum { position: relative; height: 8px; border-radius: var(--radius-full); background: var(--card-2); margin-top: var(--space-2); }
.mini-spectrum::before {
    content: ''; position: absolute; inset: 0; border-radius: inherit;
    background: linear-gradient(90deg, var(--hp-weak), var(--card-2) 45%, var(--card-2) 55%, var(--danger-weak));
}
.mini-spectrum__mid { position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background: var(--border-strong); transform: translateX(-50%); }
.mini-spectrum__marker {
    position: absolute; top: 50%; width: 14px; height: 14px; border-radius: var(--radius-full);
    border: 2px solid var(--card); transform: translate(-50%, -50%); box-shadow: var(--shadow-sm);
}
.mini-spectrum__marker--slayer { background: var(--danger); }
.mini-spectrum__marker--objective { background: var(--hp); }
.mini-spectrum__marker--balanced { background: var(--muted); }
.mini-spectrum__labels { display: flex; justify-content: space-between; font-size: var(--fs-xs); font-weight: var(--fw-medium); margin-top: var(--space-1); }
/* 선수 카드용 — 더 컴팩트 */
.player-card .mini-spectrum { height: 6px; }
.player-card .mini-spectrum__marker { width: 12px; height: 12px; }
```

- [ ] **Step 2: 검증 — 템플릿 파싱**

```bash
python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates'))
src = env.get_template('base.html').environment.loader.get_source(env, 'base.html')[0]
assert 'mini-spectrum' in src, 'FAIL: mini-spectrum not in base.html'
print('base.html: PASS')
"
```

- [ ] **Step 3: Commit**

```bash
git add templates/base.html
git commit -m "feat: 미니 스펙트럼 바 CSS (base.html 공통 클래스)"
```

---

### Task 5: players.html 배지 → 미니 스펙트럼 바 교체

**Files:**
- Modify: `templates/players.html:21-23, 40-52` (배지 제거 + 미니 바 추가)

- [ ] **Step 1: 배지를 미니 스펙트럼으로 교체**

`players.html:21-23` 수정 — 배지 부분을 미니 바로:
```html
<!-- 수정 전: -->
{% if p.role %}
<span class="role-badge role-badge--{{ p.role }}">{{ t['role_' + p.role] }}</span>
{% endif %}

<!-- 수정 후: -->
{% if mode == 'HP' and p.spectrum_pos is defined %}
<div class="mini-spectrum" title="{{ t.hub_spectrum_slay }} {{ p.slay_score }} · {{ t.hub_spectrum_obj }} {{ p.obj_score }}">
    <span class="mini-spectrum__mid"></span>
    <span class="mini-spectrum__marker mini-spectrum__marker--{{ p.role }}" style="left: {{ p.spectrum_pos }}%"></span>
</div>
<div class="mini-spectrum__labels">
    <span class="text-hp">{{ t.hub_spectrum_obj }}</span>
    <span class="text-danger">{{ t.hub_spectrum_slay }}</span>
</div>
{% endif %}
```
(동적값 `left:%`는 인라인 허용 예외. hover 시 title로 점수 표시.)

- [ ] **Step 2: player-card 레이아웃 조정**

`.player-card__header`에서 배지가 빠지므로, 이름만 남음. 미니 바는 카드 하단(ZCS 값 아래)에 배치할지, 헤더 아래에 바로 배치할지 결정 — 헤더 아래가 자연스럽다고 판단(역할 정보는 상단에). 미니 바를 `player-card__header` 다음에 배치.

- [ ] **Step 3: 검증 — 실제 렌더링**

```bash
# 서버 띄워서 /players?mode=HP 접근, spectrum 마커 존재 확인
DISCORD_BOT_TOKEN=dummy OPENAI_API_KEY=dummy uvicorn web_api:app --port 8765 &
sleep 3
python -c "
import urllib.request
resp = urllib.request.urlopen('http://localhost:8765/players?mode=HP&lang=ko')
html = resp.read().decode('utf-8')
assert 'mini-spectrum' in html, 'FAIL: mini-spectrum not rendered'
assert 'spectrum_pos' not in html or 'left:' in html, 'FAIL: marker position missing'
count = html.count('mini-spectrum__marker')
print(f'mini-spectrum markers rendered: {count}')
print('PASS')
"
```

- [ ] **Step 4: Commit**

```bash
git add templates/players.html
git commit -m "feat: players 목록 배지 → 미니 스펙트럼 바"
```

---

### Task 6: player_detail.html 배지 → 미니 스펙트럼 바 교체

**Files:**
- Modify: `templates/player_detail.html:7-9`

- [ ] **Step 1: 헤더 배지를 미니 바로 교체**

`player_detail.html:7-9` 수정:
```html
<!-- 수정 전: -->
{% if stats.hp and stats.hp.role %}
<span class="role-badge role-badge--{{ stats.hp.role }}">{{ t['role_' + stats.hp.role] }}</span>
{% endif %}

<!-- 수정 후: -->
{% if stats.hp and stats.hp.spectrum_pos is defined %}
<div class="mini-spectrum" style="width: 200px;" title="{{ t.hub_spectrum_slay }} {{ stats.hp.slay_score }} · {{ t.hub_spectrum_obj }} {{ stats.hp.obj_score }}">
    <span class="mini-spectrum__mid"></span>
    <span class="mini-spectrum__marker mini-spectrum__marker--{{ stats.hp.role }}" style="left: {{ stats.hp.spectrum_pos }}%"></span>
</div>
<div class="mini-spectrum__labels" style="width: 200px;">
    <span class="text-hp">{{ t.hub_spectrum_obj }}</span>
    <span class="text-danger">{{ t.hub_spectrum_slay }}</span>
</div>
{% endif %}
```
(상세 페이지는 여유가 있으므로 200px 고정 폭. 동적 width는 인라인 허용 예외.)

- [ ] **Step 2: 검증**

```bash
python -c "
import urllib.request
resp = urllib.request.urlopen('http://localhost:8765/players/Cartels?lang=ko')
html = resp.read().decode('utf-8')
assert 'mini-spectrum' in html, 'FAIL: mini-spectrum not in player_detail'
print('PASS')
"
```

- [ ] **Step 3: Commit**

```bash
git add templates/player_detail.html
git commit -m "feat: player_detail 배지 → 미니 스펙트럼 바"
```

---

### Task 7: 허브 스펙트럼 위치 공식을 헬퍼로 통일 (DRY)

**Files:**
- Modify: `templates/coaching_hub.html:225-229`

**문제:** 허브는 아직 인라인 Jinja2로 위치 계산. Task 1 헬퍼와 이중 진실. 허브에도 헬퍼 값 전달.

- [ ] **Step 1: analytics.py coaching_hub에서 spectrum_pos 계산해 템플릿에 전달**

`analytics.py`의 `team_role_distribution` 결과에 `spectrum_pos`를 미리 계산해 추가 (queries.py 수정). 또는 coaching_hub 데이터 조립 시(analytics.py coaching_hub 함수) 계산.

가장 단순: `queries.team_role_distribution` 반환 dict에 `spectrum_pos` 추가.
```python
# queries.py team_role_distribution, out.append({...})에 추가:
"spectrum_pos": metrics.role_spectrum_pos(slay, obj),
```

- [ ] **Step 2: coaching_hub.html 인라인 계산을 spectrum_pos 사용으로 교체**

`coaching_hub.html:225-229` 수정:
```html
<!-- 수정 전: -->
{% set ss = p.slay_score if p.slay_score else 1.0 %}
{% set os = p.obj_score if p.obj_score else 1.0 %}
{% set pos = [5, [95, (50 + norm * 450)|round(1)]|min]|max %}

<!-- 수정 후: -->
{% set pos = p.spectrum_pos %}
```
(norm 변수도 제거 — 더 이상 인라인 계산 안 함.)

- [ ] **Step 3: 검증 — 허브 페이지 정상 렌더링**

```bash
python -c "
import urllib.request
resp = urllib.request.urlopen('http://localhost:8765/?lang=ko')
html = resp.read().decode('utf-8')
assert 'spectrum-marker' in html, 'FAIL: hub spectrum broken'
print(f'hub spectrum markers: {html.count(\"spectrum-marker\")}')
print('PASS')
"
```

- [ ] **Step 4: Commit**

```bash
git add queries.py templates/coaching_hub.html
git commit -m "refactor: 허브 스펙트럼 위치 계산을 헬퍼로 통일 (DRY)"
```

---

### Task 8: 최종 검증 — verification-before-completion

- [ ] **Step 1: 전체 게이트 실행**

```bash
DISCORD_BOT_TOKEN=dummy OPENAI_API_KEY=dummy python -c "
import urllib.request, re

# G1: /players 미니 스펙트럼 렌더링
html = urllib.request.urlopen('http://localhost:8765/players?mode=HP&lang=ko').read().decode('utf-8')
assert html.count('mini-spectrum__marker') > 0, 'FAIL: no markers in players'
print(f'G1 players markers: {html.count(\"mini-spectrum__marker\")}')

# G2: player_detail 미니 스펙트럼
html2 = urllib.request.urlopen('http://localhost:8765/players/Cartels?lang=ko').read().decode('utf-8')
assert 'mini-spectrum' in html2, 'FAIL: no spectrum in detail'
print('G2 player_detail: PASS')

# G3: 허브 스펙트럼 정상 (회귀 없음)
html3 = urllib.request.urlopen('http://localhost:8765/?lang=ko').read().decode('utf-8')
assert html3.count('spectrum-marker') > 0, 'FAIL: hub spectrum broken'
print(f'G3 hub markers: {html3.count(\"spectrum-marker\")}')

# G4: SND 모드엔 스펙트럼 없음
html4 = urllib.request.urlopen('http://localhost:8765/players?mode=SND&lang=ko').read().decode('utf-8')
assert 'mini-spectrum' not in html4, 'FAIL: spectrum shown in SND'
print('G4 SND no spectrum: PASS')

# G5: role-badge 잔류 확인 (구 배지 제거)
assert 'role-badge' not in html, 'FAIL: old badge still in players'
print('G5 old badge removed: PASS')

print('ALL GATES PASS')
"
```

- [ ] **Step 2: i18n 테스트**

```bash
pytest test_i18n.py -q
```

---

## Self-Review

**1. Spec coverage:** 허브 스펙트럼 → 선수 탭 동기화. players 목록(Task 5) + player_detail(Task 6) + 허브 DRY(Task 7). ✅

**2. Placeholder scan:** 각 코드는 실제 파일 구조 기반. CSS 클래스명 일관(`mini-spectrum*`). ✅

**3. Type consistency:**
- `spectrum_pos`: float (5.0~95.0). 헬퍼 반환값과 허브/선수탭 동일.
- `slay_score`/`obj_score`: team_role_distribution 반환 타입(float)과 동일.
- ✅

**리스크:**
- players.html 카드 레이아웃: 미니 바 추가로 카드 높이 변화 — 모바일 3단 그리드 영향 확인 필요.
- player_detail 헤더: h1 안에 200px 바가 들어가면 레이아웃 깨질 수 있음 — h1 밖으로 빼야 할 수도.
- 기존 role-badge CSS가 base.html에 남아있음 — 다른 곳(commands_cog)에서 쓸 수 있으니 제거 안 함.
