"""Rebuild an engine game_state from a schema snapshot's ``observable`` part (schema §6 ``load``).

Used for states the simulator didn't produce itself: real-game recordings, constructed test states,
expert positions. The run is initialised with the same deck/stake/seed and then every observable
field is written over it. What the observable state can't supply:

* draw-pile order: ``hidden.draw_order`` if present, otherwise a seeded shuffle;
* RNG state: ``hidden.rng_state`` if present, otherwise a fresh stream from the run seed;
* voucher side effects that aren't visible as run numbers (e.g. shop discounts) are not re-applied:
  owned vouchers are marked as redeemed, and the visible run numbers (hand size, slots, ...)
  are set.
"""

from __future__ import annotations

import base64
import pickle
import random
from typing import Any

from jackdaw.engine.actions import GamePhase, SelectBlind
from jackdaw.engine.blind import Blind
from jackdaw.engine.game import step
from jackdaw.engine.hand_levels import HandLevels
from jackdaw.engine.rng import PseudoRandom
from jackdaw.engine.run_init import initialize_run
from jackdaw.schema.entities import entity_to_card

PHASE_IN = {
    "BLIND_SELECT": GamePhase.BLIND_SELECT,
    "SELECTING_HAND": GamePhase.SELECTING_HAND,
    "ROUND_EVAL": GamePhase.ROUND_EVAL,
    "SHOP": GamePhase.SHOP,
    "PACK_OPENED": GamePhase.PACK_OPENING,
    "GAME_OVER": GamePhase.GAME_OVER,
}
TYPE_NAME = {"small": "Small", "big": "Big", "boss": "Boss"}
STATUS = {
    "upcoming": "Upcoming",
    "current": "Current",
    "defeated": "Defeated",
    "skipped": "Skipped",
}


def build_state(snapshot: dict[str, Any]) -> tuple[dict[str, Any], str]:
    o = snapshot["observable"]
    hidden = snapshot.get("hidden") or {}
    run = o["run"]
    phase = PHASE_IN[snapshot["phase"]]
    seed = run["seed"]

    gs = initialize_run(run["deck"], run.get("stake", 1), seed)
    if phase == GamePhase.SELECTING_HAND:
        gs = step(gs, SelectBlind())  # sets up the round's internal bookkeeping
    gs["phase"] = phase

    # -- run ----------------------------------------------------------------------------------
    rr = gs["round_resets"]
    rr["ante"] = rr["blind_ante"] = run["ante"]
    gs["round"] = run.get("round_num", gs.get("round", 0))
    gs["dollars"] = run["money"]
    for k_snap, k_gs in (
        ("hand_size", "hand_size"),
        ("joker_slots", "joker_slots"),
        ("consumable_slots", "consumable_slots"),
        ("interest_cap", "interest_cap"),
    ):
        if run.get(k_snap) is not None:
            gs[k_gs] = run[k_snap]
    if run.get("base_hands") is not None:
        rr["hands"] = run["base_hands"]
    if run.get("base_discards") is not None:
        rr["discards"] = run["base_discards"]
    cr = gs["current_round"]
    if run.get("reroll_cost") is not None:
        cr["reroll_cost"] = run["reroll_cost"]
    cr["free_rerolls"] = run.get("free_rerolls", 0)

    # -- blinds -------------------------------------------------------------------------------
    current = None
    for b in o.get("blinds", []):
        name = TYPE_NAME[b["type"]]
        rr["blind_choices"][name] = b["key"]
        rr["blind_states"][name] = STATUS.get(b["status"], "Upcoming")
        if b.get("skip_tag"):
            rr.setdefault("blind_tags", {})[name] = b["skip_tag"]
        if b["status"] == "current":
            current = b
    if current is not None:
        blind = Blind.create(current["key"], run["ante"])
        blind.chips = current["chips_required"]
        blind.disabled = bool(current.get("disabled"))
        gs["blind"] = blind
        gs["blind_on_deck"] = TYPE_NAME[current["type"]]
    else:
        nxt = next((b for b in o.get("blinds", []) if b["status"] == "upcoming"), None)
        if nxt:
            gs["blind_on_deck"] = TYPE_NAME[nxt["type"]]

    # -- round --------------------------------------------------------------------------------
    rnd = o.get("round") or {}
    for k in ("hands_left", "discards_left", "hands_played", "discards_used"):
        if rnd.get(k) is not None:
            cr[k] = rnd[k]
    gs["chips"] = rnd.get("chips_scored") or 0
    tg = rnd.get("targets") or {}
    if tg.get("idol_card"):
        cr["idol_card"] = tg["idol_card"]
    if tg.get("mail_rank"):
        cr.setdefault("mail_card", {})["rank"] = tg["mail_rank"]
    if tg.get("ancient_suit"):
        cr.setdefault("ancient_card", {})["suit"] = tg["ancient_suit"]
    if tg.get("castle_suit"):
        cr.setdefault("castle_card", {})["suit"] = tg["castle_suit"]

    # -- hand levels ----------------------------------------------------------------------------
    hl = HandLevels()
    for name, v in o["hand_levels"].items():
        st = hl[name]
        st.level, st.chips, st.mult = v["level"], v["chips"], v["mult"]
        st.played = v.get("times_played_run", 0) or 0
        st.played_this_round = v.get("played_this_round", 0) or 0
        if "visible" in v:
            st.visible = v["visible"]
    gs["hand_levels"] = hl

    # -- cards ----------------------------------------------------------------------------------
    gs["hand"] = [entity_to_card(e) for e in sorted(o.get("hand", []), key=lambda e: e["position"])]
    hand_ids = {e["id"] for e in o.get("hand", [])}
    rest = [e for e in o.get("deck", []) if e["id"] not in hand_ids]
    draw = [e for e in rest if e.get("location") == "draw_pile"]
    disc = [e for e in rest if e.get("location") in ("discard", "played")]
    order = hidden.get("draw_order")
    if order:
        pos = {cid: i for i, cid in enumerate(order)}
        draw.sort(key=lambda e: -pos.get(e["id"], -1))  # engine draws from the end of the list
    else:
        random.Random(f"{seed}#load").shuffle(draw)
    gs["deck"] = [entity_to_card(e) for e in draw]
    gs["discard_pile"] = [entity_to_card(e) for e in disc]
    gs["jokers"] = [
        entity_to_card(e) for e in sorted(o.get("jokers", []), key=lambda e: e["position"])
    ]
    gs["consumables"] = [entity_to_card(e) for e in o.get("consumables", [])]

    shop = o.get("shop")
    if shop:
        gs["shop_cards"] = [entity_to_card(e) for e in shop.get("items", [])]
        gs["shop_vouchers"] = [entity_to_card(e) for e in shop.get("vouchers", [])]
        gs["shop_boosters"] = [entity_to_card(e) for e in shop.get("packs", [])]
        if shop.get("reroll_cost") is not None:
            cr["reroll_cost"] = shop["reroll_cost"]
    pack = o.get("pack")
    if pack:
        gs["pack_cards"] = [entity_to_card(e) for e in pack.get("cards", [])]
        gs["pack_type"] = pack.get("kind")
        gs["pack_choices_remaining"] = pack.get("choices_remaining", 1)
        gs.setdefault("shop_return_phase", GamePhase.SHOP)

    gs["used_vouchers"] = {k: True for k in o.get("vouchers_owned", [])}
    gs["awarded_tags"] = [
        {"key": k, "result": None, "blind": "loaded"} for k in o.get("tags_held", [])
    ]

    # -- boss history and per-round boss memory ------------------------------------------------
    bu = o.get("bosses_used")
    if bu is not None:
        # recorders may write an empty table as [] (Lua can't tell an empty dict from a list)
        gs["bosses_used"] = {k: int(v) for k, v in bu.items() if v} if isinstance(bu, dict) else {}
    bs = o.get("boss_state") or {}
    if gs.get("blind") is not None:
        if bs.get("only_hand"):
            gs["blind"].only_hand = bs["only_hand"]  # The Mouth
        if bs.get("hands_used"):
            # The Eye. The real game lists every hand with true/false; only true means used.
            gs["blind"].hands_used = {k: True for k, v in bs["hands_used"].items() if v}

    # -- hidden -------------------------------------------------------------------------------
    if hidden.get("rng_state"):
        gs["rng"] = pickle.loads(base64.b64decode(hidden["rng_state"]))
    else:
        gs["rng"] = PseudoRandom(seed)
    return gs, seed
