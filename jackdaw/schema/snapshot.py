"""Engine game_state -> schema v0.4 snapshot (balatro_bot docs/state_action_schema.md §3)."""

from __future__ import annotations

import base64
import pickle
from typing import Any

from jackdaw.engine.actions import GamePhase
from jackdaw.engine.data.blind_scaling import get_blind_amount
from jackdaw.engine.data.prototypes import BLINDS
from jackdaw.schema.entities import card_to_entity

SCHEMA_VERSION = "0.4"
GAME_VERSION = "1.0.1o"
ENGINE = {"name": "jackdaw", "fork_of": "TylerFlar/jackdaw-balatro@e66de78"}

PHASE = {
    GamePhase.BLIND_SELECT: "BLIND_SELECT",
    GamePhase.SELECTING_HAND: "SELECTING_HAND",
    GamePhase.ROUND_EVAL: "ROUND_EVAL",
    GamePhase.SHOP: "SHOP",
    GamePhase.PACK_OPENING: "PACK_OPENED",
    GamePhase.GAME_OVER: "GAME_OVER",
}
BLIND_TYPES = (("Small", "small"), ("Big", "big"), ("Boss", "boss"))


def _boss_state(gs: dict[str, Any]) -> dict[str, Any]:
    """Per-round boss memory the blind list can't express (The Mouth's locked hand, The Eye's used hands)."""
    b = gs.get("blind")
    if b is None:
        return {"only_hand": None, "hands_used": None}
    used = getattr(b, "hands_used", None) or {}
    return {"only_hand": getattr(b, "only_hand", None),
            "hands_used": {k: True for k, v in used.items() if v} or None}
HAND_ORDER = [
    "Flush Five",
    "Flush House",
    "Five of a Kind",
    "Straight Flush",
    "Four of a Kind",
    "Full House",
    "Flush",
    "Straight",
    "Three of a Kind",
    "Two Pair",
    "Pair",
    "High Card",
]


def stake_scaling(gs: dict[str, Any]) -> int:
    return (gs.get("modifiers") or {}).get("scaling", 1) or 1


def ante_scaling(gs: dict[str, Any]) -> float:
    return (gs.get("starting_params") or {}).get("ante_scaling", 1) or 1


def blind_chips(gs: dict[str, Any], key: str, ante: int) -> int:
    return int(get_blind_amount(ante, stake_scaling(gs)) * BLINDS[key].mult * ante_scaling(gs))


def _blinds(gs: dict[str, Any]) -> list[dict[str, Any]]:
    rr = gs.get("round_resets", {})
    ante = rr.get("ante", 1)
    choices = rr.get("blind_choices", {})
    states = rr.get("blind_states", {})
    tags = rr.get("blind_tags", {})
    cur = gs.get("blind")
    out = []
    for name, typ in BLIND_TYPES:
        key = choices.get(name)
        if key is None:
            continue
        status = (states.get(name) or "upcoming").lower()
        status = {
            "select": "upcoming",
            "current": "current",
            "defeated": "defeated",
            "skipped": "skipped",
            "upcoming": "upcoming",
        }.get(status, status)
        is_current = status == "current" and cur is not None and getattr(cur, "key", None) == key
        proto = BLINDS[key]
        out.append(
            {
                "type": typ,
                "key": key,
                "chips_required": cur.chips if is_current else blind_chips(gs, key, ante),
                "reward": 0
                if (
                    typ == "small"
                    and (gs.get("modifiers") or {}).get("no_blind_reward", {}).get("Small")
                )
                else proto.dollars,
                "status": status,
                "skip_tag": tags.get(name) if typ != "boss" else None,
                "disabled": bool(getattr(cur, "disabled", False)) if is_current else False,
            }
        )
    return out


def _upcoming_requirements(
    gs: dict[str, Any], blinds: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Every remaining blind requirement through the winning ante (schema §3.3)."""
    ante = gs.get("round_resets", {}).get("ante", 1)
    win = gs.get("win_ante", 8)
    out = []
    for b in blinds:
        if b["status"] in ("upcoming", "current"):
            out.append({"ante": ante, "type": b["type"], "chips_required": b["chips_required"]})
    for a in range(ante + 1, win + 1):
        for key, typ in (("bl_small", "small"), ("bl_big", "big")):
            out.append({"ante": a, "type": typ, "chips_required": blind_chips(gs, key, a)})
        # which boss is hidden; a regular boss is x2, the ante-8 showdown boss is x2 too
        out.append(
            {"ante": a, "type": "boss", "chips_required": int(blind_chips(gs, "bl_small", a) * 2)}
        )
    return out


def _hand_levels(gs: dict[str, Any]) -> dict[str, Any]:
    hl = gs.get("hand_levels")
    out = {}
    for name in HAND_ORDER:
        st = hl[name]
        out[name] = {
            "level": st.level,
            "chips": st.chips,
            "mult": st.mult,
            "times_played_run": st.played,
            # schema §3.4 asks for times_played_ante; the engine tracks per-round counts
            "times_played_ante": None,
            "played_this_round": st.played_this_round,
            "visible": st.visible,
        }
    return out


def _tags_held(gs: dict[str, Any]) -> list[str]:
    held = []
    for t in gs.get("awarded_tags", []):
        if any(k.endswith("_fired") and v for k, v in t.items()):
            continue
        if t.get("result") is not None:  # immediate tags resolve on award
            continue
        held.append(t["key"])
    return held


def make_snapshot(
    gs: dict[str, Any], *, seed: str, include_engine_state: bool = False
) -> dict[str, Any]:
    phase = PHASE.get(gs.get("phase"), str(gs.get("phase")))
    cr = gs.get("current_round", {})
    rr = gs.get("round_resets", {})
    blinds = _blinds(gs)
    cur = next((b for b in blinds if b["status"] == "current"), None)

    hand = [card_to_entity(c, "hand", i) for i, c in enumerate(gs.get("hand", []))]
    draw = [card_to_entity(c, "draw_pile", i) for i, c in enumerate(gs.get("deck", []))]
    disc = [card_to_entity(c, "discard", i) for i, c in enumerate(gs.get("discard_pile", []))]
    for e in draw:  # draw-pile contents are visible to the player, their order is not
        e["position"] = None
    deck = sorted(hand + draw + disc, key=lambda e: e["id"])

    shop = None
    if phase in ("SHOP", "PACK_OPENED"):
        shop = {
            "items": [card_to_entity(c, "shop", i) for i, c in enumerate(gs.get("shop_cards", []))],
            "vouchers": [
                card_to_entity(c, "shop", i) for i, c in enumerate(gs.get("shop_vouchers", []))
            ],
            "packs": [
                card_to_entity(c, "shop", i) for i, c in enumerate(gs.get("shop_boosters", []))
            ],
            "reroll_cost": cr.get("reroll_cost"),
        }
    pack = None
    if phase == "PACK_OPENED":
        pack = {
            "kind": gs.get("pack_type"),
            "cards": [card_to_entity(c, "pack", i) for i, c in enumerate(gs.get("pack_cards", []))],
            "choices_remaining": gs.get("pack_choices_remaining"),
        }

    snap = {
        "schema_version": SCHEMA_VERSION,
        "phase": phase,
        "observable": {
            "run": {
                "seed": seed,
                "deck": gs.get("selected_back_key"),
                "stake": gs.get("stake", 1),
                "ante": rr.get("ante", 1),
                "round_num": gs.get("round", 0),
                "money": gs.get("dollars", 0),
                "interest_cap": gs.get("interest_cap"),
                "hand_size": gs.get("hand_size"),
                "joker_slots": gs.get("joker_slots"),
                "consumable_slots": gs.get("consumable_slots"),
                "base_hands": rr.get("hands"),
                "base_discards": rr.get("discards"),
                "reroll_cost": cr.get("reroll_cost"),
                "free_rerolls": cr.get("free_rerolls", 0),
                "game_version": GAME_VERSION,
                "mods": [],
                "engine": ENGINE,
            },
            "round": {
                "hands_left": cr.get("hands_left", 0),
                "discards_left": cr.get("discards_left", 0),
                "hands_played": cr.get("hands_played", 0),
                "discards_used": cr.get("discards_used", 0),
                "chips_scored": gs.get("chips", 0)
                if phase in ("SELECTING_HAND", "ROUND_EVAL")
                else 0,
                "chips_required": cur["chips_required"] if cur else None,
                # per-round joker targets (not yet in schema v0.4)
                "targets": {
                    "idol_card": cr.get("idol_card"),
                    "mail_rank": (cr.get("mail_card") or {}).get("rank"),
                    "ancient_suit": (cr.get("ancient_card") or {}).get("suit"),
                    "castle_suit": (cr.get("castle_card") or {}).get("suit"),
                    "todo_hand": next(
                        (
                            j.ability.get("to_do_poker_hand")
                            for j in gs.get("jokers", [])
                            if j.center_key == "j_todo_list"
                        ),
                        None,
                    ),
                },
            },
            "blinds": blinds,
            "upcoming_requirements": _upcoming_requirements(gs, blinds),
            "hand_levels": _hand_levels(gs),
            "hand": hand,
            "jokers": [card_to_entity(c, "jokers", i) for i, c in enumerate(gs.get("jokers", []))],
            "consumables": [
                card_to_entity(c, "consumables", i) for i, c in enumerate(gs.get("consumables", []))
            ],
            "deck": deck,
            "shop": shop,
            "pack": pack,
            "vouchers_owned": sorted(k for k, v in (gs.get("used_vouchers") or {}).items() if v),
            "tags_held": _tags_held(gs),
            "score_preview": None,  # per selection: SchemaSim.preview(card_ids)
            # boss blinds seen this run ({key: times}); a boss can't return until every
            # eligible boss has appeared, so this tells which bosses are still ahead
            "bosses_used": {k: v for k, v in (gs.get("bosses_used") or {}).items() if v},
            "boss_state": _boss_state(gs),
        },
        "hidden": {
            # jackdaw draws from the end of the deck list
            "draw_order": [c.sort_id for c in reversed(gs.get("deck", []))],
            "rng_state": base64.b64encode(pickle.dumps(gs.get("rng"))).decode(),
            "upcoming_shop": None,
        },
    }
    if include_engine_state:
        snap["hidden"]["engine_state"] = base64.b64encode(pickle.dumps(gs)).decode()
    return snap
