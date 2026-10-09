"""Green Deck: $2 per unused hand, $1 per unused discard, no interest (back.lua sets these on
G.GAME.modifiers). Found transcribing a Balatro University Green Deck run: the first shop opened
with $11 on screen and $7 in the engine."""

from jackdaw.engine.run_init import initialize_run
from jackdaw.engine.economy import calculate_round_earnings


def test_green_deck_modifiers_reach_the_cash_out():
    gs = initialize_run("b_green", 8, "4W4FE8C8")
    mods = gs["modifiers"]
    assert mods.get("money_per_hand") == 2 and mods.get("money_per_discard") == 1 and mods.get("no_interest")


def test_green_deck_round_earnings():
    from jackdaw.schema import SchemaSim
    sim = SchemaSim()
    sim.reset("4W4FE8C8", deck="b_green", stake=8)
    gs = sim.gs
    gs["dollars"] = 30                               # interest would pay at $30
    from types import SimpleNamespace
    e = calculate_round_earnings(blind=SimpleNamespace(dollars=0), hands_left=3, discards_left=1, money=30,
                                 jokers=[], game_state=gs, rng=None, joker_dollars=0)
    assert (e.unused_hands_bonus, e.unused_discards_bonus, e.interest) == (6, 1, 0)
    assert e.total == 7
