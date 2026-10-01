"""Real-game scoring regression suite.

Each fixture in ``tests/fixtures/game_scenarios/`` was recorded from Balatro 1.0.1o through
BalatroBot (see the balatro_bot project's ``tools/sim_eval/``): the observable state just before a
play, the cards played in order, and the chips the game scored. The test loads that state into
the engine and checks the score exactly. Per-card debuff flags come from the game (cards created
mid-blind are not debuffed by the boss), so they are loaded as recorded, not recomputed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jackdaw.engine.actions import GamePhase, PlayHand, SelectBlind
from jackdaw.engine.blind import Blind
from jackdaw.engine.card_factory import create_joker, create_playing_card
from jackdaw.engine.data.enums import Rank, Suit
from jackdaw.engine.game import step
from jackdaw.engine.hand_levels import HandLevels
from jackdaw.engine.run_init import initialize_run

FIXTURES = Path(__file__).parent.parent / "fixtures" / "game_scenarios"

SUIT = {"H": Suit.HEARTS, "D": Suit.DIAMONDS, "C": Suit.CLUBS, "S": Suit.SPADES}
RANK = {"2": Rank.TWO, "3": Rank.THREE, "4": Rank.FOUR, "5": Rank.FIVE, "6": Rank.SIX,
        "7": Rank.SEVEN, "8": Rank.EIGHT, "9": Rank.NINE, "T": Rank.TEN, "J": Rank.JACK,
        "Q": Rank.QUEEN, "K": Rank.KING, "A": Rank.ACE}
EDITION = {"e_foil": {"foil": True}, "e_holo": {"holo": True},
           "e_polychrome": {"polychrome": True}, "e_negative": {"negative": True}}
BLIND_KEY = {
    "Small Blind": "bl_small", "Big Blind": "bl_big", "The Hook": "bl_hook", "The Ox": "bl_ox",
    "The House": "bl_house", "The Wall": "bl_wall", "The Wheel": "bl_wheel", "The Arm": "bl_arm",
    "The Club": "bl_club", "The Fish": "bl_fish", "The Psychic": "bl_psychic",
    "The Goad": "bl_goad", "The Water": "bl_water", "The Window": "bl_window",
    "The Manacle": "bl_manacle", "The Eye": "bl_eye", "The Mouth": "bl_mouth",
    "The Plant": "bl_plant", "The Serpent": "bl_serpent", "The Pillar": "bl_pillar",
    "The Needle": "bl_needle", "The Head": "bl_head", "The Tooth": "bl_tooth",
    "The Flint": "bl_flint", "The Mark": "bl_mark", "Amber Acorn": "bl_final_acorn",
    "Verdant Leaf": "bl_final_leaf", "Violet Vessel": "bl_final_vessel",
    "Crimson Heart": "bl_final_heart", "Cerulean Bell": "bl_final_bell",
}


def _card(c):
    s, r = c["key"].split("_")
    card = create_playing_card(SUIT[s], RANK[r], enhancement=c["enhancement"] or "c_base",
                               edition=EDITION.get(c["edition"]), seal=c["seal"])
    card.debuff = c["debuffed"]
    if c.get("played_this_ante"):
        card.ability["played_this_ante"] = True
    if c.get("face_down"):
        card.facing = "back"
    return card


def _load(fx):
    """Build a SELECTING_HAND game_state from a fixture's observable state."""
    o = fx["observable"]
    gs = step(initialize_run(o["run"]["deck"], 1, o["run"]["seed"]), SelectBlind())
    assert gs["phase"] == GamePhase.SELECTING_HAND
    ante = o["run"]["ante"]
    gs["round_resets"]["ante"] = ante
    gs["blind"] = Blind.create(BLIND_KEY[o["current_blind"]["name"]], ante)
    gs["blind"].chips = o["current_blind"]["chips_required"]
    cr = gs["current_round"]
    for k in ("hands_left", "discards_left", "hands_played", "discards_used"):
        cr[k] = o["round"][k]
    gs["chips"] = o["round"]["chips"]
    gs["dollars"] = o["run"]["money"]
    hl = HandLevels()
    for name, v in o["hand_levels"].items():
        st = hl[name]
        st.level, st.chips, st.mult = v["level"], v["chips"], v["mult"]
        st.played, st.played_this_round = v["times_played_run"], v["played_this_round"]
    gs["hand_levels"] = hl
    gs["hand"] = [_card(c) for c in o["hand"]]
    gs["deck"] = [_card(c) for c in o["deck_cards"]]
    gs["discard_pile"] = []
    gs["jokers"] = []
    for j in o["jokers"]:
        jc = create_joker(j["key"], edition=EDITION.get(j["edition"]))
        jc.debuff = j["debuffed"]
        gs["jokers"].append(jc)
    gs["joker_slots"] = o["run"]["joker_slots"]
    return gs


FIXTURE_FILES = sorted(FIXTURES.glob("*.json"))


@pytest.mark.parametrize("path", FIXTURE_FILES, ids=[p.stem for p in FIXTURE_FILES])
def test_game_scenario(path):
    fx = json.loads(path.read_text())
    gs = _load(fx)
    ids = [c["id"] for c in fx["observable"]["hand"]]
    idx = tuple(ids.index(i) for i in fx["action"]["cards"])
    before = gs["chips"]
    gs = step(gs, PlayHand(idx))
    exp = fx["expected"]
    assert gs["chips"] - before == exp["chips_scored"], fx["description"]
    assert gs["last_score_result"].hand_type == exp["hand_type"]


def test_fixture_set_present():
    assert len(FIXTURE_FILES) >= 89
