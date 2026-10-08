"""Editions added by consumables (Hex, Wheel of Fortune, Aura, Ectoplasm) carry their scoring values."""

from jackdaw.engine.card import Card


def test_set_edition_fills_scoring_values():
    c = Card()
    c.set_edition({"polychrome": True})
    assert c.edition["x_mult"] == 1.5
    assert c.get_edition()["x_mult_mod"] == 1.5


def test_hex_polychrome_scores():
    # replays the opening of Balatro University's 5VEE8LQ4 run: buy Acrobat, Hex it, then the
    # boss flush must score 65 x 6 = 390 as in the video (it scored 65 x 4 before the fix)
    from jackdaw.schema import SchemaSim

    s = SchemaSim()
    s.reset("5VEE8LQ4", deck="b_ghost", stake=8)
    s.step({"type": "select_blind"})
    s.step({"type": "play", "cards": [c.sort_id for c in s.gs["hand"]
                                      if (c.base.id, c.base.suit.value[0]) in {(9, "S"), (9, "H"), (9, "C"), (7, "H"), (7, "D")}]})
    s.step({"type": "cash_out"})
    acro = next(c for c in s.gs["shop_cards"] if c.center_key == "j_acrobat")
    s.step({"type": "buy", "card": acro.sort_id})
    s.step({"type": "use_consumable", "card": s.gs["consumables"][0].sort_id})
    j = s.gs["jokers"][0]
    assert j.center_key == "j_acrobat" and j.edition.get("x_mult") == 1.5
