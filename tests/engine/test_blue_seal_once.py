"""A Blue Seal held at round end makes ONE planet. Creating the planet re-sorts the hand, and the loop
walked the live list: a Blue Seal card moved further along was met again and made a second planet.
Found verifying a recorded Gold Stake run (seed 1T9NTMKH): game 1 Pluto, simulator 2."""

from jackdaw.schema import SchemaSim


def test_one_planet_per_blue_seal():
    sim = SchemaSim()
    sim.reset("1T9NTMKH", deck="b_checkered", stake=1)
    sim.step({"type": "select_blind"})
    gs = sim.gs
    gs["blind"].chips = 1
    hand = sorted(gs["hand"], key=lambda c: -c.base.id)
    low = hand[-1]
    low.set_seal("Blue")
    # the lowest card held early: a rank sort moves it to the end, past where the loop has been
    gs["hand"] = [hand[0], low] + hand[1:-1]
    gs["consumables"] = []
    sim.step({"type": "play", "cards": [hand[0].sort_id], "objective": "as_is"})
    assert [c.center_key for c in sim.gs["consumables"]] == ["c_pluto"]
