"""Tarots that need targets (Hanged Man, Devil, Strength...) can be used from the consumable tray.
SchemaSim.legal_actions used to list only what the engine's list allowed, and that list checks each
consumable with nothing selected, so targeted tarots were never offered. Found transcribing a Balatro
University Magic Deck run (a Fool's copy of The Hanged Man used on two Aces inside a Mega Arcana pack)."""

from jackdaw.engine.actions import GamePhase
from jackdaw.engine.card_factory import create_consumable
from jackdaw.schema import SchemaSim


def _sim_in_hand(key):
    sim = SchemaSim()
    sim.reset("TRAYUSE1", deck="b_red", stake=1)
    sim.step({"type": "select_blind"})
    assert sim.phase() == "SELECTING_HAND"
    sim.gs["consumables"] = [create_consumable(key)]
    return sim


def test_hanged_man_offered_mid_hand_and_destroys_targets():
    sim = _sim_in_hand("c_hanged_man")
    la = sim.legal_actions()["types"]["use_consumable"]
    cid = la["card"][0]
    assert la["targets"][cid]["max"] == 2
    two = la["targets"][cid]["cards"][:2]
    n = len(sim.gs["hand"])
    sim.step({"type": "use_consumable", "card": cid, "targets": two})
    assert sim.gs["consumables"] == []
    assert not {c.sort_id for c in sim.gs["hand"]} & set(two)
    assert len(sim.gs["hand"]) == n - 2


def test_devil_offered_mid_hand():
    sim = _sim_in_hand("c_devil")
    assert "use_consumable" in sim.legal_actions()["types"]


def test_hanged_man_offered_in_pack():
    sim = _sim_in_hand("c_hanged_man")
    sim.gs["phase"] = GamePhase.PACK_OPENING
    sim.gs["pack_cards"], sim.gs["pack_choices_remaining"] = [create_consumable("c_world")], 1
    la = sim.legal_actions()["types"]
    assert "use_consumable" in la
    cid = la["use_consumable"]["card"][0]
    sim.step({"type": "use_consumable", "card": cid, "targets": la["use_consumable"]["targets"][cid]["cards"][:1]})
    assert sim.phase() == "PACK_OPENED"


def test_not_offered_with_an_empty_hand():
    sim = SchemaSim()
    sim.reset("TRAYUSE1", deck="b_red", stake=1)
    sim.gs["consumables"] = [create_consumable("c_hanged_man")]
    assert "use_consumable" not in sim.legal_actions()["types"]
