# i18n 누락 키 검증 테스트
#
# 실행: pytest test_i18n.py
#
# 목적: ko/en/es 세 언어의 키 셋이 동일한지 검증.
# 키 추가 시 한 언어 파일에서만 추가하고 다른 언어를 잊으면
# "영어에선 키 이름이 그대로 노출"되는 사고를 이 테스트가 잡는다.

import i18n


def test_all_languages_have_same_keys():
    """ko/en/es 가 동일한 키 셋을 가져야 한다. 누락 시 어느 언어에 어떤 키가 빠졌는지 출력."""
    langs = i18n.LANGUAGES
    keysets = {lang: set(i18n.translations[lang].keys()) for lang in langs}

    errors = []
    # 기준: 첫 언어(ko). 다른 모든 언어와 비교.
    base = i18n.DEFAULT_LANG
    base_keys = keysets[base]
    for lang in langs:
        if lang == base:
            continue
        missing = base_keys - keysets[lang]
        extra = keysets[lang] - base_keys
        if missing:
            errors.append(f"[{lang}] 누락 키 ({base}엔 있음): {sorted(missing)}")
        if extra:
            errors.append(f"[{lang}] 여분 키 ({base}엔 없음): {sorted(extra)}")

    assert not errors, "언어별 키 불일치:\n" + "\n".join(errors)


def test_no_empty_values():
    """번역 값이 빈 문자열('')이면 안 됨 — 번역 누락 자리 표시이므로."""
    empties = {}
    for lang in i18n.LANGUAGES:
        empty_keys = [k for k, v in i18n.translations[lang].items() if v == ""]
        if empty_keys:
            empties[lang] = empty_keys
    assert not empties, f"빈 번역값:\n{empties}"


def test_tr_fallback_to_key_name():
    """존재하지 않는 키 → 키 이름 자체 반환 (사용자에게 raw 키가 노출되더라도 crash는 없게)."""
    result = i18n.tr("en", "this_key_does_not_exist_xyz")
    assert result == "this_key_does_not_exist_xyz"


def test_tr_format_kwargs():
    """kwargs 포맷 치환이 동작해야 함 ({name} 등)."""
    result = i18n.tr("en", "confirm_delete_player", name="TestPlayer")
    assert "TestPlayer" in result
    assert "{name}" not in result


def test_invalid_lang_falls_back_to_default():
    """지원하지 않는 언어 코드 → 기본 언어(ko) 사전 반환."""
    d = i18n.get("fr")
    assert d is i18n.translations[i18n.DEFAULT_LANG]
