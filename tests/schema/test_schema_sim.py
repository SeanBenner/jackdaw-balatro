"""Tests for the schema v0.4 interface (jackdaw.schema.SchemaSim)."""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from jackdaw.schema import SchemaError, SchemaSim

FIXTURES = sorted((Path(__file__).parent.parent / "fixtures" / "game_scenarios").glob("*.json"))
BLIND_KEY = {
    "Small Blind": "bl_small",
    "Big Blind": "bl_big",
    "The Club": "bl_club",
    "The Goad": "bl_goad",
    "The Window": "bl_window",
    "The Head": "bl_head",
    "The Plant": "bl_plant",
    "The Flint": "bl_flint",
    "The Psychic": "bl_psychic",
    "The Pillar": "bl_pillar",
    "The Hook": "bl_hook",
    "The Manacle": "bl_manacle",
    "The Eye": "bl_eye",
    "The Mouth": "bl_mouth",
}


def fixture_to_snapshot(fx: dict) -> dict:
    """Real-game fixture (recorder format) -> schema snapshot at SELECTING_HAND."""
    o = fx["observable"]
    cb = o["current_blind"]
    btype = "small" if cb["type"] == "small" else "big" if cb["type"] == "big" else "boss"

    def ent(c, loc, pos):
        return {
            **c,
            "set": "Enhanced" if c["enhancement"] else "Default",
            "location": loc,
            "position": pos,
            "cost": {"buy": None, "sell": None},
            "ability": None,
        }

    hand = [ent(c, "hand", i) for i, c in enumerate(o["hand"])]
    deck = hand + [ent(c, "draw_pile", None) for c in o["deck_cards"]]
    jokers = [
        {
            "id": j["id"],
            "key": j["key"],
            "set": "Joker",
            "edition": j["edition"],
            "debuffed": j["debuffed"],
            "stickers": {},
            "cost": {},
            "location": "jokers",
            "position": i,
        }
        for i, j in enumerate(o["jokers"])
    ]
    return {
        "schema_version": "0.4",
        "phase": "SELECTING_HAND",
        "observable": {
            "run": {
                "seed": o["run"]["seed"],
                "deck": o["run"]["deck"],
                "stake": 1,
                "ante": o["run"]["ante"],
                "round_num": o["run"]["round_num"],
                "money": o["run"]["money"],
                "hand_size": o["run"]["hand_size"],
                "joker_slots": o["run"]["joker_slots"],
                "consumable_slots": o["run"]["consumable_slots"],
            },
            "round": {
                k: o["round"][k]
                for k in ("hands_left", "discards_left", "hands_played", "discards_used")
            }
            | {"chips_scored": o["round"]["chips"]},
            "blinds": [
                {
                    "type": btype,
                    "key": BLIND_KEY[cb["name"]],
                    "chips_required": cb["chips_required"],
                    "status": "current",
                }
            ],
            "hand_levels": o["hand_levels"],
            "hand": hand,
            "jokers": jokers,
            "consumables": [],
            "deck": deck,
        },
        "hidden": None,
    }


def _loaded(fx) -> SchemaSim:
    sim = SchemaSim()
    sim.load(fixture_to_snapshot(fx))
    return sim


@pytest.fixture(scope="module")
def fixtures():
    return [json.loads(p.read_text()) for p in FIXTURES]


# --------------------------------------------------------------------------- load + exact scoring


@pytest.mark.parametrize("path", FIXTURES, ids=[p.stem for p in FIXTURES])
def test_load_and_score_recorded_arrangement(path):
    fx = json.loads(path.read_text())
    sim = _loaded(fx)
    played = fx["action"]["cards"]
    held = [c["id"] for c in fx["observable"]["hand"] if c["id"] not in played]
    jokers = [j["id"] for j in fx["observable"]["jokers"]]
    r = sim.score_arrangement(played, held, jokers)
    assert r["total"] == fx["expected"]["chips_scored"]
    assert r["hand_type"] == fx["expected"]["hand_type"]


@pytest.mark.parametrize("path", FIXTURES, ids=[p.stem for p in FIXTURES])
def test_preview_brackets_recorded_score_and_is_pure(path):
    fx = json.loads(path.read_text())
    sim = _loaded(fx)
    before = json.dumps(sim.snapshot()["observable"], sort_keys=True)
    hi = sim.preview(fx["action"]["cards"], "max")
    lo = sim.preview(fx["action"]["cards"], "min")
    assert json.dumps(sim.snapshot()["observable"], sort_keys=True) == before
    game = fx["expected"]["chips_scored"]
    assert lo["expected"] <= game <= hi["expected"]


def test_coordinate_descent_matches_exhaustive(fixtures):
    from jackdaw.schema import scoring

    worse = []
    for fx in fixtures:
        sim = _loaded(fx)
        played, held = sim._split(fx["action"]["cards"])
        jokers = list(sim.gs["jokers"])
        for obj in ("max", "min"):
            ex = scoring.arrange(sim.gs, played, held, jokers, obj, exhaustive=True)
            cd = scoring.arrange(sim.gs, played, held, jokers, obj, exhaustive=False)
            if ex["score"]["expected"] != cd["score"]["expected"]:
                worse.append((fx["id"], obj, ex["score"]["expected"], cd["score"]["expected"]))
    assert not worse


def test_play_uses_best_arrangement_and_restores_joker_order(fixtures):
    fx = next(f for f in fixtures if f["id"] == "order_x_then_plus")  # Cavendish then Joker
    sim = _loaded(fx)
    standing = [j.sort_id for j in sim.gs["jokers"]]
    best = sim.preview(fx["action"]["cards"])["total"]
    assert best > fx["expected"]["chips_scored"]  # +mult before xmult beats the recorded order
    _, events = sim.step({"type": "play", "cards": fx["action"]["cards"], "objective": "max"})
    score = next(e for e in events if e["type"] == "score")
    assert score["total"] == best
    assert [j.sort_id for j in sim.gs["jokers"]] == standing


# --------------------------------------------------------------------------- runs through the masks


def _sample(masks, rng):
    types = masks["types"]
    t = rng.choice(sorted(types))
    m = types[t]
    if t in ("play", "discard"):
        cards = list(m["must_include"])
        k = max(rng.randint(m["min"], m["max"]), len(cards))
        cards += rng.sample([c for c in m["cards"] if c not in cards], k - len(cards))
        a = {"type": t, "cards": cards}
        if t == "play":
            a["objective"] = rng.choice(m["objective"])
        return a
    if t == "rearrange_jokers":
        order = list(m["order"])
        rng.shuffle(order)
        return {"type": t, "order": order}
    if t in ("use_consumable", "pack_pick"):
        c = rng.choice(m["card"])
        tg = m["targets"][c]
        a = {"type": t, "card": c}
        if tg["max"]:
            a["targets"] = rng.sample(
                tg["cards"], rng.randint(tg["min"], min(tg["max"], len(tg["cards"])))
            )
        return a
    if t in ("buy", "sell"):
        return {"type": t, "card": rng.choice(m["card"])}
    return {"type": t}


def test_random_runs_only_take_legal_actions():
    """Every action sampled from legal_actions() must be accepted by step()."""
    rejected, steps = [], 0
    for k in range(12):
        rng = random.Random(k)
        sim = SchemaSim()
        sim.reset(f"MASK{k}", "b_blue", 1)
        for _ in range(400):
            if sim.phase() == "GAME_OVER":
                break
            masks = sim.legal_actions()
            if not masks["types"]:
                break
            a = _sample(masks, rng)
            if a["type"] == "play":
                a["objective"] = "max"
                sim.gs["chips"] = sim.gs.get("chips", 0) + 10**4  # reach shops and packs
            try:
                sim.step(a)
                steps += 1
            except SchemaError as e:
                rejected.append((k, a["type"], str(e)[:80]))
    assert steps > 300
    assert not rejected, rejected[:5]


def test_snapshot_roundtrip_and_clone():
    sim = SchemaSim()
    sim.reset("ROUND", "b_blue", 1)
    sim.step({"type": "select_blind"})
    snap = sim.snapshot(include_engine_state=True)
    other = SchemaSim()
    other.load(snap)
    assert other.snapshot()["observable"] == sim.snapshot()["observable"]
    c = sim.clone()
    ids = [x["id"] for x in sim.snapshot()["observable"]["hand"]][:2]
    c.step({"type": "play", "cards": ids})
    assert sim.snapshot()["observable"]["round"]["hands_played"] == 0


def test_observable_only_load_keeps_observable_state():
    sim = SchemaSim()
    sim.reset("OBS", "b_blue", 1)
    sim.step({"type": "select_blind"})
    snap = sim.snapshot()
    other = SchemaSim()
    other.load({**snap, "hidden": None})
    a, b = snap["observable"], other.snapshot()["observable"]
    for k in ("hand", "jokers", "hand_levels", "round", "blinds"):
        assert a[k] == b[k], k
    assert sorted(e["id"] for e in a["deck"]) == sorted(e["id"] for e in b["deck"])


def test_ids_unique_across_interleaved_sims():
    a, b = SchemaSim(), SchemaSim()
    a.reset("IDA", "b_blue", 1)
    b.reset("IDB", "b_blue", 1)  # resets jackdaw's global id counter; a must not be affected

    def win_blind(s):
        s.step({"type": "select_blind"})
        s.gs["chips"] = 10**6
        s.step({"type": "play", "cards": [s.gs["hand"][0].sort_id]})
        s.step({"type": "cash_out"})

    win_blind(a)
    win_blind(b)
    a.step({"type": "next_round"})
    win_blind(a)
    for s in (a, b):
        o = s.snapshot()["observable"]
        ids = [e["id"] for e in o["deck"] + o["jokers"] + o["shop"]["items"] + o["shop"]["packs"]]
        assert len(ids) == len(set(ids))


def test_preview_is_pure_under_the_hook():
    """The Hook discards at random during scoring; preview must not touch the real piles."""
    sim = SchemaSim()
    sim.reset("HOOK", "b_blue", 1)
    sim.step({"type": "select_blind"})
    from jackdaw.engine.blind import Blind

    sim.gs["blind"] = Blind.create("bl_hook", 1)
    before = json.dumps(sim.snapshot()["observable"], sort_keys=True)
    p = sim.preview([c.sort_id for c in sim.gs["hand"][:3]])
    assert json.dumps(sim.snapshot()["observable"], sort_keys=True) == before
    assert p["deterministic"] is False


def test_upcoming_requirements_blue_white():
    snap = SchemaSim().reset("REQ", "b_blue", 1)
    req = snap["observable"]["upcoming_requirements"]
    assert [r["chips_required"] for r in req[:3]] == [300, 450, 600]
    assert req[-1] == {"ante": 8, "type": "boss", "chips_required": 100000}
    assert len(req) == 24


def test_score_distribution():
    sim = SchemaSim()
    sim.reset("DIST", "b_blue", 1)

    def first_five(s):  # test-only policy: play the first five cards in hand
        return {"type": "play", "cards": [c.sort_id for c in s.gs["hand"][:5]]}

    d = sim.score_distribution(8, first_five)
    assert d["n"] == 8 and 0 <= d["beat_fraction"] <= 1
    assert d["round_total"]["p10"] <= d["round_total"]["p90"]
    assert sim.phase() == "BLIND_SELECT"  # the real sim is untouched


BOSSES = [
    "bl_tooth",
    "bl_flint",
    "bl_plant",
    "bl_club",
    "bl_goad",
    "bl_head",
    "bl_window",
    "bl_psychic",
    "bl_ox",
    "bl_arm",
    "bl_eye",
    "bl_mouth",
    "bl_wall",
    "bl_needle",
    "bl_pillar",
    "bl_manacle",
    "bl_water",
    "bl_serpent",
    "bl_small",
]
STATE_JOKERS = [
    ["j_bull", "j_greedy_joker", "j_egg", "j_swashbuckler", "j_droll"],
    ["j_bootstraps", "j_blue_joker", "j_erosion", "j_acrobat", "j_joker"],
    ["j_supernova", "j_card_sharp", "j_ride_the_bus", "j_runner", "j_square"],
    ["j_abstract", "j_stencil", "j_banner", "j_mystic_summit", "j_green_joker"],
]


@pytest.mark.parametrize("boss", BOSSES)
@pytest.mark.parametrize("jset", range(len(STATE_JOKERS)))
def test_prediction_equals_engine_play(boss, jset):
    """The arrangement's predicted score must be what the engine then scores (bug: The Tooth's
    money loss happened after Bull read money in the preview)."""
    from jackdaw.engine.blind import Blind
    from jackdaw.engine.card_factory import create_joker

    sim = SchemaSim()
    sim.reset(f"PRED{jset}", "b_blue", 1)
    sim.step({"type": "select_blind"})
    sim.gs["blind"] = Blind.create(boss, 1)
    sim.gs["dollars"] = 23
    sim.gs["jokers"] = [create_joker(k) for k in STATE_JOKERS[jset]]
    sim._exit()
    for n in (5, 3, 1):
        if sim.phase() != "SELECTING_HAND":
            break
        cards = [c.sort_id for c in sim.gs["hand"][:n]]
        _, events = sim.step({"type": "play", "cards": cards})
        score = next(e for e in events if e["type"] == "score")
        assert score["predicted"] == score["total"], (boss, STATE_JOKERS[jset], n)
