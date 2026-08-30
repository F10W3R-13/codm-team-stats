# 코칭 브레인(knowledge/) → AI 인사이트 주입 검증 (오프라인, API 호출 없음)
#
# 확인 항목:
#   1. 고정 영역 파일 존재/크기/수정시각
#   2. maps/ 동적 영역: 실제 파일 목록 + DB map_name 스타일 키 매칭
#   3. 실제 인사이트가 쓰는 도메인 조합 → get_domains() 주입량
#   4. build_system_prompt() 최종 프롬프트에 코칭 지식이 실제 포함되는지 (있/없 diff)
#   5. insight_cache 무효화용 fingerprint()
#
# 사용: python scripts/check_coaching_brain.py
# 배포 DB/볼트 검증: railway run --service Postgres 와 별개로,
# 배포 환경 볼트는 git 에 올라간 coaching brain/knowledge 기준이므로 로컬과 동일.

import os
import sys

# 프롬프트 조립 모듈이 config 를 import 할 수 있게 더미 환경변수 선행 세팅
os.environ.setdefault("DISCORD_BOT_TOKEN", "dummy")
os.environ.setdefault("OPENAI_API_KEY", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import coaching_brain_loader as cbl  # noqa: E402
import prompt_context  # noqa: E402


def _human_size(n: int) -> str:
    return f"{n/1024:.1f}KB" if n >= 1024 else f"{n}B"


def check_fixed_domains() -> int:
    print("== 1. 고정 영역 파일 ==")
    missing = 0
    for key, rel in cbl._DOMAIN_FILES.items():
        path = os.path.join(cbl.KNOWLEDGE_DIR, rel)
        try:
            st = os.stat(path)
            import datetime
            mtime = datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
            print(f"  [OK]   {key:<16} {rel:<40} {_human_size(st.st_size):>8}  {mtime}")
        except OSError:
            missing += 1
            print(f"  [MISS] {key:<16} {rel}  ← 주입 안 됨 (빈 문자열로 안전 생략)")
    return missing


def check_map_domains() -> None:
    print("\n== 2. maps/ 동적 영역 ==")
    maps_dir = os.path.join(cbl.KNOWLEDGE_DIR, "maps")
    try:
        files = sorted(f for f in os.listdir(maps_dir) if f.endswith(".md"))
    except OSError:
        print("  [MISS] maps/ 폴더 없음 — 맵 인사이트에 코칭 지식 미주입")
        return
    print(f"  맵 파일 {len(files)}개: {', '.join(f[:-3] for f in files)}")
    # DB map_name 스타일(대소문자 섞임)로 매칭 테스트
    for probe in files[:2] + ["nonexistent-map"]:
        stem = probe[:-3] if probe.endswith(".md") else probe
        resolved = cbl._resolve_map_file(stem)
        tag = "OK" if resolved else "SKIP"
        print(f"  [{tag}] maps:{stem} → {resolved}")


def check_real_combos() -> None:
    print("\n== 3. 실제 인사이트 도메인 조합 → 주입량 ==")
    # analytics_insights._domains_for_match / _domains_for_player 미러
    combos = {
        "HP 매치+맵 (match/map)": ["principles", "mechanics-core", "mode-hp",
                                   "maps:Firing Range"],
        "SND 매치 (match)": ["principles", "mechanics-core", "mode-snd"],
        "선수 프로필 (player)": ["principles", "mechanics-core", "mechanics-meta",
                                 "mode-hp", "mode-snd"],
        "허브 브리핑 (hub)": ["principles", "team"],
    }
    for name, domains in combos.items():
        text = cbl.get_domains(domains)
        status = f"{len(text):>7,}자" if text else "  0자 ← 주입 없음!"
        print(f"  {name:<28} {status}")


def check_system_prompt() -> None:
    print("\n== 4. build_system_prompt 최종 프롬프트 검증 ==")
    task = "Write 3-4 sentences of key insight from the match stats JSON."
    domains = ["principles", "mechanics-core", "mode-hp", "maps:Firing Range"]
    with_kb = prompt_context.build_system_prompt(task, "ko", domains=domains)
    without_kb = prompt_context.build_system_prompt(task, "ko", domains=[])
    delta = len(with_kb) - len(without_kb)
    print(f"  도메인 미주입 프롬프트: {len(without_kb):,}자")
    print(f"  도메인 주입  프롬프트: {len(with_kb):,}자  (+{delta:,}자)")
    if delta <= 0:
        print("  [FAIL] 코칭 지식이 시스템 프롬프트에 포함되지 않음!")
        return
    kb_text = cbl.get_domains(domains)
    head = " ".join(kb_text.split())[:160]
    print(f"  주입된 코칭 지식 프리뷰: {head}...")
    print("  [OK] 코칭 브레인이 시스템 프롬프트에 반영됨")


def check_fingerprint() -> None:
    print("\n== 5. insight_cache 무효화 지문 ==")
    fp = cbl.fingerprint()
    print(f"  fingerprint: {fp or '(없음 — 볼트 인식 안 됨)'}")
    print("  (이 값이 바뀌면 캐시된 인사이트가 자동 재생성됨)")


def main() -> int:
    print(f"코칭 브레인 루트: {cbl.KNOWLEDGE_DIR}\n")
    missing = check_fixed_domains()
    check_map_domains()
    check_real_combos()
    check_system_prompt()
    check_fingerprint()
    print()
    if missing:
        print(f"결론: 고정 영역 {missing}개 누락 — 해당 영역만 인사이트에 미주입.")
        return 1
    print("결론: 모든 고정 영역 정상 주입.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
