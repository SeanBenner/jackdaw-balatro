"""Decks that start with consumables get them in the consumable area (back.lua apply_to_run)."""

from jackdaw.engine.run_init import initialize_run


def test_ghost_deck_starts_with_hex():
    gs = initialize_run("b_ghost", 8, "5VEE8LQ4")
    assert [c.center_key for c in gs["consumables"]] == ["c_hex"]
    # created after the deck, as in the game's event order
    assert gs["consumables"][0].sort_id > max(c.sort_id for c in gs["deck"])


def test_magic_deck_starts_with_two_fools():
    gs = initialize_run("b_magic", 1, "MAGIC1")
    assert [c.center_key for c in gs["consumables"]] == ["c_fool", "c_fool"]


def test_other_decks_start_empty():
    assert initialize_run("b_blue", 1, "BLUE1")["consumables"] == []
