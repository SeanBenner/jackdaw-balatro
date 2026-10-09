"""Consumables can be used while a pack is open (vanilla allows it): Hex used mid-pack, before a joker is
taken, can only hit the jokers already held. Found transcribing a Balatro University Ghost Deck run."""

from jackdaw.engine.actions import GamePhase, UseConsumable, get_legal_actions
from jackdaw.engine.card_factory import create_consumable, create_joker
from jackdaw.engine.game import step
from jackdaw.engine.run_init import initialize_run


def _pack_gs():
    gs = initialize_run("b_blue", 1, "PACKUSE1")
    gs["jokers"] = [create_joker("j_gift")]
    gs["consumables"] = [create_consumable("c_hex")]
    gs["phase"] = GamePhase.PACK_OPENING
    gs["pack_cards"], gs["pack_choices_remaining"] = [create_joker("j_walkie_talkie")], 1
    return gs


def test_use_offered_with_a_pack_open():
    assert any(isinstance(a, UseConsumable) for a in get_legal_actions(_pack_gs()))


def test_hex_mid_pack_hits_the_held_joker():
    gs = _pack_gs()
    step(gs, UseConsumable(card_index=0))
    assert gs["phase"] == GamePhase.PACK_OPENING
    assert [j.center_key for j in gs["jokers"]] == ["j_gift"]
    assert (gs["jokers"][0].edition or {}).get("polychrome") or (gs["jokers"][0].edition or {}).get("type") == "polychrome"
    assert gs["consumables"] == []


def test_schema_offers_use_in_pack():
    from jackdaw.schema import SchemaSim
    sim = SchemaSim()
    sim.reset("PACKUSE1", deck="b_ghost", stake=1)       # Ghost Deck starts with Hex
    gs = sim.gs
    gs["jokers"] = [create_joker("j_gift")]
    gs["phase"] = GamePhase.PACK_OPENING
    gs["pack_cards"], gs["pack_choices_remaining"] = [create_joker("j_walkie_talkie")], 1
    la = sim.legal_actions()["types"]
    assert "use_consumable" in la
    sim.step({"type": "use_consumable", "card": la["use_consumable"]["card"][0]})
    assert sim.phase() == "PACK_OPENED"
