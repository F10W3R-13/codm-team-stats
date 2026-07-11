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
