"""The Fool is usable from the consumable tray once a tarot or planet other than The Fool has been used
(vanilla card.lua: G.GAME.last_tarot_planet). The legal-action list, the action mask and the observation
used to call can_use_consumable without the game state, so it never saw last_tarot_planet and never
offered The Fool. Found transcribing a Balatro University Magic Deck run (Fool used in a Mega Arcana
pack right after The Hanged Man was taken from it)."""

from jackdaw.engine.actions import GamePhase, UseConsumable, get_legal_actions
from jackdaw.engine.card_factory import create_consumable
from jackdaw.engine.game import step
from jackdaw.engine.run_init import initialize_run


def _gs(last):
    gs = initialize_run("b_blue", 1, "FOOLUSE1")
    gs["consumables"] = [create_consumable("c_fool")]
    gs["phase"] = GamePhase.SHOP
    gs["last_tarot_planet"] = last
    return gs


def test_fool_offered_after_a_tarot():
    assert any(isinstance(a, UseConsumable) for a in get_legal_actions(_gs("c_hanged_man")))


def test_fool_not_offered_without_a_prior_tarot_or_after_fool():
    assert not any(isinstance(a, UseConsumable) for a in get_legal_actions(_gs(None)))
    assert not any(isinstance(a, UseConsumable) for a in get_legal_actions(_gs("c_fool")))


def test_fool_makes_the_copy():
    gs = _gs("c_hanged_man")
    step(gs, UseConsumable(card_index=0))
    assert [c.center_key for c in gs["consumables"]] == ["c_hanged_man"]


def test_fool_usable_in_pack_after_pack_tarot():
    gs = _gs("c_hanged_man")
    gs["phase"] = GamePhase.PACK_OPENING
    gs["pack_cards"], gs["pack_choices_remaining"] = [create_consumable("c_world")], 1
    assert any(isinstance(a, UseConsumable) for a in get_legal_actions(gs))


def test_observation_sees_the_fool():
    # (the action mask's copy of this check is fixed on the joker-moves branch)
    from jackdaw.env import observation
    gs = _gs("c_hanged_man")
    assert observation.encode_consumable(gs["consumables"][0], gs)[3] == 1.0
