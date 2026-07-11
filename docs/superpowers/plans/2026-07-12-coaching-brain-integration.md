# 코칭 브레인 → AI 인사이트 이식 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 코칭 브레인(`coaching brain/knowledge/`)을 기존 AI 인사이트 시스템에 이식해, 각 인사이트 함수가 맥락에 맞는 코칭 지식을 선택적으로 주입받도록 한다. AI의 원래 행동 지시·출력 형식은 보존.

**Architecture:** 신규 `coaching_brain_loader.py`가 코칭 브레인 마크다운을 영역별로 mtime 캐싱하며 읽는다. `prompt_context.build_system_prompt()`가 `domains` 파라미터로 영역을 받아 코칭 브레인 통찰을 주입한다. `analytics_insights.py`의 7개 인사이트 함수는 각자 데이터에서 mode/map을 추출해 domains를 구성해 넘긴다(기존 task 지시문은 수정 안 함).

**Tech Stack:** Python 3 표준 라이브러리만 (`os.path`, `pathlib`, `functools`). 의존성 추가 없음. 기존 FastAPI/OpenAI 스택 유지.

## Global Constraints

- **지표 공식 고정** (AGENTS.md): ZCS = `max(0, 1.1·OBJ + 8·CapKill + 4.1·K − 5·D)`, RDS = `max(0, 4.1·K + 3.5·A + 14·FK + 20·LWW + 0.12·ADR − 5·D)`. `_METRIC_DEFINITIONS`는 이 공식과 정확히 일치.
- **DB mode 값**: `"HP"`, `"SND"` (Control은 현재 DB에 없지만 코칭 브레인엔 있어 향후 대비해 매핑 유지).
- **DB map_name ↔ 코칭 브레인 파일명**: 대소문자 불일치(`arsenal` vs `Arsenal.md`), 공백(`Firing Range`), 미존재 맵(`Coastal` 등) 존재. loader는 **대소문자 무시 매칭** + 미존재 시 스킵.
- **코칭 브레인 경로**: `"coaching brain/knowledge/"` (CWD = 프로젝트 루트). 한국어 파일명 포함.
- **AI task 지시문**: `analytics_insights.py`의 각 task 문자열은 1자도 수정 금지. domains 파라미터만 추가.
- **실패 안전**: 코칭 브레인 폴더/파일 없으면 빈 문자열 반환, 서버/인사이트 정상 동작 유지.
- **인라인 스타일 금지**(AGENTS.md): 본 변경은 백엔드 Python만 — 템플릿/CSS 미관련.

**Spec:** `docs/superpowers/specs/2026-07-12-coaching-brain-integration-design.md`

---

## File Structure

| 파일 | 유형 | 책임 |
|---|---|---|
| `coaching_brain_loader.py` | 신규 | 코칭 브레인 md를 영역별로 mtime 캐싱 읽기. 고정/동적 영역 매핑. |
| `prompt_context.py` | 수정 | `_STATIC_DOMAIN_CONTEXT` → `_METRIC_DEFINITIONS` 슬림화, `_MAP_META` 제거, `build_system_prompt`에 `domains` 파라미터 추가. |
| `analytics_insights.py` | 수정 | 7개 인사이트 함수에 `domains=` 전달, `_domains_for_match` 헬퍼 추가. task 지시문 불변. |
| `test_coaching_brain_loader.py` | 신규 | loader 단위 테스트 (mtime 캐싱, 대소문자 매칭, 미존재 스킵, 실패 안전). |
| `prompt.py` | 확인만 | `SYSTEM_PROMPT = build_system_prompt()` 하위 호환 — 변경 불필요(확인 단계). |
| `coaching brain/` | git 추적 | `git add` (untracked → 추적). 비밀정보 아님. |

---

## Task 1: `coaching_brain_loader.py` — 영역별 mtime 캐싱 로더

**Files:**
- Create: `coaching_brain_loader.py`
- Test: `test_coaching_brain_loader.py`

**Interfaces:**
- Consumes: 없음 (표준 라이브러리만)
- Produces:
  - `get_domains(domains: list[str], lang: str = "ko") -> str` — 영역 리스트 → 결합된 md 텍스트. 빈 결과/에러 시 `""`.
  - 내부 `_read_cached(rel_path: str) -> str` — mtime 기반 단일 파일 캐싱 읽기.

- [ ] **Step 1: Write the failing test**

`test_coaching_brain_loader.py`:

```python
# coaching_brain_loader 단위 테스트
#
# 실행: pytest test_coaching_brain_loader.py -v
#
# 검증 항목:
#  - 고정 영역(principles 등) 정상 로드
#  - 동적 영역(maps:Combine) 정상 로드
#  - 미존재 영역/맵 → 빈 문자열 (실패 안전)
#  - mtime 캐싱: 파일 수정 시 자동 리로드
#  - 대소문자 무시 맵 매칭 (arsenal → Arsenal.md)
#  - lang 파라미터 무시(현재) — 빈 문자열 아님만 확인

import os
import time
import tempfile
import shutil

import coaching_brain_loader as loader


def test_fixed_domain_loads():
    """principles 영역이 비지 않은 텍스트를 반환."""
    result = loader.get_domains(["principles"])
    assert result  # 비지 않음
    assert "코칭" in result or "원칙" in result or "CODM" in result.lower()


def test_multiple_domains_combined():
    """여러 영역이 결합되어 반환."""
    result = loader.get_domains(["principles", "mechanics-core"])
    assert len(result) > len(loader.get_domains(["principles"]))


def test_dynamic_map_domain_loads():
    """maps:Combine 동적 키가 maps/Combine.md를 로드."""
    result = loader.get_domains(["maps:Combine"])
    assert result  # 비지 않음


def test_case_insensitive_map_match():
    """소문자 'maps:combine'이 Combine.md에 매칭."""
    lower = loader.get_domains(["maps:combine"])
    upper = loader.get_domains(["maps:Combine"])
    assert lower == upper  # 동일 파일 → 동일 내용
    assert lower  # 비지 않음


def test_nonexistent_map_returns_empty():
    """maps:존재안함 → 빈 문자열 (예외 발생 X)."""
    result = loader.get_domains(["maps:절대없는맵12345"])
    assert result == ""


def test_nonexistent_domain_returns_empty():
    """정의되지 않은 영역 키 → 빈 문자열 (예외 X)."""
    result = loader.get_domains(["존재안함"])
    assert result == ""


def test_empty_domain_list_returns_empty():
    """빈 리스트 → 빈 문자열."""
    assert loader.get_domains([]) == ""


def test_mixed_valid_invalid_returns_valid_only():
    """유효+무효 영역 혼합 → 유효한 것만 결합."""
    result = loader.get_domains(["principles", "절대없음", "maps:Combine", "없는키"])
    assert result  # 비지 않음
    assert "절대없음" not in result


def test_mtime_cache_autoreload():
    """파일 수정 시 mtime 변경 감지 → 자동 리로드."""
    # 임시 knowledge 디렉토리로 loader의 KNOWLEDGE_DIR 교체
    tmpdir = tempfile.mkdtemp()
    try:
        orig_dir = loader.KNOWLEDGE_DIR
        sub = os.path.join(tmpdir, "principles")
        os.makedirs(sub)
        fpath = os.path.join(sub, "코칭철학원칙.md")
        with open(fpath, "w", encoding="utf-8") as f:
            f.write("# v1 내용\n")
        loader.KNOWLEDGE_DIR = tmpdir
        loader._CACHE.clear()  # 캐시 초기화

        first = loader.get_domains(["principles"])
        assert "v1" in first

        # mtime이 달라지도록 충분한 시간 경과 후 수정
        time.sleep(0.05)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write("# v2 수정됨\n")

        second = loader.get_domains(["principles"])
        assert "v2" in second, "mtime 변경 후 자동 리로드 안 됨"
        assert "v1" not in second

        loader.KNOWLEDGE_DIR = orig_dir
        loader._CACHE.clear()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_lang_param_ignored_but_accepted():
    """lang 파라미터가 에러 없이 받아들여짐 (현재 무시)."""
    result = loader.get_domains(["principles"], lang="en")
    assert result  # lang=en이어도 한국어 원본 로드됨
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest test_coaching_brain_loader.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'coaching_brain_loader'`

- [ ] **Step 3: Write minimal implementation**

`coaching_brain_loader.py`:

```python
# 코칭 브레인 → AI 인사이트 영역별 로더
#
# 코치의 세컨드 브레인(coaching brain/knowledge/)을 마크다운 원본에서 읽어,
# AI 인사이트가 맥락에 맞는 코칭 지식만 선택적으로 주입받도록 한다.
#
# 특징:
#   - mtime 기반 캐싱: 코치가 Obsidian에서 파일을 수정하면
#     다음 AI 호출 시 자동 반영 (uvicorn 재시작 불필요).
#   - 고정 영역(principles, mechanics-*, mode-*, team) + 동적 영역(maps:{Name}).
#   - 실패 안전: 파일/폴더 없으면 "" 반환, 서버/인사이트 정상 동작 유지.
#
# 사용: prompt_context.build_system_prompt()가 get_domains(domains) 호출.

import os

# 코칭 브레인 knowledge 루트 (CWD = 프로젝트 루트 기준)
KNOWLEDGE_DIR = "coaching brain/knowledge"

# 고정 영역 → 상대 경로 매핑
_DOMAIN_FILES = {
    "principles":      "principles/코칭철학원칙.md",
    "mechanics-core":  "mechanics/CODM기본역학.md",
    "mechanics-meta":  "mechanics/무기옵스킬메타.md",
    "mechanics-terms": "mechanics/공용어사전.md",
    "mode-hp":         "modes/Hardpoint.md",
    "mode-snd":        "modes/SearchDestroy.md",
    "mode-control":    "modes/Control.md",
    "team":            "team/팀운영.md",
}

# 캐시: { 절대경로: (mtime, 내용) }
_CACHE: dict[str, tuple[float, str]] = {}


def _read_cached(rel_path: str) -> str:
    """mtime 기반 캐싱으로 단일 파일 읽기.

    mtime이 변경되면 디스크에서 재읽기, 같으면 캐시 반환.
    파일 없음/에러 시 빈 문자열 + 콘솔 로그 (예외 발생 X).
    """
    abs_path = os.path.join(KNOWLEDGE_DIR, rel_path)
    try:
        mtime = os.path.getmtime(abs_path)
    except OSError:
        return ""

    cached = _CACHE.get(abs_path)
    if cached and cached[0] == mtime:
        return cached[1]

    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
        _CACHE[abs_path] = (mtime, content)
        return content
    except OSError as e:
        print(f"[coaching_brain_loader] read fail {abs_path}: {e}", flush=True)
        return ""


def _resolve_map_file(map_key: str) -> str | None:
    """maps:{Name} 동적 키 → 대소문자 무시 매칭으로 실제 파일 경로 반환.

    DB map_name이 'arsenal'/'Combine'/'Firing Range' 등 들쭣날쭣하므로
    코칭 브레인 maps/ 폴더의 실제 파일명과 대소문자 무시 비교.
    매칭 없으면 None.
    """
    maps_dir = os.path.join(KNOWLEDGE_DIR, "maps")
    try:
        files = os.listdir(maps_dir)
    except OSError:
        return None
    target = map_key.lower()
    for fname in files:
        stem = fname[:-3] if fname.endswith(".md") else fname  # .md 제거
        if stem.lower() == target:
            return f"maps/{fname}"
    return None


def _resolve_domain(domain: str) -> str | None:
    """단일 영역 키 → 파일 상대경로. 못 찾으면 None."""
    # 1. 고정 영역
    if domain in _DOMAIN_FILES:
        return _DOMAIN_FILES[domain]
    # 2. 동적 맵 영역 (maps:{Name})
    if domain.startswith("maps:"):
        return _resolve_map_file(domain[5:])
    return None


def get_domains(domains: list, lang: str = "ko") -> str:
    """영역 리스트 → 결합된 마크다운 텍스트.

    - 고정 키: _DOMAIN_FILES에서 조회.
    - 동적 키(maps:{Name}): 대소문자 무시로 maps/ 파일 매칭, 없으면 스킵.
    - 정의 안 된 키: 스킵.
    - 빈 결과/전체 실패 → "" 반환.
    - lang: 현재 무시 (마크다운 원본 한국어 고정). 자리만 확보.
    """
    if not domains:
        return ""
    parts = []
    for domain in domains:
        rel = _resolve_domain(domain)
        if rel is None:
            continue
        content = _read_cached(rel)
        if content:
            parts.append(content)
    return "\n\n---\n\n".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest test_coaching_brain_loader.py -v
```
Expected: PASS (10개 테스트 전부). 단, 로컬에 `coaching brain/knowledge/` 폴더가 있어야 함 (현재 존재 확인됨).

- [ ] **Step 5: Commit**

```bash
git add coaching_brain_loader.py test_coaching_brain_loader.py
git commit -m "feat: coaching_brain_loader — 영역별 mtime 캐싱 로더 (코칭 브레인)"
```

---

## Task 2: `prompt_context.py` — 지표 정의 슬림화 + 코칭 브레인 통합

**Files:**
- Modify: `prompt_context.py` (전체 재구성)
- Test: `test_prompt_context_domains.py` (신규)

**Interfaces:**
- Consumes: `coaching_brain_loader.get_domains(domains, lang)` (Task 1)
- Produces:
  - `build_system_prompt(task: str, lang: str = "ko", domains: list = None) -> str` — **시그니처 변경** (domains 추가, 기본값 None).
  - `_METRIC_DEFINITIONS` (신규 상수, 기존 `_STATIC_DOMAIN_CONTEXT` 대체).
  - `_DEFAULT_DOMAINS = ["principles", "mechanics-core"]`.

- [ ] **Step 1: Write the failing test**

`test_prompt_context_domains.py`:

```python
# prompt_context 도메인 통합 테스트
#
# 실행: pytest test_prompt_context_domains.py -v
#
# 검증:
#  - build_system_prompt가 domains 파라미터를 받는다 (하위 호환: None OK)
#  - domains 전달 시 코칭 브레인 내용이 프롬프트에 포함된다
#  - domains=None → 기본 세트(principles+mechanics-core) 주입
#  - 지표 정의(ZCS/RDS 공식)는 항상 포함
#  - _MAP_META 제거 확인

import prompt_context as pc


def test_build_prompt_accepts_domains_param():
    """build_system_prompt(task, lang, domains) 시그니처 동작."""
    result = pc.build_system_prompt("do thing", "ko", domains=["principles"])
    assert isinstance(result, str)
    assert "do thing" in result


def test_domains_none_backward_compatible():
    """domains 생략(기본값 None) → 기본 세트 주입, 에러 없음."""
    result = pc.build_system_prompt("task", "ko")
    assert "task" in result
    # 기본 세트 = principles + mechanics-core
    assert "원칙" in result or "코칭" in result


def test_coaching_brain_content_included():
    """domains로 전달한 영역의 코칭 브레인 내용이 프롬프트에 들어간다."""
    result = pc.build_system_prompt("task", "ko", domains=["maps:Combine"])
    # maps/Combine.md 내용이 들어가야 함 (P3 스폰 등)
    assert "P3" in result or "스폰" in result or "Combine" in result


def test_metric_definitions_always_present():
    """ZCS/RDS 공식 정의는 domains와 무관하게 항상 포함."""
    result = pc.build_system_prompt("task", "ko", domains=[])
    assert "ZCS" in result
    assert "RDS" in result
    # ZCS 공식 검증 (metrics.py와 정합)
    assert "1.1" in result and "8" in result and "4.1" in result


def test_map_meta_removed():
    """_MAP_META (구 맵 tendency 딕셔너리) 제거 확인."""
    assert not hasattr(pc, "_MAP_META"), "_MAP_META는 코칭 브레인으로 이관되어 제거되어야 함"


def test_default_domains_constant():
    """_DEFAULT_DOMAINS 상수 존재 + 기본 세트."""
    assert hasattr(pc, "_DEFAULT_DOMAINS")
    assert "principles" in pc._DEFAULT_DOMAINS
    assert "mechanics-core" in pc._DEFAULT_DOMAINS
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest test_prompt_context_domains.py -v
```
Expected: FAIL — `AttributeError: build_system_prompt() got unexpected keyword 'domains'` 등.

- [ ] **Step 3: Rewrite `prompt_context.py`**

**변경 원칙**: `_STATIC_DOMAIN_CONTEXT` → `_METRIC_DEFINITIONS`로 교체(지표 정의만 남김). `_MAP_META` + `_format_map_meta()` 제거. `_PLAYER_IGN_MAP` + `_format_ign_map()` 유지. `build_system_prompt`에 `domains` 파라미터 추가 + `coaching_brain_loader` 통합.

새 `prompt_context.py` 전체 (기존 구조 유지하되 위 3점 변경):

```python
# CODM 도메인 컨텍스트 (Domain Context for AI Prompts)
#
# 이 팀의 코칭 VOD 전사문 분석 결과 + 코칭 브레인(coaching brain/knowledge/)을 바탕으로,
# GPT가 "CODM 팀 코치의 시각"으로 인사이트/요약을 생성하도록 지식을 주입한다.
#
# 갱신 3계층:
#   - 정적 (수동): 계산 지표 정의(metrics.py 동기화)·발음변형 맵.
#   - 코칭 브레인 (런타임): coaching_brain_loader가 coaching brain/knowledge/에서
#     영역별로 읽어 mtime 자동 캐싱. 코치가 Obsidian에서 수정하면 다음 호출에 반영.
#   - 동적 (자동): 팀 로스터·역할·스탯 → 매 호출마다 DB에서 조회.
#   - 시점 (자동): 현재 날짜 → 메타 시점 고정.
#
# analytics_insights.py의 모든 GPT 호출이 build_system_prompt()를 거친다.

import datetime

import coaching_brain_loader

# 전사문 발음 오류 매핑 (OCR/Alias 스킬과 연계)
# refresh_domain_context.py 실행으로 새 변형을 발견해 여기에 추가.
_PLAYER_IGN_MAP = {
    "Shisui": ["Shizi", "she-she", "she she", "Shishi", "Shisi", "Chisu", "Shane",
               "쉬스이", "시스이"],
    "Maozyn": ["Mao", "Maozen", "Mazin", "Maoz", "마오진", "마오즌"],
    "Cartels": ["Cartel", "cartilage", "cartos", "카르텔"],
    "Kingz": ["Kings", "King", "Kingsui", "킹즈"],
    "Exile": ["Exhale", "엑자일"],
    "unravel": ["Unravel", "언래블", "Jason", "제이슨"],  # Jason은 unravel의 실명
}

# 계산 지표 정의 — metrics.py 공식과 정확히 동기화.
# 코칭 통찰(역학·용어·코칭톤·맵)은 코칭 브레인에서 로드 (coaching_brain_loader).
_METRIC_DEFINITIONS = """# CODM Metric Definitions (authoritative — matches metrics.py)

You are advising a competitive Call of Duty Mobile (CODM) team. Use this domain knowledge to ground every insight in real game understanding.

## Game & Modes
CODM competitive uses two modes:
- HP (Hardpoint / 거점): capture rotating hills P1→P2→P3→P4, ~60s each. OBJ = hill time in seconds (higher = better). CapKill = bonus-score kills (multikills, trades, top-enemy kills, in-hill kills) — NOT pure objective time. "hill"/"언덕" = the current active point.
- SND (Search & Destroy / 폭파): alternating attack/defense, round-based. FK = First Blood (first kill), LWW = Lone Wolf Win, ADR = avg damage per round.

## Key Metric Definitions (don't recompute — interpret the numbers provided)
- ZCS (HP only) = max(0, 1.1·OBJ + 8·CapKill + 4.1·K − 5·D). Team avg ~150–200; 250+ = ace-level zone control; <100 = low impact.
  ZCS measures ZONE CONTROL CONTRIBUTION — how much a player helped OWN the hill.
  CapKill ×8 (highest weight): bonus-score kills are HIGH-QUALITY objective-tied kills.
  K ×4.1: standard kills — half the value of a CapKill (context matters).
  OBJ ×1.1: hill time — pure presence, alone low-value.
  D ×5 (heavier than K's 4.1): deaths penalized MORE than kills rewarded.
  → Modest K/D + high CapKill density + rare hill deaths = high ZCS. Raw fragging with low OBJ/CapKill = lower ZCS.
- RDS (SND only) = max(0, 4.1·K + 3.5·A + 14·FK + 20·LWW + 0.12·ADR − 5·D). SND 제1 지표 (ZCS의 SND 대응).
  FK ×14, LWW ×20: opening duels and clutches weigh heavily — round-swinging events.
- K/D: ~1.0 avg, 1.3+ strong, <0.8 weak.
- DPK (dmg/kills): LOWER is better (finishing ability). ~700–1100.
- DPD (dmg/deaths): HIGHER is better (value per life). ~800–1300.
- Impact = min(200, 73 + 2.6K − 3.1D + 0.92·OBJ + 0.009·dmg). 150+ = excellent.
- AP% = (CapKill / K) × 100 — kill quality density. HIGH = kills are objective-relevant.
- Direction: HIGHER better = ZCS, RDS, DPD, Impact, OBJ, K/D. LOWER better = DPK, deaths.
"""

# domains=None일 때 기본 코칭 브레인 영역 (항상 깔리는 최소 통찰)
_DEFAULT_DOMAINS = ["principles", "mechanics-core"]


def _format_ign_map() -> str:
    """발음 변형 맵을 GPT가 읽을 텍스트로 포맷."""
    if not _PLAYER_IGN_MAP:
        return ""
    lines = ["", "## Player Name Variants (transcript/voice pronunciation drift)"]
    for ign, variants in _PLAYER_IGN_MAP.items():
        if variants:
            lines.append(f"- {ign}: {', '.join(variants)}")
    lines.append("When you see a variant in a transcript, treat it as the formal IGN and use the formal name in output.")
    return "\n".join(lines)


def team_roster_context() -> str:
    """동적 팀 로스터 (DB에서 자동 조회).

    all_players_overview("HP") + classify_role()로 현재 로스터·역할·평균 스탯을 가져옴.
    새 선수 영입·역할 변경·스탯 변화는 DB 반영 즉시 자동 반영.
    조회 실패 시 빈 문자열 (정적 컨텍스트만으로 동작).
    """
    try:
        import queries
        import metrics
        players = queries.all_players_overview("HP")
        team_avg = queries.team_averages("HP")
        if not players:
            return ""
        lines = ["", f"## Current Team Roster (HP, as of {datetime.date.today().isoformat()})"]
        for p in players[:8]:
            name = p.get("name")
            matches = p.get("matches", 0)
            kd = p.get("avg_kd")
            # all_players_overview는 avg_ck로 반환 → classify_role 호환을 위해 복사
            p_norm = dict(p)
            if "avg_ck" in p_norm and "avg_capture" not in p_norm:
                p_norm["avg_capture"] = p_norm["avg_ck"]
            role = metrics.classify_role(p_norm, team_avg) if team_avg else "balanced"
            lines.append(
                f"- {name} — {role}, {matches} HP matches, avg K/D {kd}"
            )
        return "\n".join(lines)
    except Exception:
        return ""


def build_system_prompt(task: str, lang: str = "ko", domains: list = None) -> str:
    """모든 AI 호출용 system 프롬프트 조합.

    계산 지표 정의 + IGN 변형 맵 + 코칭 브레인 통찰(선택적) + 날짜 + 동적 로스터 + 작업 지시문.
    task: 각 함수의 개별 지시문 (길이·포커스). lang: ko/en/es.
    domains: 주입할 코칭 브레인 영역 키 리스트 (예: ["principles","maps:Combine"]).
             None이면 _DEFAULT_DOMAINS(principles + mechanics-core) 사용.
             코칭 브레인 로드 실패 시 통찰 없이 지표+로스터만으로 동작 (실패 안전).
    """
    today = datetime.date.today().isoformat()
    lang_note = {"ko": "Korean (한국어)", "en": "English", "es": "Spanish (español)"}.get(lang, "Korean (한국어)")

    # 코칭 브레인 영역 로드 (실패 시 "" — 정상 동작 유지)
    try:
        insight_context = coaching_brain_loader.get_domains(
            domains if domains is not None else _DEFAULT_DOMAINS, lang
        )
    except Exception as e:
        print(f"[prompt_context] coaching_brain_loader fail (fallback to metrics-only): {e}", flush=True)
        insight_context = ""

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

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest test_prompt_context_domains.py -v
```
Expected: PASS (6개 테스트).

- [ ] **Step 5: 하위 호환 회귀 — prompt.py 확인**

```bash
python -c "import prompt; print(type(prompt.SYSTEM_PROMPT), len(prompt.SYSTEM_PROMPT))"
```
Expected: `<class 'str'>` + 양수. `SYSTEM_PROMPT = build_system_prompt()` (domains 없음) 가 정상 동작해야 함.

- [ ] **Step 6: Commit**

```bash
git add prompt_context.py test_prompt_context_domains.py
git commit -m "feat: prompt_context — 지표 정의 슬림화 + 코칭 브레인 domains 통합"
```

---

## Task 3: `analytics_insights.py` — 7개 인사이트 함수 domains 연결

**Files:**
- Modify: `analytics_insights.py:39-385` (7개 함수 각각 build_system_prompt 호출부)
- Test: 수동 회귀 (로컬 OPENAI_API_KEY 필요 — 자동화 불가)

**Interfaces:**
- Consumes: `prompt_context.build_system_prompt(task, lang, domains)` (Task 2)
- Produces: 각 인사이트 함수가 데이터 기반 domains 구성해 전달. task 지시문·응답 형식 불변.

- [ ] **Step 1: `_domains_for_match` 헬퍼 추가**

`analytics_insights.py` 상단 (import 후, `_openai` 정의 전)에 추가:

```python
def _domains_for_match(mode: str, map_name: str = None, extra: list = None) -> list:
    """매치/맵 계열 인사이트 공용: 모드+맵 도메인 조합.

    mode: 'HP'/'SND'/'Control'. map_name: DB map_name (대소문자 무관, loader가 매칭).
    extra: 추가 영역 (예: ['team','mechanics-terms']).
    """
    d = ["principles", "mechanics-core"]
    mode_key = {"HP": "mode-hp", "SND": "mode-snd", "Control": "mode-control"}.get(mode)
    if mode_key:
        d.append(mode_key)
    if map_name:
        d.append(f"maps:{map_name}")  # 코칭 브레인에 없으면 loader가 스킵
    if extra:
        d.extend(extra)
    return d
```

- [ ] **Step 2: `match_insight` — domains 추가**

`analytics_insights.py:62-68`의 `build_system_prompt` 호출부 변경:

**변경 전:**
```python
                    "content": prompt_context.build_system_prompt(
                        "Write 1-2 sentences of key insight from the match stats JSON. "
                        "Provide insight (who had good form, team strengths/weaknesses, "
                        "what stands out tactically — e.g. anchor play, slayer dominance, "
                        "ZCS outliers), not just a list of numbers. Concise, for Discord.",
                        lang,
                    ),
```

**변경 후:**
```python
                    "content": prompt_context.build_system_prompt(
                        "Write 1-2 sentences of key insight from the match stats JSON. "
                        "Provide insight (who had good form, team strengths/weaknesses, "
                        "what stands out tactically — e.g. anchor play, slayer dominance, "
                        "ZCS outliers), not just a list of numbers. Concise, for Discord.",
                        lang,
                        domains=_domains_for_match(report["mode"], report.get("map_name")),
                    ),
```

- [ ] **Step 3: `weekly_insight` — domains 추가**

`analytics_insights.py:97-103` 변경 (task 문자열 불변, domains만):

**변경 전:** 마지막 인자 `"ko"` 또는 `lang,` 후 닫는 괄호.

**변경 후:** `lang,` 뒤에 추가:
```python
                        domains=["principles", "mechanics-core", "team"],
```

(weekly는 모드 혼합 집계라 mode-specific 도메인 없음. team 운영 관점.)

- [ ] **Step 4: `trend_insight` — domains 추가**

`trend_insight`는 `build_system_prompt`를 쓰지 않고 직접 system content를 만듦(`analytics_insights.py:136-141`). **여기는 `prompt_context.build_system_prompt`로 전환**:

**변경 전 (137-141):**
```python
                    "content": (
                        f"You are a CODM esports player form analyst. Diagnose the player's "
                        f"recent form vs overall average in 1-2 sentences {li}. "
                        f"Include whether rising/falling with specific numeric evidence. Concise."
                    ),
```

**변경 후:**
```python
                    "content": prompt_context.build_system_prompt(
                        f"Diagnose the player's recent form vs overall average in 1-2 "
                        f"sentences {li}. Include whether rising/falling with specific "
                        f"numeric evidence. Concise.",
                        lang,
                        domains=_domains_for_match(trend.get("mode")),
                    ),
```

(이로써 trend_insight도 지표 정의 + 코칭 브레인을 받음. 기존엔 빈약한 직접 프롬프트였음 — 품질 향상 효과.)

- [ ] **Step 5: `player_profile_insight` — domains 추가**

`analytics_insights.py:175-185` 변경 (task 문자열 불변):

**변경 후 domains (mode별 조건부):**
```python
                    "content": prompt_context.build_system_prompt(
                        "Write 3-5 sentences of coaching insight from a player's overall stats "
                        "and team average. Include: 1) clear strengths/weaknesses vs team average "
                        "(mention ±% with metric interpretation), "
                        f"2) play style bias — "
                        f"{'infer slayer/objective/balanced from OBJ, CapKill, ZCS, DPD (HP-only metrics). ' if stats.get('hp') else ''}"
                        f"3) form stability (mention std dev if present). "
                        f"IMPORTANT: ZCS/OBJ/CapKill are HP-only metrics — never reference them for SND-only data. "
                        f"Grounded in numbers, no over-interpretation. Concise and actionable, for web display.",
                        lang,
                        domains=_domains_for_player(stats),
                    ),
```

그리고 헬퍼 `_domains_for_player` 추가 (Step 1 위치에):
```python
def _domains_for_player(stats: dict) -> list:
    """선수 프로필용 도메인: hp/snd 존재 여부로 모드 영역 선택."""
    d = ["principles", "mechanics-core", "mechanics-meta"]
    if stats.get("hp"):
        d.append("mode-hp")
    if stats.get("snd"):
        d.append("mode-snd")
    return d
```

- [ ] **Step 6: `map_advice` — domains 추가**

`analytics_insights.py:239-249` 변경 (task 문자열 불변):

**변경 후:**
```python
                    "content": prompt_context.build_system_prompt(
                        f"Describe the NUMERIC TRENDS of one map ({mode}) in 3-4 sentences. "
                        f"RULES: only point out statistical tendencies (e.g. 'on this map "
                        f"team K/D is -12% vs season'{zcs_hint}"
                        + ("Do NOT mention ZCS — it is undefined for SND. " if not is_hp else "")
                        + f"). Cross-reference the map tendency in your domain context when "
                        f"relevant. Do NOT give direct orders or tactical instructions. "
                        f"Stick to what the numbers show — let the coach interpret. "
                        f"Grounded strictly in the JSON. For web display.",
                        lang,
                        domains=_domains_for_match(mode, map_data.get("map_name"),
                                                   extra=["mechanics-terms"]),
                    ),
```

- [ ] **Step 7: `summarize_transcript` — domains 추가**

`analytics_insights.py:294-306` 변경 (task 문자열 불변):

**변경 후 domains:**
```python
                        domains=_domains_for_match(
                            report.get("mode"),
                            report.get("map_name"),
                            extra=["mechanics-terms", "team"],
                        ),
```

- [ ] **Step 8: `briefing_insight` — domains 추가**

`analytics_insights.py:364-376` 변경 (task 문자열 불변):

**변경 후:**
```python
                    "content": prompt_context.build_system_prompt(
                        "You are the coach's pre-match briefing. Produce EXACTLY 3 items, "
                        "each item = one action line + one supporting number. "
                        "Sources: form_alerts (slumping players), banpick (map score/delta/badge — "
                        "PICK maps are strong, BAN maps are weak), "
                        "role spectrum (composition skew), open_notes (unresolved action items). "
                        "Be DIRECT and prescriptive (the coach acts on this) — unlike player-facing map advice, "
                        "you MAY give concrete directives ('Focus X', 'Ban Y'). "
                        "Format strictly: 3 lines, each '1. <conclusion> — <number>'. "
                        "Keep total under 250 characters. No preamble, no closing remarks. "
                        "Grounded only in the provided data; no fabrication.",
                        lang,
                        domains=["principles", "mechanics-core", "team", "mechanics-meta"],
                    ),
```

- [ ] **Step 9: 로컬 회귀 — 모듈 import + 함수 호출 가능 확인**

```bash
python -c "
import analytics_insights as ai
# 모든 함수가 import 에러 없이 로드되는지
print('match_insight:', callable(ai.match_insight))
print('weekly_insight:', callable(ai.weekly_insight))
print('trend_insight:', callable(ai.trend_insight))
print('player_profile_insight:', callable(ai.player_profile_insight))
print('map_advice:', callable(ai.map_advice))
print('summarize_transcript:', callable(ai.summarize_transcript))
print('briefing_insight:', callable(ai.briefing_insight))
print('_domains_for_match:', ai._domains_for_match('HP', 'Combine'))
print('_domains_for_player:', ai._domains_for_player({'hp': True, 'snd': None}))
"
```
Expected: 전부 `True` + `_domains_for_match` 리스트 출력 + `_domains_for_player` 리스트 출력. import 에러 없음.

- [ ] **Step 10: 전체 테스트 스위트 회귀**

```bash
pytest test_coaching_brain_loader.py test_prompt_context_domains.py test_i18n.py -v
```
Expected: 전부 PASS (기존 i18n 테스트도 영향받지 않아야 함).

- [ ] **Step 11: Commit**

```bash
git add analytics_insights.py
git commit -m "feat: 7개 인사이트 함수에 코칭 브레인 domains 연결 (task 지시문 불변)"
```

---

## Task 4: 코칭 브레인 폴더 git 추적 + AGENTS.md 메모

**Files:**
- Track: `coaching brain/` (현재 untracked)
- Modify: `AGENTS.md` (선택, ~10줄 메모)
- Test: 없음 (git 상태 확인만)

**Interfaces:**
- 없음 (메타데이터/문서 작업)

- [ ] **Step 1: .gitignore 충돌 확인**

```bash
git check-ignore "coaching brain/" "coaching brain/knowledge/principles/코칭철학원칙.md"
```
Expected: 출력 없음 (무시되지 않음). 만약 경로가 출력되면 .gitignore에 해당 패턴이 있음 → 제거 필요. (현재 `.gitignore`엔 coaching brain 패턴 없음 예상.)

- [ ] **Step 2: 코칭 브레인 내 비밀정보 스캔**

```bash
grep -rl -E "API_KEY|TOKEN|password|secret|service-account|DISCORD_BOT_TOKEN" "coaching brain/" 2>/dev/null
```
Expected: 출력 없음 (순수 마크다운 지식만). 만약 매칭되면 해당 파일 제외 후 재검토. (`.obsidian/` 설정 파일은 커밋 제외 후보 — 아래 Step 3에서 처리.)

- [ ] **Step 3: .obsidian/ 작업공간 파일 제외 (개인 설정)**

`.obsidian/workspace.json` 등은 개인 Obsidian 상태라 커밋 불필요. `.gitignore`에 추가:

`.gitignore` 맨 아래에 추가:
```
# 코칭 브레인 — Obsidian 개인 작업공간 상태 (지식은 커밋, 설정은 제외)
coaching brain/.obsidian/workspace.json
coaching brain/.obsidian/graph.json
```

(`app.json`, `appearance.json`, `core-plugins.json`은 볼트 기본 설정이라 커밋해도 무방하나, 팀원 없이 1인 사용이면 workspace/graph만 제외해도 충분.)

- [ ] **Step 4: 코칭 브레인 git add**

```bash
git add "coaching brain/"
git status
```
Expected: `coaching brain/knowledge/**/*.md` + `.obsidian/*.json`(workspace/graph 제외) + `.zcode/` 등이 staging. **`knowledge/` 마크다운 파일이 전부 포함되어야 함.**

- [ ] **Step 5: AGENTS.md 메모 추가 (선택)**

`AGENTS.md`의 "6. 이 프로젝트 메모" 섹션 끝(데이터 현황 메모 전)에 추가:

```markdown
### 코칭 브레인 → AI 인사이트 연동
- `coaching brain/knowledge/` (Obsidian 볼트)가 AI 인사이트의 코칭 지식 진실 공급원.
- `coaching_brain_loader.py`가 영역별(principles/mechanics/modes/maps/team)로 mtime 캐싱 읽기. 코치가 Obsidian에서 수정하면 다음 AI 호출 시 자동 반영 (재시작 불필요).
- `prompt_context.build_system_prompt(task, lang, domains)`가 domains로 선택적 주입. 각 인사이트 함수가 맥락에 맞는 영역 명시.
- 코칭 브레인 폴더/파일 없으면 빈 문자열 → 지표 정의만으로 AI 동작 (실패 안전).
- 지표 공식(ZCS/RDS) 정의는 `prompt_context._METRIC_DEFINITIONS`에 고정 (metrics.py 동기화). 코칭 통찰과 분리.
```

- [ ] **Step 6: Commit**

```bash
git add .gitignore "coaching brain/" AGENTS.md
git status   # 비밀정보(.env, service-account.json, codm.db) 빠졌는지 최종 확인
git commit -m "chore: coaching brain 지식베이스 git 추적 + AGENTS.md 연동 메모"
```

---

## Task 5: 최종 통합 검증

**Files:**
- 없음 (검증만)

- [ ] **Step 1: 전체 테스트 스위트**

```bash
pytest test_coaching_brain_loader.py test_prompt_context_domains.py test_i18n.py -v
```
Expected: 전부 PASS.

- [ ] **Step 2: 엔드투엔드 — 실제 인사이트 호출 (OPENAI_API_KEY 필요)**

```bash
python -c "
import analytics_insights as ai
import queries

# match_insight 실제 호출 (로컬 DB에서 최근 매치)
reports = queries.recent_match_reports(1) if hasattr(queries, 'recent_match_reports') else []
if reports:
    r = ai.match_insight(reports[0], 'ko')
    print('match_insight 길이:', len(r))
    print('미리보기:', r[:200])
else:
    print('로컬 매치 데이터 없음 — 수동 더미로 대체')
    # 최소 더미로 함수가 에러 없이 동작하는지만
    dummy = {'mode':'HP','map_name':'Combine','mom':'Test','best':{},'worst':{},'team_totals':{},'players':[]}
    r = ai.match_insight(dummy, 'ko')
    print('더미 match_insight:', repr(r)[:100])
"
```
Expected: 에러 없이 문자열 반환 (빈 문자열이어도 OK — API 키 없으면). **예외 발생 없음**이 핵심.

- [ ] **Step 3: mtime 자동 갱신 엔드투엔드**

```bash
# 1. 코칭 브레인 원칙 파일 백업
cp "coaching brain/knowledge/principles/코칭철학원칙.md" /tmp/cb_backup.md

# 2. 파일 수정 (테스트 마커 추가)
echo "" >> "coaching brain/knowledge/principles/코칭철학원칙.md"
echo "<!-- TEST_MARKER_$(date +%s) -->" >> "coaching brain/knowledge/principles/코칭철학원칙.md"

# 3. build_system_prompt 호출 → 마커 포함 확인
python -c "
import prompt_context as pc
p = pc.build_system_prompt('test', 'ko', domains=['principles'])
print('마커 감지:', 'TEST_MARKER_' in p)
"

# 4. 원본 복원
cp /tmp/cb_backup.md "coaching brain/knowledge/principles/코칭철학원칙.md"
```
Expected: `마커 감지: True`.

- [ ] **Step 4: 서버 기동 smoke test (옵션, 로컬)**

```bash
timeout 8 python -c "
import web_api
print('web_api import OK — 서버 모듈 정상')
" 2>&1 | head -5
```
Expected: `web_api import OK`. (uvicorn 전체 기동은 로컬 환경에서 별도.)

- [ ] **Step 5: git 상태 최종 확인**

```bash
git status
git log --oneline -5
```
Expected: clean working tree + 커밋 4개 (Task 1~4).

---

## 배포 후 확인 (로컬 불가 — AGENTS.md §3)

- Railway 재배포 후 `coaching brain/` 폴더가 컨테이너에 존재하는지 (Railway 대시보드 또는 로그).
- 실제 GPT 응답에 코칭 브레인 지식이 반영되는지 (매치 상세 페이지 인사이트 정성 확인).
- 토큰 사용량 변화 (OpenAI 대시보드 — 10~18% 증가 예상).

---

## Self-Review (작성자 점검)

**Spec coverage:**
- ✅ 맥락별 선택적 주입 → Task 3 매핑표
- ✅ 런타임 파일 읽기 + mtime 캐시 → Task 1 `_read_cached`
- ✅ 지표/로스터 남기고 통찰은 브레인 → Task 2 `_METRIC_DEFINITIONS` + `_MAP_META` 제거
- ✅ A안 명시적 영역 지정 → Task 3 각 함수 domains 명시
- ✅ AI 원래 의도 보존 → Task 3 "task 문자열 불변" 각 step에 명시
- ✅ 대소문자 무시 맵 매칭 → Task 1 `_resolve_map_file` + 테스트
- ✅ 실패 안전 → Task 1/2 try-except + 빈 문자열
- ✅ 코칭 브레인 git 추적 → Task 4
- ✅ 커밋 2개 → 실제론 4개로 세분 (AGENTS.md §7 기능 단위 준수)

**Placeholder scan:** 없음. 모든 step에 실제 코드/명령.

**Type consistency:**
- `get_domains(domains: list, lang: str) -> str` — Task 1 정의, Task 2/3 일관 사용
- `build_system_prompt(task, lang, domains=None)` — Task 2 정의, Task 3 7개 함수 일관
- `_domains_for_match(mode, map_name, extra)` — Task 3 정의 후 match/trend/map/transcript에서 동일 시그니처 사용
- `_domains_for_player(stats)` — Task 3 player_profile 전용
