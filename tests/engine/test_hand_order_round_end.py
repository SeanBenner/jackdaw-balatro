"""Hand order is what the game shows, and the discard pile and round-end return follow it.

A Blue Seal planet or a Hook discard must not reshuffle the hand's order: the round-end return to
the deck reads it, and identical-rank cards (a lucky and a plain King of Spades) swap otherwise.
Found verifying recorded runs 1T9NTMKH (decision 127) and T2Y7BFRN (decision 250).
"""

import pytest

from jackdaw.engine.actions import PlayHand, SelectBlind
from jackdaw.engine.game import _resolve_create_descriptors, step
from jackdaw.engine.run_init import initialize_run


def test_planet_creation_leaves_hand_order():
    gs = initialize_run("b_red", 1, "PLANET_ORDER")
    step(gs, SelectBlind())
    gs["hand"] = sorted(gs["hand"], key=lambda c: c.get_nominal())
    before = [id(c) for c in gs["hand"]]

    _resolve_create_descriptors(gs, [{"type": "Planet", "forced_key": "c_pluto", "seed": "blusl"}])

    assert [c.center_key for c in gs["consumables"]] == ["c_pluto"]
    assert [id(c) for c in gs["hand"]] == before


@pytest.mark.parametrize("seed", ["HOOK_ORDER_A", "HOOK_ORDER_B", "HOOK_ORDER_C", "HOOK_ORDER_D"])
def test_hook_discards_in_hand_order(seed):
    gs = initialize_run("b_red", 1, seed)
    step(gs, SelectBlind())
    gs["blind"].name = "The Hook"
    gs["blind"].boss = True
    gs["blind"].chips = 10**9
    before = list(gs["hand"])
    played = before[0]

    step(gs, PlayHand(card_indices=(0,)))

    hooked = [c for c in gs["discard_pile"] if c is not played]
    assert len(hooked) == 2
    positions = [next(i for i, h in enumerate(before) if h is c) for c in hooked]
    assert positions == sorted(positions)
