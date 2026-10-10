"""A Rental joker that goes extinct at round end still pays its $3: vanilla removes Gros Michel by a
queued event, so it's still in the end_round loop when calculate_rental runs (state_events.lua:99-110).
Found verifying a recorded Gold Stake run (seed T2Y7BFRN): game $45, simulator $48."""

from jackdaw.engine.card_factory import create_joker
from jackdaw.engine.round_lifecycle import process_round_end_cards


def test_rental_charged_for_every_joker_in_the_loop():
    gs = {"dollars": 20, "rental_rate": 3}
    banana = create_joker("j_gros_michel", rental=True)
    other = create_joker("j_joker")
    res = process_round_end_cards([banana, other], gs)
    assert gs["dollars"] == 17 and res.rental_cost == 3


def test_round_won_charges_the_extinct_rental(monkeypatch):
    from jackdaw.engine import game, jokers as J
    from jackdaw.schema import SchemaSim
    sim = SchemaSim()
    sim.reset("T2Y7BFRN", deck="b_red", stake=8)
    gs = sim.gs
    banana = create_joker("j_gros_michel", rental=True)
    gs["jokers"] = [banana]
    real = J.on_end_of_round

    def extinct(jokers, *a, **k):
        out = real(jokers, *a, **k)
        out.setdefault("jokers_removed", []).append(banana)
        return out
    monkeypatch.setattr(J, "on_end_of_round", extinct)
    before = gs["dollars"] = 20
    game._joker_end_of_round_effects(gs)
    assert banana not in gs["jokers"]
    assert gs["dollars"] == before - 3
