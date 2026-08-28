# tests/test_opponent_matching.py
import opponent_matching as om


def test_norm_name_strips_and_lowercases():
    assert om.norm_name("  ZeR0!  ") == "zer0"


def test_norm_name_nfkc_fullwidth():
    # 전각 알파벳은 NFKC로 반각화 → 소문자화
    assert om.norm_name("Ｇｏｄ") == "god"


def test_norm_name_removes_non_alnum():
    # ø(U+00F8)는 NFKC 분해 없음 → 비영숫자 제거 대상
    assert om.norm_name("ZeRø") == "zer"
    assert om.norm_name("god_like") == "godlike"


def test_similarity_ocr_noise():
    s = om.similarity("Renegul8808", "RenegulBB08")
    assert s >= 0.8  # B↔8 한 글자 OCR 혼동


def test_similarity_empty_is_zero():
    assert om.similarity("", "abc") == 0.0
    assert om.similarity("!!!", "abc") == 0.0  # 정규화 후 빈 문자열


def test_best_fuzzy_match_threshold():
    cands = [(1, "Renegul8808"), (2, "TotallyDifferent")]
    assert om.best_fuzzy_match("RenegulBB08", cands, 0.75) == (1, om.similarity("RenegulBB08", "Renegul8808"))
    assert om.best_fuzzy_match("RenegulBB08", cands, 0.99) is None


def test_tally_majority_wins():
    # 5명 중 3명 일치 → 과반(0.6) 통과
    assert om.tally_team_votes([1, 1, 1, 2], total=5) == (1, 3)


def test_tally_tie_rejected():
    assert om.tally_team_votes([1, 1, 2, 2], total=5) == (None, 0)


def test_tally_below_ratio_rejected():
    assert om.tally_team_votes([1, 1], total=5) == (None, 0)


def test_tally_empty():
    assert om.tally_team_votes([], total=5) == (None, 0)
