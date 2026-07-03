# 국제화(i18n) — 한국어 / 영어 / 스페인어
#
# 웹과 디스코드 명령어가 공통으로 쓰는 UI 문자열 사전.
# 사용: t = i18n.translations["en"]; t["nav_dashboard"]
#       또는 i18n.tr("en", "nav_dashboard")
#
# 언어 코드: ko(한국어-코치용), en(영어-선수용), es(스페인어-선수용)
# 기본값: ko
#
# 구조 (패키지):
#   i18n/_ko.py, _en.py, _es.py — 각 언어의 STRINGS dict.
#   키 추가/수정 시 해당 언어 파일만 편집. test_i18n.py가 누락 키 검증.

LANGUAGES = ["ko", "en", "es"]
DEFAULT_LANG = "ko"

from ._ko import STRINGS as _ko
from ._en import STRINGS as _en
from ._es import STRINGS as _es

translations = {
    "ko": _ko,
    "en": _en,
    "es": _es,
}


def get(lang: str) -> dict:
    """해당 언어의 문자열 사전 반환. 없으면 기본값(ko)."""
    if lang not in translations:
        lang = DEFAULT_LANG
    return translations[lang]


def tr(lang: str, key: str, **kwargs) -> str:
    """단일 문자열 번역. kwargs 있으면 .format() 적용."""
    d = get(lang)
    s = d.get(key, translations[DEFAULT_LANG].get(key, key))
    if kwargs:
        try:
            s = s.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return s


def lang_name(lang: str, target_lang: str = "en") -> str:
    """언어 코드의 표시명 (언어 선택기용)."""
    names = {
        "ko": {"ko": "한국어", "en": "Korean", "es": "Coreano"},
        "en": {"ko": "영어", "en": "English", "es": "Inglés"},
        "es": {"ko": "스페인어", "en": "Spanish", "es": "Español"},
    }
    return names.get(lang, {}).get(target_lang, lang)
