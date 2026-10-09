"""Card:set_eternal / set_perishable respect the joker's compat flags and exclude each other."""

from jackdaw.engine.card_factory import create_joker


def test_eternal_incompatible_jokers_stay_sellable():
    for key in ("j_turtle_bean", "j_gros_michel", "j_ice_cream", "j_ramen"):
        j = create_joker(key)
        j.set_eternal(True)
        assert not j.eternal, key


def test_eternal_and_perishable_exclusive():
    j = create_joker("j_8_ball")
    j.set_eternal(True)
    j.set_perishable(True)
    assert j.eternal and not j.perishable
