# 코칭 브레인 → AI 인사이트 이식 설계

> **날짜**: 2026-07-12
> **목표**: 코치의 세컨드 브레인(`coaching brain/`)을 기존 AI 인사이트 시스템에 이식해 인사이트 품질을 높이되, AI의 원래 의도·행동 지시는 보존한다.

---

## 배경

### 현재 상태
- **코칭 브레인** (`coaching brain/knowledge/`, Obsidian 볼트, ~44KB): 코치가 전사문 기반으로 정리한 CODM 철학·역학·맵·모드·팀운영 지식. 모듈화된 17개 마크다운 파일. 계속 손으로 수정되는 "살아있는" 세컨드 브레인.
- **기존 AI 주입부** (`prompt_context.py`): `_STATIC_DOMAIN_CONTEXT`(단일 문자열 ~5KB)가 모드/지표/역할/용어/코칭톤을 요약. `_PLAYER_IGN_MAP`(발음변형), `_MAP_META`(맵 tendency). `build_system_prompt()`가 이걸 조합 → `analytics_insights.py`의 7개 인사이트 함수가 전부 통과.
- **핵심 인사이트**: 두 시스템은 **같은 전사문**에서 나왔지만 코칭 브레인이 훨씬 풍부한 상위집합(superset). 기존 정적 컨텍스트는 코칭 브레인의 "요약 카드".

### 왜 이식하나
- 기존 AI는 "지표 해석 + 일반 CODM 상식" 수준. 코치의 고유한 철학·맵 심층 지식·팀 운영 원칙이 빠져 있어 인사이트가 평범함.
- 코칭 브레인을 주입하면 AI가 "이 코치의 시각"으로 인사이트를 생성 → 품질·일관성·깊이 향상.

---

## 설계 결정 (브레인스토밍 합의)

| 결정 | 선택 | 이유 |
|---|---|---|
| 이식 범위 | **맥락별 선택적 주입** | 호출 성격에 맞는 문서만 선택. 토큰 비용 최소화(전체 12,000토큰의 10~18%), 품질 최대화 |
| 로딩 방식 | **런타임 파일 읽기 + mtime 캐시** | 세컨드 브레인을 계속 수정하므로. mtime 체크로 재시작 없이 자동 반영 |
| 겹침 처리 | **지표/로스터는 남기고 통찰은 브레인으로 이관** | 계산 지표 정의(metrics.py 동기화)는 prompt_context에, 인간 통찰은 코칭 브레인에. 책임 분리 |
| 접근법 | **A안: 명시적 영역 지정** | 각 인사이트 함수가 `domains=["..."]` 명시. 투명·예측 가능·코칭 브레인 구조와 1:1 대응 |

---

## 아키텍처

```
[coaching brain/knowledge/*.md]   ← 코치가 손으로 수정 (진실 공급원)
            │ 런타임 파일 읽기 (mtime 캐시)
            ▼
[coaching_brain_loader.py] (신규)  ← 영역별 로드 + mtime 자동 무효화
            │ get_domains(["principles","maps:Combine"])
            ▼
[prompt_context.py] (변경)         ← build_system_prompt가 브레인 통합
   ├ 지표 정의(ZCS/RDS/DPK...) — 유지 (기존, 슬림화)
   ├ IGN 변형 맵 — 유지 (기존)
   ├ 동적 로스터 — 유지 (기존)
   └ 코칭 통찰 — 코칭 브레인에서 로드 (신규)
            │
            ▼
[analytics_insights.py] (변경最小)
   7개 인사이트 함수 각자 domains=["..."] 명시만 추가
   task 지시문·응답 형식·캐싱 전부 건드리지 않음
```

---

## 컴포넌트 상세

### 1. `coaching_brain_loader.py` (신규, ~80줄)

**단일 책임**: 코칭 브레인 마크다운을 영역 단위로 읽고 mtime 기반 캐시로 반환.

#### 영역 스키마 (코칭 브레인 구조와 1:1 매핑)

```python
KNOWLEDGE_DIR = "coaching brain/knowledge"

_DOMAIN_FILES = {
    "principles":      "principles/코칭철학원칙.md",
    "mechanics-core":  "mechanics/CODM기본역학.md",
    "mechanics-meta":  "mechanics/무기옵스킬메타.md",
    "mechanics-terms": "mechanics/공용어사전.md",
    "mode-hp":         "modes/Hardpoint.md",
    "mode-snd":        "modes/SearchDestroy.md",
    "mode-control":    "modes/Control.md",
    "team":            "team/팀운영.md",
    # maps:{MapName} → maps/{MapName}.md (동적 키)
}
```

#### 핵심 함수 2개

```python
def _read_cached(rel_path: str) -> str:
    """mtime 기반 캐싱으로 단일 파일 읽기.
    mtime 변경 시 자동 리로드, 아니면 캐시 반환.
    파일 없음/에러 시 빈 문자열 (서버 터트리지 않음) + 콘솔 로그.
    """

def get_domains(domains: list[str], lang: str = "ko") -> str:
    """영역 리스트 → 결합된 마크다운 텍스트.
    - 고정 키: _DOMAIN_FILES에서 조회
    - 동적 키(maps:{MapName}): maps/{MapName}.md 시도, 없으면 스킵
    - 빈 결과면 "" 반환
    """
```

#### 설계 결정
1. **`lang` 파라미터는 현재 무시** (마크다운 원본 한국어 고정). AI가 task 지시로 출력 언어 제어하므로 문제없음. 자리만 확보 (YAGNI — 향후 번역 레이어 가능).
2. **맵은 동적 키**: `"maps:Combine"` → `maps/Combine.md`. 코칭 브레인에 없는 맵은 자동 스킵. 새 맵 문서 추가 시 매핑 테이블 수정 불필요.
3. **마크다운 원본 그대로 주입**. Obsidian 링크는 AI가 무시. 향후 토큰 절약 필요 시 헤더/링크 정제 옵션.
4. **실패 안전**: 파일 없음/권한/인코딩 에러 → 빈 문자열 + 로그. AI 호출은 지표/로스터만으로 계속 동작.

---

### 2. `prompt_context.py` (수정, ~40줄 변경)

#### `_STATIC_DOMAIN_CONTEXT` 재구성

기존 ~5KB(모드+지표+역할+용어+코칭톤)를 두 책임으로 분리:

**유지 → `_METRIC_DEFINITIONS`** (계산 지표 정의, metrics.py와 동기화):
- 모드 정의 (HP/SND/Control + OBJ/CapKill/FK/LWW 의미)
- 지표 공식·벤치마크·방향 (ZCS/RDS/DPK/DPD/Impact/AP%, 높/낮)
- IGN 발음변형 맵 (`_PLAYER_IGN_MAP`) — OCR/전사 처리용, 코칭 통찰 아님

**제거 → 코칭 브레인으로 이관**:
- Tactical Terms (스폰/푸시/로테...) → `mechanics-terms` (공용어사전.md)
- Roles/Positions (AR/OBJ/sniper...) → `mechanics-core` (CODM기본역학.md)
- CODM Mechanics (scorestreak...) → `mechanics-core`/`mechanics-meta`
- Coaching Tone → `principles` (코칭철학원칙.md)
- `_MAP_META` 딕셔너리 → `maps:{MapName}` (코칭 브레인이 상위집합)

#### `build_system_prompt` 시그니처 확장

```python
_DEFAULT_DOMAINS = ["principles", "mechanics-core"]  # domains=None일 때

def build_system_prompt(task: str, lang: str = "ko", domains: list = None) -> str:
    """모든 AI 호출용 system 프롬프트 조합.
    지표 정의 + IGN 맵 + 코칭 브레인 통찰(선택) + 날짜 + 동적 로스터 + task.
    하위 호환: domains=None → 기본 세트(principles + mechanics-core).
    """
    insight_context = coaching_brain_loader.get_domains(
        domains or _DEFAULT_DOMAINS, lang
    )  # "" 일 수 있음 — 그래도 동작

    parts = [
        _METRIC_DEFINITIONS,
        _format_ign_map(),
        insight_context,
        f"\n## Current Date (meta snapshot): {today}",
        team_roster_context(),
        f"\n## Task\n{task}",
        f"\nRespond in {lang_note}.",
    ]
    return "\n".join(p for p in parts if p)
```

#### 하위 호환성
- `build_system_prompt(task, lang)` 호출 그대로 동작 (domains=None → 기본 세트).
- `SYSTEM_PROMPT = build_system_prompt()` 상수 호환.
- 코칭 브레인 폴더 없거나 비면 `insight_context = ""` → 기존처럼 지표+로스터만으로 동작. **배포 환경 누락 시에도 서버 안 터짐.**

---

### 3. `analytics_insights.py` (수정 최小, 7곳 × 1~3줄)

#### 영역 매핑표

| 함수 | 데이터에서 추출 | domains |
|---|---|---|
| `match_insight` | mode, map_name | `principles`, `mechanics-core`, `mode-{mode}`, `maps:{map}` |
| `weekly_insight` | (주간 집계) | `principles`, `mechanics-core`, `team` |
| `trend_insight` | mode | `principles`, `mechanics-core`, `mode-{mode}` |
| `player_profile_insight` | hp/snd 존재 | `principles`, `mechanics-core`, `mechanics-meta`, `mode-{hp/snd}` |
| `map_advice` | mode, map_name | `principles`, `mode-{mode}`, `maps:{map}`, `mechanics-terms` |
| `summarize_transcript` | mode, map_name | `principles`, `mechanics-core`, `mode-{mode}`, `maps:{map}`, `mechanics-terms`, `team` |
| `briefing_insight` | (허브 종합) | `principles`, `mechanics-core`, `team`, `mechanics-meta` |

#### 헬퍼 함수 (반복 로직 추출)

```python
def _domains_for_match(mode: str, map_name: str = None, extra: list = None) -> list:
    """매치/맵 계열 함수 공용: 모드+맵 도메인 조합."""
    d = ["principles", "mechanics-core"]
    mode_key = {"HP": "mode-hp", "SND": "mode-snd", "Control": "mode-control"}.get(mode)
    if mode_key:
        d.append(mode_key)
    if map_name:
        d.append(f"maps:{map_name}")  # 없으면 loader가 스킵
    if extra:
        d.extend(extra)
    return d
```

#### 각 함수 변경 패턴 (task 지시문은 수정 안 함)

```python
# 변경 전
"content": prompt_context.build_system_prompt("Write 1-2 sentences...", lang),

# 변경 후
"content": prompt_context.build_system_prompt(
    "Write 1-2 sentences...",
    lang,
    domains=_domains_for_match(report["mode"], report.get("map_name")),
),
```

---

## AI 원래 의도 보존 (사용자 핵심 요구사항)

| 보존 항목 | 어떻게 보존되나 |
|---|---|
| 각 함수 task 지시문 | **1자도 수정 안 함**. domains만 추가 |
| 응답 형식/길이/언어 | 동일. system 프롬프트 구조만 확장 |
| 숫자 기반 grounding | 유지. 지표 정의 레이어 그대로 |
| 캐싱 (insight_cache.py) | 영향 없음. 동일 입력 → 동일 캐싱 |
| 실패 시 빈 문자열 | 유지. 코칭 브레인 로드 실패해도 기존처럼 동작 |

→ 코칭 브레인은 "AI가 더 풍부하게 해석할 수 있는 배경지식"만 추가. 행동 지시·출력 형식은 건드리지 않음.

---

## 토큰 예산 (선택적 주입 결과)

| 함수 | 예상 추가 토큰 | 전체 주입(12,000) 대비 |
|---|---|---|
| match_insight | ~1,800 | 15% |
| player_profile_insight | ~1,600 | 13% |
| map_advice | ~1,500 | 13% |
| summarize_transcript | ~2,200 | 18% (가장 풍부) |
| briefing_insight | ~1,700 | 14% |
| weekly/trend | ~1,200 | 10% |

---

## 검증 전략

### 로컬 검증 가능
| 항목 | 방법 |
|---|---|
| 코칭 브레인 로드 정상 | `python -c "import coaching_brain_loader; print(len(coaching_brain_loader.get_domains(['principles','maps:Combine'])))"` |
| mtime 캐시 동작 | 파일 touch 후 재호출 → 다른 결과 |
| 없는 맵 스킵 | `get_domains(['maps:존재안함'])` → `""` |
| 하위 호환 | `build_system_prompt("test","ko")` (domains 없이) 정상 반환 |
| 인사이트 회귀 | `match_insight(report)` 빈 문자열 아닌 정상 반환 (OPENAI_API_KEY 필요) |
| 지표 정합성 | `_METRIC_DEFINITIONS` vs `metrics.py` 수동 대조 (ZCS/RDS 가중치) |
| 맵/mode 키 정규화 | DB 실제 mode/map_name 값 → loader 매핑 키와 일치 확인 (샘플 5-10행) |

### 배포 후 확인 (로컬 불가, AGENTS.md §3)
- Railway 환경에서 코칭 브레인 폴더 경로 인식
- 실제 GPT 응답 품질 향상 (정성)

---

## 파일 체크리스트

| 파일 | 변경 유형 | 규모 | 내용 |
|---|---|---|---|
| `coaching_brain_loader.py` | 신규 | ~80줄 | 영역 스키마, `_read_cached`(mtime), `get_domains` |
| `prompt_context.py` | 수정 | ~40줄 변경 | `_STATIC`→`_METRIC_DEFINITIONS` 슬림화, `_MAP_META` 제거, domains 파라미터 추가, 코칭 브레인 통합 |
| `analytics_insights.py` | 수정 | 7곳 × 1~3줄 | 각 함수 `domains=` 전달, `_domains_for_match` 헬퍼 |
| `coaching brain/` 폴더 | git 추적 | — | `git add` (현재 untracked). 비밀정보 아님 |
| AGENTS.md | 수정(선택) | ~10줄 | 코칭 브레인 이식 아키텍처 메모 |

**총 규모**: 신규 1 + 수정 2 = ~120줄.

---

## 커밋 계획 (AGENTS.md §7)

사용자 승인 시 2개 커밋 분리:
1. `feat: 코칭 브레인 → AI 인사이트 이식 (선택적 영역 주입)` — loader + prompt_context + analytics_insights
2. `chore: coaching brain 지식베이스 git 추적 추가` — 폴더 커밋

---

## 리스크 & 완화

| 리스크 | 완화 |
|---|---|
| 코칭 브레인에 없는 맵이 DB에 있음 | loader가 스킵 → 기존 지표만으로 동작 |
| 코칭 브레인 폴더 배포 누락 | `get_domains`가 "" 반환 → 기존처럼 동작 |
| 토큰 비용 증가 | 선택적 주입으로 10~18%만 |
| 기존 캐시된 인사이트가 구버전 지식 | TTL 1시간 자연 갱신 |

---

## 배포 고려 (Railway)

코칭 브레인 폴더를 git에 커밋해야 배포 반영. 현재 `git status`에 `?? "coaching brain/"` (untracked). 비밀정보 아님 — 순수 마크다운 지식이라 `.gitignore` 대상 아님. 구현 시 `git add` 후 `.gitignore` 충돌 확인.
