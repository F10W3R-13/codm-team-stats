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
