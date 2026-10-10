"""A playing card taken from a Standard pack goes to the bottom of the deck: CardArea:emplace inserts
deck cards at index 1 (cardarea.lua:33) and draws take the top (the list's end). Found verifying a
recorded Red Deck run (seed 8BKHH355): the simulator drew the picked card first into the next Arcana
pack's hand."""

from jackdaw.engine import game
from jackdaw.engine.card import Card
from jackdaw.engine.actions import GamePhase


def test_standard_pack_pick_lands_at_the_bottom():
    from jackdaw.schema import SchemaSim
    sim = SchemaSim()
    sim.reset("8BKHH355", deck="b_red", stake=1)
    gs = sim.gs
    top_before = gs["deck"][-1]
    c = Card()
    c.set_base("D_8", "Diamonds", "8")
    c.set_ability("c_base")
    gs["pack_cards"] = [c]
    gs["pack_choices_remaining"] = 1
    gs["phase"] = GamePhase.PACK_OPENING
    game._handle_pick_pack_card(gs, 0)
    assert gs["deck"][0] is c
    assert gs["deck"][-1] is top_before
