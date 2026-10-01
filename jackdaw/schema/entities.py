"""Conversion between jackdaw engine objects and schema v0.4 entities.

Schema: balatro_bot ``docs/state_action_schema.md`` §3.7 (Card entity).
Entity ``id`` is the engine's ``Card.sort_id``, which is stable for a card's whole life.
"""

from __future__ import annotations

import copy
from typing import Any

from jackdaw.engine.card import Card
from jackdaw.engine.card_factory import create_consumable, create_joker, create_playing_card
from jackdaw.engine.data.enums import Rank, Suit

SUIT_LETTER = {Suit.HEARTS: "H", Suit.DIAMONDS: "D", Suit.CLUBS: "C", Suit.SPADES: "S"}
LETTER_SUIT = {v: k for k, v in SUIT_LETTER.items()}
RANK_LETTER = {
    Rank.TWO: "2",
    Rank.THREE: "3",
    Rank.FOUR: "4",
    Rank.FIVE: "5",
    Rank.SIX: "6",
    Rank.SEVEN: "7",
    Rank.EIGHT: "8",
    Rank.NINE: "9",
    Rank.TEN: "T",
    Rank.JACK: "J",
    Rank.QUEEN: "Q",
    Rank.KING: "K",
    Rank.ACE: "A",
}
LETTER_RANK = {v: k for k, v in RANK_LETTER.items()}

EDITION_KEY = {
    "foil": "e_foil",
    "holo": "e_holo",
    "polychrome": "e_polychrome",
    "negative": "e_negative",
}
KEY_EDITION = {v: {k: True} for k, v in EDITION_KEY.items()}

_SET_NAMES = {
    "Default": "Default",
    "Enhanced": "Enhanced",
    "Joker": "Joker",
    "Tarot": "Tarot",
    "Planet": "Planet",
    "Spectral": "Spectral",
    "Voucher": "Voucher",
    "Booster": "Booster",
}


def edition_key(card: Card) -> str | None:
    ed = card.edition or {}
    for k, v in ed.items():
        if v and k in EDITION_KEY:
            return EDITION_KEY[k]
    return None


def _plain(v: Any) -> Any:
    """Copy an ability value into JSON-compatible data (numbers, strings, lists, dicts)."""
    if isinstance(v, (int, float, str, bool)) or v is None:
        return v
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    return str(v)


def card_to_entity(card: Card, location: str, position: int) -> dict[str, Any]:
    """Engine Card -> schema Card entity."""
    ab = card.ability or {}
    is_playing = card.base is not None
    if is_playing:
        key = card.card_key
        rank = RANK_LETTER[card.base.rank]
        suit = SUIT_LETTER[card.base.suit]
        enh = card.center_key if card.center_key not in ("c_base", None) else None
        card_set = "Enhanced" if enh else "Default"
        ability = None
        if ab.get("perma_bonus"):
            ability = {"perma_bonus": ab["perma_bonus"]}
    else:
        key = card.center_key
        rank = suit = None
        enh = None
        card_set = _SET_NAMES.get(ab.get("set", ""), ab.get("set"))
        ability = _plain(
            {k: v for k, v in ab.items() if k not in ("name", "set", "effect", "order")}
        )
    ent = {
        "id": card.sort_id,
        "key": key,
        "set": card_set,
        "rank": rank,
        "suit": suit,
        "enhancement": enh,
        "edition": edition_key(card),
        "seal": card.seal,
        "stickers": {
            "eternal": bool(card.eternal),
            "perishable_rounds": card.perish_tally if card.perishable else None,
            "rental": bool(card.rental),
        },
        "debuffed": bool(card.debuff),
        "face_down": card.facing == "back",
        "cost": {"buy": card.cost, "sell": card.sell_cost},
        "ability": ability,
        "location": location,
        "position": position,
    }
    if is_playing:
        # Not yet in schema v0.4 (see sim_evaluation "schema feedback"): The Pillar reads it.
        ent["played_this_ante"] = bool(ab.get("played_this_ante"))
    return ent


def entity_to_card(ent: dict[str, Any]) -> Card:
    """Schema Card entity -> engine Card. ``id`` is kept as the card's ``sort_id``."""
    if ent.get("rank") is not None:
        card = create_playing_card(
            LETTER_SUIT[ent["suit"]],
            LETTER_RANK[ent["rank"]],
            enhancement=ent.get("enhancement") or "c_base",
            edition=KEY_EDITION.get(ent.get("edition")),
            seal=ent.get("seal"),
        )
        if ent.get("played_this_ante"):
            card.ability["played_this_ante"] = True
        if (ent.get("ability") or {}).get("perma_bonus"):
            card.ability["perma_bonus"] = ent["ability"]["perma_bonus"]
    elif ent.get("set") == "Joker":
        st = ent.get("stickers") or {}
        card = create_joker(
            ent["key"],
            edition=KEY_EDITION.get(ent.get("edition")),
            eternal=bool(st.get("eternal")),
            perishable=st.get("perishable_rounds") is not None,
            rental=bool(st.get("rental")),
        )
        if st.get("perishable_rounds") is not None:
            card.perish_tally = st["perishable_rounds"]
        for k, v in (ent.get("ability") or {}).items():
            card.ability[k] = copy.deepcopy(v)
    else:
        card = create_consumable(ent["key"])
        if ent.get("edition"):
            card.set_edition(KEY_EDITION[ent["edition"]])
    card.sort_id = ent["id"]
    card.debuff = bool(ent.get("debuffed"))
    card.facing = "back" if ent.get("face_down") else "front"
    cost = ent.get("cost") or {}
    if cost.get("buy") is not None:
        card.cost = cost["buy"]
    if cost.get("sell") is not None:
        card.sell_cost = cost["sell"]
    return card
