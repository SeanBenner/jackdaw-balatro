"""Buy and Use works with full consumable slots: the game skips the space check for that button
(button_callbacks.lua:2407) and uses the card straight from the shop. Found verifying a recorded
run (seed T2Y7BFRN): the simulator refused a Hermit bought and used with both slots taken."""

from jackdaw.engine.actions import GamePhase
from jackdaw.engine.card_factory import create_consumable


def test_buy_and_use_hermit_with_full_slots():
    from jackdaw.schema import SchemaSim
    sim = SchemaSim()
    sim.reset("T2Y7BFRN", deck="b_red", stake=1)
    gs = sim.gs
    gs["phase"] = GamePhase.SHOP
    gs["consumables"] = [create_consumable("c_fool"), create_consumable("c_moon")]
    hermit = create_consumable("c_hermit")
    hermit.cost = 3
    gs["shop_cards"] = [hermit]
    gs["dollars"] = 10
    sim.step({"type": "buy_and_use", "card": hermit.sort_id})
    assert sim.gs["dollars"] == 14                       # 10 - 3, then doubled up to +$20
    assert [c.center_key for c in sim.gs["consumables"]] == ["c_fool", "c_moon"]


def test_plain_buy_still_needs_room():
    import pytest
    from jackdaw.schema import SchemaSim
    from jackdaw.schema.sim import SchemaError
    sim = SchemaSim()
    sim.reset("T2Y7BFRN", deck="b_red", stake=1)
    gs = sim.gs
    gs["phase"] = GamePhase.SHOP
    gs["consumables"] = [create_consumable("c_fool"), create_consumable("c_moon")]
    hermit = create_consumable("c_hermit")
    hermit.cost = 3
    gs["shop_cards"] = [hermit]
    gs["dollars"] = 10
    with pytest.raises(SchemaError):
        sim.step({"type": "buy", "card": hermit.sort_id})
