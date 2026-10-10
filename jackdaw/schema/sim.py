"""``SchemaSim``: jackdaw behind the balatro_bot simulator contract (schema v0.4 §6).

    sim = SchemaSim()
    snap = sim.reset("SEED", "b_blue", 1)
    masks = sim.legal_actions()
    snap, events = sim.step({"type": "select_blind"})
    sim.preview([12, 31])                      # exact score after the best arrangement
    sim.step({"type": "play", "cards": [12, 31], "objective": "max"})

Entities are referred to by ``id`` (the engine's stable ``Card.sort_id``).
"""

from __future__ import annotations

import base64
import copy
import pickle
import random
from collections.abc import Callable
from typing import Any

import jackdaw.engine.card as _card_mod
from jackdaw.engine import actions as A
from jackdaw.engine.actions import GamePhase
from jackdaw.engine.game import IllegalActionError
from jackdaw.engine.game import step as engine_step
from jackdaw.engine.run_init import initialize_run
from jackdaw.schema import scoring
from jackdaw.schema.snapshot import PHASE, make_snapshot

SHOP_LISTS = (("shop_cards", "card"), ("shop_vouchers", "voucher"), ("shop_boosters", "pack"))


class SchemaError(ValueError):
    """An action that doesn't fit the current state (bad ids, wrong phase, bad targets)."""


class SchemaSim:
    def __init__(self) -> None:
        self.gs: dict[str, Any] | None = None
        self.seed: str = ""
        self._id_counter = 0

    # ------------------------------------------------------------------ id counter isolation
    # jackdaw keeps the card-id counter as module state and resets it per run; each sim keeps its
    # own
    # so several sims (clones, search) in one process never hand out colliding ids.
    def _enter(self) -> None:
        _card_mod._sort_id_counter = self._id_counter

    def _exit(self) -> None:
        self._id_counter = _card_mod._sort_id_counter

    def _engine(self, action: Any) -> None:
        self._enter()
        try:
            self.gs = engine_step(self.gs, action)
        finally:
            self._exit()

    # ------------------------------------------------------------------ contract
    def reset(self, seed: str, deck: str = "b_blue", stake: int = 1) -> dict[str, Any]:
        _card_mod.reset_sort_id_counter()
        self.gs = initialize_run(deck, stake, seed)
        self.seed = seed
        self._exit()
        return self.snapshot()

    def snapshot(self, *, include_engine_state: bool = False) -> dict[str, Any]:
        return make_snapshot(self.gs, seed=self.seed, include_engine_state=include_engine_state)

    def clone(self) -> SchemaSim:
        other = SchemaSim()
        other.gs = copy.deepcopy(self.gs)
        other.seed = self.seed
        other._id_counter = self._id_counter
        return other

    def load(self, snapshot: dict[str, Any]) -> None:
        """Resume from a snapshot. Sim-made snapshots with ``hidden.engine_state`` restore exactly;
        anything else (recorded or constructed states) is rebuilt from ``observable``."""
        eng = (snapshot.get("hidden") or {}).get("engine_state")
        if eng:
            self.gs = pickle.loads(base64.b64decode(eng))
            self.seed = snapshot["observable"]["run"]["seed"]
            self._id_counter = max(_all_ids(self.gs), default=0)
            return
        from jackdaw.schema.load import build_state

        self._enter()
        try:
            self.gs, self.seed = build_state(snapshot)
            _card_mod._sort_id_counter = max(
                _card_mod._sort_id_counter, max(_all_ids(self.gs), default=0)
            )
        finally:
            self._exit()

    def phase(self) -> str:
        return PHASE[self.gs["phase"]]

    # ------------------------------------------------------------------ legal actions
    def legal_actions(self) -> dict[str, Any]:
        """Masks per action type (schema §4): which types are legal, which entity ids each argument
        may take, and list-length bounds. Consumable targets carry their own min/max."""
        from jackdaw.env.consumable_targets import (
            get_consumable_target_spec,
            get_valid_target_cards,
        )

        gs = self.gs
        ph = gs["phase"]
        hand = gs.get("hand", [])
        jokers = gs.get("jokers", [])
        cons = gs.get("consumables", [])
        engine_legal = A.get_legal_actions(gs) if ph != GamePhase.GAME_OVER else []
        types: dict[str, Any] = {}

        def targets_for(card):
            spec = get_consumable_target_spec(card, gs)
            if not spec.needs_card_targets:
                return {"cards": [], "min": 0, "max": 0}
            if spec.target_filter == "all_hand":
                return {"cards": [c.sort_id for c in hand], "min": 0, "max": 0, "all_hand": True}
            valid = get_valid_target_cards(card, hand, gs)
            return {
                "cards": [hand[i].sort_id for i in valid],
                "min": spec.min_targets,
                "max": spec.max_targets,
            }

        if ph == GamePhase.BLIND_SELECT:
            if any(isinstance(a, A.SelectBlind) for a in engine_legal):
                types["select_blind"] = {}
            if any(isinstance(a, A.SkipBlind) for a in engine_legal):
                types["skip_blind"] = {}
        if ph == GamePhase.SELECTING_HAND:
            cr = gs["current_round"]
            forced = [c.sort_id for c in hand if c.ability.get("forced_selection")]
            if hand and cr.get("hands_left", 0) > 0:
                types["play"] = {
                    "cards": [c.sort_id for c in hand],
                    "min": 1,
                    "max": min(5, len(hand)),
                    "must_include": forced,
                    "objective": ["max", "min"],
                }
            if hand and cr.get("discards_left", 0) > 0:
                types["discard"] = {
                    "cards": [c.sort_id for c in hand],
                    "min": 1,
                    "max": min(5, len(hand)),
                    "must_include": forced,
                }
        if ph == GamePhase.ROUND_EVAL:
            types["cash_out"] = {}
        if ph == GamePhase.SHOP:
            buy = []
            for a in engine_legal:
                if isinstance(a, A.BuyCard):
                    buy.append(gs["shop_cards"][a.shop_index].sort_id)
                elif isinstance(a, A.RedeemVoucher):
                    buy.append(gs["shop_vouchers"][a.card_index].sort_id)
                elif isinstance(a, A.OpenBooster):
                    buy.append(gs["shop_boosters"][a.card_index].sort_id)
            if buy:
                types["buy"] = {"card": buy}
            if any(isinstance(a, A.Reroll) for a in engine_legal):
                types["reroll"] = {}
            types["next_round"] = {}
        if ph == GamePhase.PACK_OPENING:
            pick = {}
            for a in engine_legal:
                if isinstance(a, A.PickPackCard):
                    c = gs["pack_cards"][a.card_index]
                    pick[c.sort_id] = (
                        targets_for(c)
                        if c.ability.get("set") in ("Tarot", "Spectral")
                        else {"cards": [], "min": 0, "max": 0}
                    )
            if pick:
                types["pack_pick"] = {"card": list(pick), "targets": pick}
            types["pack_skip"] = {}
        if ph != GamePhase.GAME_OVER:
            usable = [cons[a.card_index] for a in engine_legal if isinstance(a, A.UseConsumable)]
            if usable and ph in (GamePhase.SELECTING_HAND, GamePhase.SHOP, GamePhase.BLIND_SELECT,
                               GamePhase.PACK_OPENING):
                types["use_consumable"] = {
                    "card": [c.sort_id for c in usable],
                    "targets": {c.sort_id: targets_for(c) for c in usable},
                }
            sell = [
                (jokers if a.area == "jokers" else cons)[a.card_index].sort_id
                for a in engine_legal
                if isinstance(a, A.SellCard)
            ]
            if sell:
                types["sell"] = {"card": sell}
            if len(jokers) > 1:
                types["rearrange_jokers"] = {"order": [c.sort_id for c in jokers]}
        return {"phase": PHASE[ph], "types": types}

    # ------------------------------------------------------------------ step
    def step(self, action: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        gs = self.gs
        t = action.get("type")
        money0, chips0 = gs.get("dollars", 0), gs.get("chips", 0)
        hand0 = {c.sort_id for c in gs.get("hand", [])}
        events: list[dict[str, Any]] = []
        try:
            if t == "select_blind":
                self._engine(A.SelectBlind())
            elif t == "skip_blind":
                self._engine(A.SkipBlind())
            elif t == "play":
                events.append(self._play(action["cards"], action.get("objective", "max")))
            elif t == "discard":
                self._engine(A.Discard(tuple(self._hand_idx(action["cards"]))))
            elif t == "rearrange_jokers":
                gs["jokers"] = self._reorder(gs.get("jokers", []), action["order"])
            elif t == "rearrange_hand":
                # the hand's on-screen order (the player's sort or drags); The Death copies the
                # rightmost selected card, by position
                gs["hand"] = self._reorder(gs.get("hand", []), action["order"])
            elif t == "use_consumable":
                i = self._index(gs.get("consumables", []), action["card"])
                self._engine(A.UseConsumable(i, self._targets(action)))
            elif t == "sell":
                area = (
                    "jokers"
                    if any(c.sort_id == action["card"] for c in gs.get("jokers", []))
                    else "consumables"
                )
                self._engine(A.SellCard(area, self._index(gs.get(area, []), action["card"])))
            elif t == "buy":
                self._buy(action["card"])
            elif t == "buy_and_use":
                gs["_buy_and_use"] = True               # no room needed: it never lands in the slots
                try:
                    self._buy(action["card"])
                finally:
                    self.gs.pop("_buy_and_use", None)
                gs = self.gs
                cons = gs.get("consumables", [])
                self._engine(
                    A.UseConsumable(self._index(cons, action["card"]), self._targets(action))
                )
            elif t == "reroll":
                self._engine(A.Reroll())
            elif t == "next_round":
                self._engine(A.NextRound())
            elif t == "pack_pick":
                i = self._index(gs.get("pack_cards", []), action["card"])
                self._engine(A.PickPackCard(i, self._targets(action)))
            elif t == "pack_skip":
                self._engine(A.SkipPack())
            elif t == "cash_out":
                self._engine(A.CashOut())
            else:
                raise SchemaError(f"unknown action type {t!r}")
        except IllegalActionError as e:
            raise SchemaError(str(e)) from e
        gs = self.gs
        drawn = [c.sort_id for c in gs.get("hand", []) if c.sort_id not in hand0]
        if drawn:
            events.append({"type": "drawn", "cards": drawn})
        if gs.get("dollars", 0) != money0:
            events.append({"type": "money", "delta": gs.get("dollars", 0) - money0})
        if t == "play":
            events.append({"type": "chips", "delta": gs.get("chips", 0) - chips0})
        return self.snapshot(), events

    # ------------------------------------------------------------------ scoring
    def preview(self, card_ids: list[int], objective: str = "max") -> dict[str, Any]:
        """Exact score of playing these cards after the arrangement for ``objective`` (schema §3.6).
        Never changes the game state."""
        arr = self.arrange_for_score(card_ids, objective)
        s = arr["score"]
        return {
            "hand_type": s["hand_type"],
            "chips": s["chips"],
            "mult": s["mult"],
            "total": s["total"],
            "scoring_card_ids": s["scoring_card_ids"],
            "deterministic": s["deterministic"],
            "expected": s["expected"],
            "min": s["min"],
            "max": s["max"],
            "arrangement": {k: arr[k] for k in ("played", "held", "jokers", "objective")},
        }

    def score_arrangement(
        self, played: list[int], held: list[int] | None = None, jokers: list[int] | None = None
    ) -> dict[str, Any]:
        """Score one explicit arrangement (e.g. the order a human used). Never changes the state."""
        by_id = {c.sort_id: c for c in self.gs.get("hand", [])}
        p, h = self._split(played)
        p = [by_id[i] for i in played]
        if held is not None:
            if sorted(held) != sorted(c.sort_id for c in h):
                raise SchemaError("held must list every unplayed hand card")
            h = [by_id[i] for i in held]
        js = self.gs.get("jokers", [])
        j = self._reorder(js, jokers) if jokers is not None else list(js)
        return scoring.score_dist(self.gs, p, h, j)

    def arrange_for_score(self, card_ids: list[int], objective: str = "max") -> dict[str, Any]:
        played, held = self._split(card_ids)
        return scoring.arrange(self.gs, played, held, list(self.gs.get("jokers", [])), objective)

    def score_distribution(
        self,
        n: int,
        policy: Callable[[SchemaSim], dict[str, Any]],
        *,
        blind: str | None = None,
        seed: int = 0,
    ) -> dict[str, Any]:
        """Play the next blind ``n`` times from the current build with fresh shuffles of the
        observable
        deck (schema §6.1). Must be called at BLIND_SELECT. ``blind`` optionally forces the current
        blind's key (e.g. 'bl_plant'). ``policy(sim)`` returns schema actions for SELECTING_HAND."""
        if self.gs["phase"] != GamePhase.BLIND_SELECT:
            raise SchemaError("score_distribution starts from BLIND_SELECT")
        from jackdaw.engine.rng import PseudoRandom

        totals, bests, beats = [], [], 0
        for k in range(n):
            sim = self.clone()
            g = sim.gs
            g["rng"] = PseudoRandom(f"{self.seed}#dist{seed}_{k}")  # no access to the real future
            pool = g.get("deck", []) + g.get("hand", []) + g.get("discard_pile", [])
            random.Random(f"{seed}_{k}").shuffle(pool)
            g["deck"], g["hand"], g["discard_pile"] = pool, [], []
            if blind:
                on_deck = g.get("blind_on_deck", "Small")
                g["round_resets"]["blind_choices"][on_deck] = blind
            sim.step({"type": "select_blind"})
            required = sim.gs["blind"].chips
            best = 0
            while sim.gs["phase"] == GamePhase.SELECTING_HAND:
                before = sim.gs.get("chips", 0)
                sim.step(policy(sim))
                best = max(best, sim.gs.get("chips", 0) - before)
            total = sim.gs.get("chips", 0)
            totals.append(total)
            bests.append(best)
            beats += total >= required
        q = _quantiles
        return {"n": n, "beat_fraction": beats / n, "round_total": q(totals), "best_hand": q(bests)}

    # ------------------------------------------------------------------ helpers
    def _play(self, card_ids: list[int], objective: str) -> dict[str, Any]:
        gs = self.gs
        arr = self.arrange_for_score(card_ids, objective)
        standing = [c.sort_id for c in gs.get("jokers", [])]
        by_id = {c.sort_id: c for c in gs["hand"]}
        gs["hand"] = [by_id[i] for i in arr["played"]] + [by_id[i] for i in arr["held"]]
        gs["jokers"] = self._reorder(gs["jokers"], arr["jokers"])
        self._engine(A.PlayHand(tuple(range(len(card_ids)))))
        # restore the policy's standing joker order (schema §4.1); new jokers go to the end
        alive = {c.sort_id: c for c in self.gs.get("jokers", [])}
        self.gs["jokers"] = [alive[i] for i in standing if i in alive] + [
            c for c in self.gs.get("jokers", []) if c.sort_id not in standing
        ]
        res = self.gs.get("last_score_result")
        return {
            "type": "score",
            "arrangement": {k: arr[k] for k in ("played", "held", "jokers")},
            "hand_type": res.hand_type,
            "chips": res.chips,
            "mult": res.mult,
            "total": res.total,
            "breakdown": list(res.breakdown),
            "predicted": arr["score"]["expected"],
        }

    def _split(self, card_ids: list[int]) -> tuple[list, list]:
        hand = self.gs.get("hand", [])
        ids = set(card_ids)
        if len(ids) != len(card_ids) or not ids <= {c.sort_id for c in hand}:
            raise SchemaError("cards must be distinct ids of cards in hand")
        return [c for c in hand if c.sort_id in ids], [c for c in hand if c.sort_id not in ids]

    def _hand_idx(self, card_ids: list[int]) -> list[int]:
        return [self._index(self.gs.get("hand", []), i) for i in card_ids]

    def _targets(self, action: dict[str, Any]) -> tuple[int, ...] | None:
        tg = action.get("targets")
        return tuple(self._hand_idx(tg)) if tg else None

    @staticmethod
    def _index(cards: list, card_id: int) -> int:
        for i, c in enumerate(cards):
            if c.sort_id == card_id:
                return i
        raise SchemaError(f"no card with id {card_id}")

    @staticmethod
    def _reorder(cards: list, order: list[int]) -> list:
        by_id = {c.sort_id: c for c in cards}
        if sorted(order) != sorted(by_id):
            raise SchemaError("order must list every card id exactly once")
        return [by_id[i] for i in order]

    def _buy(self, card_id: int) -> None:
        for key, kind in SHOP_LISTS:
            for i, c in enumerate(self.gs.get(key, [])):
                if c.sort_id == card_id:
                    act = {
                        "card": A.BuyCard(i),
                        "voucher": A.RedeemVoucher(i),
                        "pack": A.OpenBooster(i),
                    }[kind]
                    self._engine(act)
                    return
        raise SchemaError(f"no shop item with id {card_id}")


def _quantiles(xs: list[float]) -> dict[str, float]:
    s = sorted(xs)
    pick = lambda p: s[min(len(s) - 1, int(p * (len(s) - 1) + 0.5))]  # noqa: E731
    return {
        "p10": pick(0.1),
        "p25": pick(0.25),
        "p50": pick(0.5),
        "p75": pick(0.75),
        "p90": pick(0.9),
        "mean": sum(s) / len(s),
    }


def _all_ids(gs: dict[str, Any]) -> list[int]:
    ids = []
    for k in (
        "deck",
        "hand",
        "discard_pile",
        "jokers",
        "consumables",
        "shop_cards",
        "shop_vouchers",
        "shop_boosters",
        "pack_cards",
    ):
        ids += [c.sort_id for c in gs.get(k, []) or []]
    return ids
