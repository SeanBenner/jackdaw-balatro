"""Selling isn't shop-only (Card:can_sell_card has no state gate), and spectral packs can be picked from."""

from jackdaw.engine.actions import GamePhase, SellCard, get_legal_actions
from jackdaw.engine.card_factory import create_joker
from jackdaw.engine.run_init import initialize_run


def _gs(phase):
    gs = initialize_run("b_blue", 1, "SELL1")
    gs["jokers"] = [create_joker("j_joker")]
    gs["phase"] = phase
    return gs


def test_sell_offered_outside_the_shop():
    for phase in (GamePhase.BLIND_SELECT, GamePhase.PACK_OPENING, GamePhase.SHOP):
        gs = _gs(phase)
        if phase == GamePhase.PACK_OPENING:
            gs["pack_cards"], gs["pack_choices_remaining"] = [], 0
        assert any(isinstance(a, SellCard) for a in get_legal_actions(gs)), phase


def test_eternal_jokers_not_offered():
    gs = _gs(GamePhase.BLIND_SELECT)
    gs["jokers"][0].eternal = True
    assert not any(isinstance(a, SellCard) for a in get_legal_actions(gs))
