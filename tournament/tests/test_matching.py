from matching import normalize, fuzzy_match


def test_normalize_lowercases_and_strips_clan_tag():
    assert normalize("[CLAN]AcePro") == "acepro"
    assert normalize("Ace_Pro_99") == "acepro99"
    assert normalize("  ACE  ") == "ace"


def test_normalize_strips_special_chars():
    assert normalize("Sniper|BT") == "sniperbt"
    assert normalize("xX_Kingz_Xx") == "xxkingzxx"


def test_fuzzy_match_exact_after_normalize():
    candidates = ["AcePro", "Sniper99", "Kingz"]
    assert fuzzy_match("acepro", candidates) == "AcePro"
    assert fuzzy_match("[CLAN]AcePro", candidates) == "AcePro"


def test_fuzzy_match_handles_typos():
    candidates = ["AcePro", "Sniper99", "Kingz"]
    # 1글자 오타/대소문자는 매칭
    assert fuzzy_match("AcePr0", candidates) == "AcePro"  # o→0


def test_fuzzy_match_returns_none_for_no_match():
    candidates = ["AcePro", "Sniper99"]
    assert fuzzy_match("CompletelyDifferent", candidates) is None


def test_fuzzy_match_empty_candidates():
    assert fuzzy_match("Anyone", []) is None
