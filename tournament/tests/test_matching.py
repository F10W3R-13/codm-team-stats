from matching import normalize, fuzzy_match


def test_normalize_lowercases_and_strips_clan_tag():
    assert normalize("[CLAN]AcePro") == "acepro"
    assert normalize("Ace_Pro_99") == "acepro"  # 끝 숫자접미사 제거 (식별번호)
    assert normalize("  ACE  ") == "ace"


def test_normalize_strips_special_chars():
    assert normalize("Sniper|BT") == "sniperbt"
    assert normalize("xX_Kingz_Xx") == "xxkingzxx"


def test_normalize_strips_trailing_digits():
    """끝 숫자접미사(플레이어 식별번호) 제거 — Hashirama6974 → hashirama."""
    assert normalize("Hashirama6974") == "hashirama"
    assert normalize("AcePro42") == "acepro"


def test_normalize_keeps_korean():
    """한글 IGN 보존 — 박민재, 한자(理/狸)는 제거."""
    assert normalize("CLRS.박민재") == "clrs박민재"  # 점 접두사는 fuzzy의 _strip_clan_prefix가 처리
    assert normalize("Guri狸") == "guri"  # 한자(너구리 狸)는 제거
    assert normalize("Guri理") == "guri"  # 한자(이치 理)도 제거


def test_fuzzy_match_exact_after_normalize():
    candidates = ["AcePro", "Sniper", "Kingz"]
    assert fuzzy_match("acepro", candidates) == "AcePro"
    assert fuzzy_match("[CLAN]AcePro", candidates) == "AcePro"


def test_fuzzy_match_strips_clan_prefix():
    """클랜태그 접두사 제거 후 매칭 — Fz.slca(OCR오타) → Sica."""
    candidates = ["Sica", "Karpe", "Bang"]
    assert fuzzy_match("Fz.Sica", candidates) == "Sica"
    assert fuzzy_match("Fz.slca", candidates) == "Sica"  # OCR 오타 (l↔i)
    assert fuzzy_match("CLRS.LL", candidates) is None  # LL은 후보에 없음


def test_fuzzy_match_handles_typos():
    candidates = ["AcePro", "Sniper", "Kingz"]
    # 1글자 오타/대소문자는 매칭
    assert fuzzy_match("AcePr0", candidates) == "AcePro"  # o→0


def test_fuzzy_match_returns_none_for_no_match():
    candidates = ["AcePro", "Sniper"]
    assert fuzzy_match("CompletelyDifferent", candidates) is None


def test_fuzzy_match_empty_candidates():
    assert fuzzy_match("Anyone", []) is None
