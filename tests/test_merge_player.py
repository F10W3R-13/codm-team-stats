# merge_player — 병합 시 src 이름이 dst의 alias(source='Merge')로 영구 등록되는지 검증.
# 병합한 닉네임이 재유입되면 새 선수로 다시 생성되지 않고 dst에 자동 귀속되어야 한다.


def test_merge_registers_src_name_as_alias(seeded_db):
    import db

    with db.get_conn() as conn:
        guest_id = conn.execute_returning_id(
            "INSERT INTO players(name) VALUES (?)", ("GuestNick",)
        )
    db.add_alias("GuestAlt", "GuestNick")

    result = db.merge_player(guest_id, "Shisui")
    assert result["ok"] is True

    aliases = {a["ign"]: a for a in db.list_aliases()}
    # 병합 이력 — src 이름 자체가 dst의 별명으로 남는다 (핵심 수정점)
    assert aliases["GuestNick"]["player_name"] == "Shisui"
    assert aliases["GuestNick"]["source"] == "Merge"
    # src가 원래 갖고 있던 alias도 함께 이관
    assert aliases["GuestAlt"]["player_name"] == "Shisui"

    with db.get_conn() as conn:
        # src 선수 행은 삭제됨
        left = conn.execute(
            "SELECT COUNT(*) AS c FROM players WHERE name = ?", ("GuestNick",)
        ).fetchone()["c"]
        assert left == 0
        # 재유입 시 alias 역참조로 Shisui에 귀속 (새 선수 생성 없음)
        shisui_id = conn.execute(
            "SELECT id FROM players WHERE name = 'Shisui'"
        ).fetchone()["id"]
        assert db.resolve_player_id(conn, "GuestNick") == shisui_id


def test_merge_missing_player_fails(seeded_db):
    import db

    result = db.merge_player(999999, "Shisui")
    assert result["ok"] is False
