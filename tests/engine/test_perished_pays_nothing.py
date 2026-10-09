"""A perishable joker that expires at the end of a round pays no dollar bonus that round."""

from jackdaw.engine.card_factory import create_joker
from jackdaw.engine.run_init import initialize_run
from jackdaw.engine.game import _joker_end_of_round_effects


def test_cloud9_expiring_this_round_pays_nothing():
    gs = initialize_run("b_blue", 1, "PERISH1")
    j = create_joker("j_cloud_9")
    j.set_perishable(True)
    gs["jokers"] = [j]
    j.perish_tally = 1
    j.ability["perish_tally"] = 1
    eor = _joker_end_of_round_effects(gs)
    assert j.debuff
    assert eor["dollars_earned"] == 0


def test_cloud9_unexpired_pays():
    gs = initialize_run("b_blue", 1, "PERISH1")
    j = create_joker("j_cloud_9")
    gs["jokers"] = [j]
    assert _joker_end_of_round_effects(gs)["dollars_earned"] > 0
