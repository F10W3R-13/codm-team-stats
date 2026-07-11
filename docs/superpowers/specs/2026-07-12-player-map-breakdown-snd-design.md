# 선수 맵별 성적 HP/SND 토글 설계

> **날짜**: 2026-07-12
> **목표**: 선수 상세 페이지의 맵별 성적 히트맵을 HP 5개 맵에서 SND 맵까지 확장. 카드 내 모드 토글로 HP/SND 전환. SND는 RDS ±% 기반.

---

## 배경

### 현재 상태
- 선수 상세 페이지(`/players/{name}`)의 맵별 히트맵은 **HP 전용**.
- `queries.player_map_breakdown(player_id, min_matches=5)` — `mode='HP'` 고정, `player_stats_hp` 테이블만 조회, ZCS 기반.
- 템플릿은 `player_maps` 리스트를 HP 섹션 아래 히트맵으로 렌더. SND 섹션엔 맵별 데이터 없음.
- HP 히트맵 데이터는 충분(Combine/Hacienda/Takeoff/Summit/Arsenal 등 다수 매치).

### 데이터 현실 (SND)
- 현재 SND 맵 데이터: Meltdown(2), Firing Range(1), Coastal(1). 총 4매치.
- 기존 `min_matches=5`로는 전부 미만 → 빈 결과.
- SND 임계를 2로 낮추면 Meltdown 1개 표시. 향후 매치 누적 시 자동 확장.

### 왜 확장하나
- SND 선수 평가에 맵별 데이터가 빠져 있어 종합 평가 불가.
- HP/SND 대칭 구조(AGENTS.md 원칙: SND 제1지표=RDS)를 맵별 히트맵에도 적용.

---

## 설계 결정 (브레인스토밍 합의)

| 결정 | 선택 | 이유 |
|---|---|---|
| SND 맵 지표 | **RDS ±%** | HP의 ZCS ±%와 대칭. AGENTS.md 원칙(SND 제1지표=RDS) 부합 |
| 토글 UI | **카드 내 모드 토글** | JS로 전환(새로고침 없음). HP/SND 카드 분리 대신 1개 카드에서 모드 전환 |
| SND min_matches | **min=2** | 현재 데이터 부족(Meltdown 2). 빈 화면보단 일부라도 표시가 UX상 나음 |
| 접근법 | **A안: 기존 함수 확장** | `player_map_breakdown`에 `mode` 파라미터. HP 로직 보존 + SND 분기 추가. ±% 로직 공용 |

---

## 아키텍처

```
[queries.py]
  player_map_breakdown(player_id, mode="HP", min_matches=5)
    ├ mode="HP"  → player_stats_hp, ZCS 쿼리, _player_overall_zcs()
    └ mode="SND" → player_stats_snd, RDS 쿼리, _player_overall_rds() (신규)
  반환: [{map_name, matches, metric, metric_pct, ...}]  ← zcs/zcs_pct → metric/metric_pct 통일
            │
            ▼
[web_api.py] player_detail 라우트
  player_maps     = player_map_breakdown(pid, mode="HP",  min_matches=5)  ← HP
  player_maps_snd = player_map_breakdown(pid, mode="SND", min_matches=2)  ← SND 신규
  _heat_class(pct) 헬퍼 — HP/SND 공용 색 등급 (기존 인라인 삼항 리팩터)
            │  render(... player_maps, player_maps_snd)
            ▼
[templates/player_detail.html]
  맵 히트맵 카드 1개
    ├ [HP] [SND] 토글 버튼 (둘 다 데이터 있을 때만)
    ├ HP 패널  (data-map-panel="hp")  — player_maps
    └ SND 패널 (data-map-panel="snd") — player_maps_snd
  JS: 토글 클릭 → 패널 display 전환
[i18n/_ko.py, _en.py, _es.py]
  player_maps_help_snd, player_maps_no_data_hp/snd 신규 3키
[templates/base.html]
  .mode-toggle, .mode-toggle__btn, .map-panel CSS 클래스
```

---

## 컴포넌트 상세

### 1. `queries.py` — `player_map_breakdown` mode 확장

**시그니처 변경**: `player_map_breakdown(player_id, mode="HP", min_matches=5)`

**mode 분기**:
- `mode="HP"`: 기존 로직. `player_stats_hp`, ZCS 공식 `max(0, 1.1·obj_time + 8·capture_kill + 4.1·kills - 5·deaths)`, `_player_overall_zcs()`.
- `mode="SND"`: 신규. `player_stats_snd`, RDS 공식 `max(0, 4.1·kills + 3.5·assists + 14·first_kill + 20·lone_wolf_win + 0.12·adr - 5·deaths)`, `_player_overall_rds()` 신규.

**SND 쿼리**:
```sql
SELECT LOWER(m.map_name) map_name,
       COUNT(*) matches,
       ROUND(AVG(MAX(0, 4.1*s.kills + 3.5*s.assists + 14*s.first_kill
                   + 20*s.lone_wolf_win + 0.12*s.adr - 5*s.deaths)),1) metric
FROM player_stats_snd s
JOIN matches m ON m.id=s.match_id
WHERE s.player_id=? AND m.map_name IS NOT NULL AND m.map_name != ''
  AND m.mode='SND'
GROUP BY LOWER(m.map_name)
HAVING COUNT(*) >= ?
ORDER BY metric DESC
```

**`_player_overall_rds()` 신규** (기존 `_player_overall_zcs`와 대칭):
```sql
SELECT ROUND(AVG(MAX(0, 4.1*kills + 3.5*assists + 14*first_kill
                  + 20*lone_wolf_win + 0.12*adr - 5*deaths)),1) rds
FROM player_stats_snd WHERE player_id=?
```

**반환 키 통일**: `zcs`/`zcs_pct` → `metric`/`metric_pct`. 템플릿이 mode 무관하게 동작.

**하위 호환**: 기존 호출 `player_map_breakdown(pid, min_matches=5)` → mode 기본 "HP"로 동작. 단 반환 키 변경(의도적)은 web_api + 템플릿과 함께 업데이트.

---

### 2. `web_api.py` — player_detail 라우트

**호출부 변경** (`web_api.py:147` 근처):
```python
player_maps = queries.player_map_breakdown(pid, mode="HP", min_matches=5) if stats["hp"] else []
player_maps_snd = queries.player_map_breakdown(pid, mode="SND", min_matches=2) if stats["snd"] else []
```

**`_heat_class` 헬퍼 추가** (기존 인라인 삼항 리팩터, HP/SND 공용):
```python
def _heat_class(pct: float) -> str:
    """맵 히트맵 색 등급 (±% 기준). HP/SND 공용."""
    if pct >= 15: return "heat-2"
    if pct >= 5:  return "heat-1"
    if pct <= -15: return "heat--2"
    if pct <= -5:  return "heat--1"
    return "heat-0"
```

**heat_class 적용** (HP/SND 양쪽):
```python
for m in player_maps:
    m["heat_class"] = _heat_class(m["metric_pct"])
for m in player_maps_snd:
    m["heat_class"] = _heat_class(m["metric_pct"])
```

**render 전달**: `player_maps_snd=player_maps_snd` 추가.

---

### 3. `templates/player_detail.html` — 토글 카드

기존 HP 맵 블록(`{% if player_maps %}` ~ `{% endif %}`)을 아래로 교체:

```html
{# ── 맵별 성적 히트맵 (HP/SND 토글) ── #}
{% if player_maps or player_maps_snd %}
<div class="card section">
    <h2>🗺️ {{ t.player_maps_title }}</h2>

    {# 모드 토글 — 둘 다 데이터 있을 때만 #}
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
        <p class="muted stat-label">{{ t.player_maps_help_snd }} ({{ t.rds_label }} {{ stats.snd.rds }})</p>
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

**토글 JS** (player_detail.html 하단 `<script>`):
```javascript
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
```

**동작 시나리오**:

| 상황 | 표시 |
|---|---|
| HP 데이터만 | HP 패널만, 토글 버튼 없음 |
| SND 데이터만 | SND 패널만, 토글 버튼 없음 |
| 둘 다 있음 | 토글 버튼 + HP 기본, 클릭 시 SND 전환 |
| 둘 다 없음 | 카드 자체 미표시 |

---

### 4. `templates/base.html` — CSS 클래스

`:root` 토큰 기반 (인라인 금지 규칙 준수):
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
.map-panel { /* 컨테이너 — 특별한 스타일 없음, display 전환만 */ }
```

---

### 5. `i18n/_ko.py`, `_en.py`, `_es.py` — 신규 3키

| 키 | ko | en | es |
|---|---|---|---|
| `player_maps_help_snd` | `이 선수의 SND 맵별 RDS (본인 평균 대비)` | `This player's RDS by SND map (vs own average)` | `RDS por mapa SND (vs propio promedio)` |
| `player_maps_no_data_hp` | `이 선수의 HP 맵 데이터가 부족합니다` | `Not enough HP map data for this player` | `Datos insuficientes de mapas HP` |
| `player_maps_no_data_snd` | `이 선수의 SND 맵 데이터가 부족합니다` | `Not enough SND map data for this player` | `Datos insuficientes de mapas SND` |

`test_i18n.py`가 3개 언어 키 동일성 강제 → 3개 언어 모두 동일 키 추가.

**기존 키 재사용** (변경 불필요): `player_maps_title`, `player_maps_weak`, `player_maps_avg`, `player_maps_strong`, `player_maps_help` (HP용), `mode_hp`, `mode_snd`, `rds_label`, `zcs_label`, `matches`.

---

## 검증 전략

### 로컬 검증 가능
| 항목 | 방법 |
|---|---|
| HP 쿼리 하위 호환 | `player_map_breakdown(pid, min_matches=5)` (mode 생략) → 기존과 동일 |
| SND 쿼리 정상 | `player_map_breakdown(pid, mode="SND", min_matches=2)` → Meltdown 등 반환 |
| RDS 공식 정합성 | 반환 `metric` 값 vs `metrics.compute_rds()` 수동 대조 |
| 빈 결과 처리 | SND 데이터 없는 선수 → 빈 리스트 → 카드/패널 분기 |
| heat_class 헬퍼 | `_heat_class(15)`="heat-2", `_heat_class(-20)`="heat--2", `_heat_class(0)`="heat-0" |
| i18n 키 동일성 | `pytest test_i18n.py` → 3개 언어 동일 키셋 (신규 3키 포함) |
| 토글 JS 동작 | 로컬 uvicorn 기동 → 선수 페이지 HP/SND 전환 (수동) |
| Postgres 호환 | `_adapt_sql`이 `MAX(0,...)`→`GREATEST`, `?`→`%s` 변환 (로컬 SQLite 통과 → 배포 신뢰) |

### 배포 후 확인 (로컬 불가, AGENTS.md §3)
- 실제 배포 Postgres에서 SND 쿼리 정상 동작 (`AVG(MAX(0,...))` 중첩 괄호 — `_adapt_sql` 파서가 처리, 이미 검증된 패턴)

---

## 파일 체크리스트

| 파일 | 변경 유형 | 규모 | 내용 |
|---|---|---|---|
| `queries.py` | 수정 | ~40줄 변경 | `player_map_breakdown`에 `mode` 파라미터, 쿼리 분기, `metric`/`metric_pct` 통일, `_player_overall_rds()` 신규 |
| `web_api.py` | 수정 | ~15줄 변경 | player_detail 라우트: SND 호출 추가, `_heat_class` 헬퍼, `player_maps_snd` 렌더 전달 |
| `templates/player_detail.html` | 수정 | ~40줄 변경 | 맵 카드 HP/SND 토글 구조 재구성, `metric`/`metric_pct` 키 적용, 토글 JS |
| `templates/base.html` | 수정 | ~15줄 추가 | `.mode-toggle`/`.mode-toggle__btn`/`.map-panel` CSS 클래스 |
| `i18n/_ko.py`, `_en.py`, `_es.py` | 수정 | 각 3줄씩 | 신규 3키 |
| `test_player_maps.py` | 신규 | ~50줄 | `player_map_breakdown` HP/SND 분기 + `_heat_class` 단위테스트 |

**총 규모**: 수정 5파일 + 신규 1파일 = ~160줄.

---

## 데이터 현실 (SND 맵)

| 맵 | 매치 수 | min=2 시 표시? |
|---|---|---|
| Meltdown | 2 | ✅ |
| Firing Range | 1 | ❌ (임계 미만) |
| Coastal | 1 | ❌ (임계 미만) |

→ 현재 SND 토글해도 Meltdown 1개만 표시. 데이터 쌓이면 자동 확장. "데이터 부족" 메시지가 아니라 실제 데이터(Meltdown)가 보이는 게 UX상 나음.

---

## 커밋 계획 (AGENTS.md §7)

구현 완료 후 1개 커밋 제안 (기능 단위 단일):
```
feat: 선수 맵별 성적 HP/SND 토글 (SND RDS ±% 추가)
```
(사용자 승인 시에만.)

---

## 템플릿 변경 안전성

| 리스크 | 완화 |
|---|---|
| Jinja2 `{{ }}` 안 JS 연산자 | 토글 JS는 순수 `<script>` 블록, Jinja 변수 없음 → 충돌 0 |
| 맵 링크 `?mode=SND` | `/maps/{name}` 라우트가 이미 `mode` 파라미터 지원 |
| `metric` 키 미정의 참조 | `player_map_breakdown`이 항상 `metric` 키 반환 보장 |
| 인라인 스타일 | `style="display:none"`만 예외(Jinja 조건부), 나머진 클래스 |
