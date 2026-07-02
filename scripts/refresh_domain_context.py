# 전사문 도메인 컨텍스트 갱신 보조 스크립트
#
# 새 전사문(transcript)이 추가된 후 실행하면, prompt_context.py에 반영할
# 신규 선수 이름 변형·맵 이름·전술 용어 후보를 콘솔에 제안한다.
#
# 파일을 자동 수정하지 않는다 — 사람이 검토 후 prompt_context.py 편집 → 커밋.
# LLM/API 호출 없음 (비용 0, regex + 빈도 카운트만).
#
# 실행: python scripts/refresh_domain_context.py
#        (CWD는 프로젝트 루트여야 함)

import re
import sys
from collections import Counter
from pathlib import Path

# 루트의 전사문샘플*.md + transcripts/ 폴더 양쪽 스캔
ROOT = Path(__file__).resolve().parent.parent
SEARCH_DIRS = [ROOT, ROOT / "transcripts"]
GLOBS = ["전사문*.md", "전사문샘플*.md", "transcript*.md", "transcript*.txt"]

# 현재 등록된 선수 정식 IGN (prompt_context.py와 동기화)
KNOWN_IGNS = {"Shisui", "Maozyn", "Cartels", "Kingz", "Exile", "unravel"}

# 현재 등록된 발음 변형 (소문자 비교용)
KNOWN_VARIANTS = set()
for v in [
    "shizi", "she-she", "she she", "shishi", "shisi", "chisu", "shane", "쉬스이", "시스이",
    "mao", "maozen", "mazin", "maoz", "마오진", "마오즌",
    "cartel", "cartilage", "cartos", "카르텔",
    "kings", "king", "kingsui", "킹즈",
    "exhale", "엑자일",
    "unravel", "언래블",
]:
    KNOWN_VARIANTS.add(v.lower())

# CODM 공식 맵 + 전사에서 자주 등장한 맵
KNOWN_MAPS = {"Combine", "Summit", "Standoff", "Raid", "Tunnel", "Takeoff",
              "Meltdown", "Coastal", "Hacienda", "Arsenal", "Crash"}

# 전술/도메인 용어 (이미 등록된 것)
KNOWN_TERMS = {"spawn", "push", "rotation", "retake", "trade", "flank", "pinch",
               "hold", "peek", "hill", "trophy", "halftime", "momentum",
               "스폰", "푸시", "로테", "리테", "언덕", "힐", "캡", "거점"}


def collect_files():
    files = []
    for d in SEARCH_DIRS:
        if not d.exists():
            continue
        for g in GLOBS:
            files.extend(sorted(d.glob(g)))
    # 중복 제거
    seen = set()
    unique = []
    for f in files:
        rp = f.resolve()
        if rp not in seen:
            seen.add(rp)
            unique.append(f)
    return unique


def load_text(files):
    chunks = []
    for f in files:
        try:
            chunks.append(f.read_text(encoding="utf-8", errors="ignore"))
        except Exception as e:
            print(f"  [skip] {f.name}: {e}")
    return "\n".join(chunks)


def find_player_variants(text):
    """선수 이름 변형 후보 탐지.

    전략: 정식 IGN 주변 텍스트 + 대문자 시작 고유명사 후보에서
    기존에 등록되지 않은 토큰을 수집. 오탐 많지만 사람이 검토.
    """
    suggestions = {}
    # 1) 정식 IGN의 소문자 변형 패턴 주변에서 유사 토큰
    ign_patterns = {
        "Shisui": r"\b(Shizi|She[\s-]?[Ss]he|Shishi|Shisi|Chisu|쉬스이|시스이)\b",
        "Maozyn": r"\b(Mao(?:zyn|zen|z)?|Mazin|마오진|마오즌)\b",
        "Cartels": r"\b(Cartel|Cartilage|Cartos|카르텔)\w*",
        "Kingz": r"\b(Kings?|Kingsui|킹즈)\b",
        "Exile": r"\b(Exhale|엑자일)\b",
    }
    for ign, pat in ign_patterns.items():
        found = set(re.findall(pat, text, flags=re.IGNORECASE))
        new = {f for f in found if f.lower() not in KNOWN_VARIANTS and f.lower() != ign.lower()}
        if new:
            suggestions[ign] = sorted(new)

    # 2) 추가: 의문의 대문자 고유명사 (선수일 가능성)
    proper = re.findall(r"\b[A-Z][a-z]{3,8}\b", text)
    proper_freq = Counter(p for p in proper if p.lower() not in KNOWN_VARIANTS
                          and p not in KNOWN_IGNS and p not in KNOWN_MAPS)
    suspects = [w for w, c in proper_freq.most_common(40) if c >= 3]
    return suggestions, suspects


def find_new_maps(text):
    """알려지지 않은 맵 이름 후보 (대문자 시작, 빈도 높음)."""
    proper = re.findall(r"\b[A-Z][a-z]{3,10}\b", text)
    freq = Counter(proper)
    candidates = []
    for w, c in freq.most_common():
        if c < 3:
            break
        if w in KNOWN_MAPS or w in KNOWN_IGNS:
            continue
        # 일반 영어 단어/불용어 제외 (대략적)
        if w.lower() in {"the", "this", "that", "they", "there", "then", "what",
                         "when", "with", "from", "have", "been", "will", "just",
                         "like", "know", "think", "going", "yeah", "right",
                         "thing", "things", "maybe", "actually", "something",
                         # 전사 특유 화자/감탄/스페인어 불용어
                         "okay", "well", "because", "what", "pero", "como",
                         "porque", "bueno", "dice", "esto", "este", "esta",
                         "que", "todo", "mismo", "tienes", "tambien", "muy",
                         # CODM 비선수 엔티티 (오퍼레이터/콜아웃은 별도)
                         "yeah", "nigga", "niggas", "bro", "shit", "fuck"}:
            continue
        candidates.append((w, c))
    return candidates[:15]


def find_term_frequencies(text):
    """등록된 전술 용어의 출현 빈도 (컨텍스트 유효성 점검용)."""
    freq = {}
    for term in sorted(KNOWN_TERMS):
        c = len(re.findall(rf"\b{re.escape(term)}\b", text, flags=re.IGNORECASE))
        if c > 0:
            freq[term] = c
    return freq


def main():
    files = collect_files()
    if not files:
        print("전사문 파일을 찾을 수 없음.")
        print(f"검색 위치: {[str(d) for d in SEARCH_DIRS]}")
        print(f"검색 패턴: {GLOBS}")
        sys.exit(1)

    print(f"=== {len(files)}개 전사문 스캔 ===")
    for f in files:
        print(f"  - {f.relative_to(ROOT)}")
    print()

    text = load_text(files)
    print(f"총 {len(text):,}자 분석\n")

    # 1) 선수 변형
    suggestions, suspects = find_player_variants(text)
    print("─── 선수 이름 변형 제안 (prompt_context._PLAYER_IGN_MAP 검토) ───")
    if suggestions:
        for ign, news in suggestions.items():
            print(f"  {ign}: 새 변형 후보 → {', '.join(news)}")
    else:
        print("  새 변형 없음 (이미 등록된 것과 일치).")
    if suspects:
        print(f"\n  미확인 고유명사 후보 (선수/콜아웃 혼재, 검토 필요):")
        for w in suspects[:20]:
            print(f"    {w}")
    print()

    # 2) 맵
    new_maps = find_new_maps(text)
    print("─── 미등록 맵 이름 후보 (prompt_context._MAP_META 검토) ───")
    if new_maps:
        for w, c in new_maps:
            print(f"  {w} ({c}회)")
    else:
        print("  유의미 후보 없음.")
    print()

    # 3) 용어 빈도
    freq = find_term_frequencies(text)
    print("─── 등록된 전술 용어 출현 빈도 (컨텍스트 유효성) ───")
    for term, c in sorted(freq.items(), key=lambda x: -x[1]):
        print(f"  {term}: {c}회")
    print()

    print("─── 다음 단계 ───")
    print("1. 위 제안을 검토해 prompt_context.py의 _PLAYER_IGN_MAP / _MAP_META 편집.")
    print("2. 새 게임 메타·코칭 패턴이 보이면 _STATIC_DOMAIN_CONTEXT도 갱신.")
    print("3. 팀 로스터는 자동(DB 조회)이므로 수동 갱신 불필요.")
    print("4. 커밋.")


if __name__ == "__main__":
    main()
