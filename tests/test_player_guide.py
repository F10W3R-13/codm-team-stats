# player_guide 단위 테스트 (/ask 컨텍스트 선택, /reminder 메시지 길이)
import player_guide as pg


def test_detect_maps():
    assert pg.detect_maps("Takeoff P3 they hold it") == ["takeoff"]
    assert pg.detect_maps("¿Cómo defiendo B en Firing Range?") == ["firing-range"]
    assert pg.detect_maps("what does recycle mean") == []


def test_context_for_one_map_is_focused():
    ctx, maps = pg.build_context("Takeoff P3 break?")
    assert maps == ["takeoff"]
    assert "=== maps/takeoff ===" in ctx and "=== modes/hardpoint ===" in ctx
    assert "=== maps/coastal ===" not in ctx
    assert "=== team-notes ===" not in ctx


def test_context_without_map_has_all_pages_but_not_team_notes():
    ctx, maps = pg.build_context("what does recycle mean?")
    assert maps == []
    assert "=== maps/coastal ===" in ctx and "=== glossary ===" in ctx
    assert "=== team-notes ===" not in ctx


def test_team_notes_only_when_a_player_is_named():
    ctx, _ = pg.build_context("what should Maozyn work on?")
    assert "=== team-notes ===" in ctx


def test_forced_map():
    ctx, maps = pg.build_context("what do we do?", "coastal")
    assert maps == ["coastal"] and "=== maps/coastal ===" in ctx


def test_reminder_fits_discord_and_has_no_unconfirmed():
    for lang in ("en", "es"):
        msgs = pg.build_reminder(lang, "UD", ["combine", "hacienda", "summit", "arsenal"])
        assert len(msgs) >= 2
        for m in msgs:
            assert pg._u16(m) <= pg.LIMIT
            assert "❓" not in m


def test_reminder_custom_fix_replaces_defaults():
    msgs = pg.build_reminder("en", "UD", ["takeoff"], ["Rotate first when behind. `S18 ✅`"])
    assert "Rotate first when behind" in msgs[0] and "rotation**" not in msgs[0]


def test_split_message():
    chunks = pg.split_message("line\n" * 1000)
    assert all(len(c) <= pg.LIMIT for c in chunks) and len(chunks) > 1
