"""Side-effect-free scoring and the score arrangement search (schema §3.6, §4.1).

``score_play`` runs jackdaw's own pipeline (``Blind.press_play`` + ``score_hand``) on deep copies of
everything the pipeline mutates (played/held cards, jokers, hand levels, blind, RNG, money), so
calling it never changes the live game_state.

``arrange`` chooses the played-card order, held-card order and joker order that best meets the
objective ("max" or "min"). Cards and jokers with identical observable signatures are
interchangeable,
so only distinct orders are tried. If the joint search space is small it is searched exhaustively;
otherwise hill-climbing over swap/move neighbourhoods is used. Tests compare the two on the
real-game
fixtures and on random many-joker builds.
"""

from __future__ import annotations

import copy
import itertools
from typing import Any

from jackdaw.engine.rng import PseudoRandom
from jackdaw.engine.scoring import score_hand

EXHAUSTIVE_LIMIT = 200
PERM_LIMIT = 720
SAMPLES = 32  # random-effect samples for reported expected/min/max
SEARCH_SAMPLES = 4  # common random draws per candidate while searching arrangements
MAX_EVALS = 300  # evaluation budget per hill-climbing search

# Content whose effect on the score is random (schema §3.6 reports these as a distribution).
RANDOM_ENHANCEMENTS = {"m_lucky"}
RANDOM_JOKERS = {"j_misprint", "j_bloodstone", "j_space"}
RANDOM_BOSSES = {"The Hook", "Crimson Heart"}


def _copy_card(c):
    """Copy everything scoring can mutate on a card (much faster than deepcopy)."""
    n = copy.copy(c)
    n.ability = copy.deepcopy(c.ability)
    if c.base is not None:
        n.base = copy.copy(c.base)
    if c.edition is not None:
        n.edition = dict(c.edition)
    return n


def _prep(gs: dict[str, Any], played: list, held: list) -> dict[str, Any]:
    """The top-level fields score_hand reads (mirrors game._handle_play_hand)."""
    cr = gs["current_round"]
    # scratch copy: every list/dict one level deep, so effects that append (The Hook's discards,
    # created cards) or set flags land in the copy, never in the live game_state
    g = {
        k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v)
        for k, v in gs.items()
    }
    g["hands_left"] = cr.get("hands_left", 0) - 1
    g["current_round_hands_played"] = cr.get("hands_played", 0)
    g["discards_left"] = cr.get("discards_left", 0)
    g["discards_used"] = cr.get("discards_used", 0)
    g["money"] = gs.get("dollars", 0)
    g["deck_cards_remaining"] = len(gs.get("deck", []))
    all_cards = gs.get("deck", []) + held + gs.get("discard_pile", []) + played
    g["playing_cards_count"] = len(all_cards)
    g["stone_tally"] = sum(1 for c in all_cards if c.center_key == "m_stone")
    g["steel_tally"] = sum(1 for c in all_cards if c.center_key == "m_steel")
    g["enhanced_card_count"] = sum(1 for c in all_cards if c.center_key not in ("", "c_base"))
    g["mail_card_id"] = cr.get("mail_card", {}).get("id")
    g["idol_card"] = cr.get("idol_card")
    g["ancient_suit"] = cr.get("ancient_card", {}).get("suit")
    g["consumable_usage_tarot"] = gs.get("consumable_usage_total", {}).get("tarot", 0)
    return g


def is_random(gs: dict[str, Any], played: list, held: list, jokers: list) -> bool:
    if getattr(gs.get("blind"), "name", "") in RANDOM_BOSSES and not getattr(
        gs.get("blind"), "disabled", False
    ):
        return True
    if any(c.center_key in RANDOM_ENHANCEMENTS for c in played):
        return True
    return any(j.center_key in RANDOM_JOKERS for j in jokers)


def score_play(
    gs: dict[str, Any], played: list, held: list, jokers: list, *, rng: PseudoRandom | None = None
) -> dict[str, Any]:
    """Score one play on copies.

    Returns hand_type, chips, mult, total, scoring card ids and dollars."""
    from jackdaw.engine.game import _press_play

    played_c = [_copy_card(c) for c in played]
    held_c = [_copy_card(c) for c in held]
    jokers_c = [_copy_card(c) for c in jokers]
    hl, blind = copy.deepcopy((gs["hand_levels"], gs["blind"]))
    rng_c = copy.copy(rng or gs["rng"])
    rng_c._state = dict(rng_c._state)
    g = _prep(gs, played_c, held_c)
    g.update(
        hand=held_c,
        jokers=jokers_c,
        hand_levels=hl,
        blind=blind,
        rng=rng_c,
        current_round=dict(gs["current_round"]),
    )
    blind.triggered = False
    _press_play(g, blind, played_c, rng_c)
    held_c = g["hand"]  # The Hook may have removed cards
    res = score_hand(
        played_c,
        held_c,
        jokers_c,
        hl,
        blind,
        rng_c,
        probabilities_normal=gs.get("probabilities", {}).get("normal", 1),
        game_state=g,
        back_key=gs.get("selected_back_key"),
        blind_chips=blind.chips,
    )
    return {
        "hand_type": res.hand_type,
        "chips": res.chips,
        "mult": res.mult,
        "total": res.total,
        "scoring_card_ids": [c.sort_id for c in res.scoring_cards],
        "dollars": res.dollars_earned + (g.get("dollars", 0) - gs.get("dollars", 0)),
        "debuffed": res.debuffed,
    }


def score_dist(
    gs: dict[str, Any], played: list, held: list, jokers: list, samples: int | None = None
) -> dict[str, Any]:
    """Score, and if randomness is involved, sample it (expected/min/max over ``samples`` draws,
    default SAMPLES). Draws use fixed per-index streams, so candidates are compared on common
    random numbers."""
    base = score_play(gs, played, held, jokers)
    if not is_random(gs, played, held, jokers):
        return {
            **base,
            "deterministic": True,
            "expected": base["total"],
            "min": base["total"],
            "max": base["total"],
        }
    seed = gs["rng"].seed_str if hasattr(gs["rng"], "seed_str") else "SAMPLE"
    totals = [
        score_play(gs, played, held, jokers, rng=PseudoRandom(f"{seed}#preview{k}"))["total"]
        for k in range(samples or SAMPLES)
    ]
    return {
        **base,
        "deterministic": False,
        "expected": sum(totals) / len(totals),
        "min": min(totals),
        "max": max(totals),
        "samples": len(totals),
    }


# --------------------------------------------------------------------------- arrangement search


def _sig(c) -> tuple:
    """Observable identity: cards with equal signatures are interchangeable for scoring."""
    ab = c.ability or {}
    return (
        c.card_key,
        c.center_key,
        tuple(sorted((c.edition or {}).items())),
        c.seal,
        bool(c.debuff),
        bool(ab.get("played_this_ante")),
        ab.get("perma_bonus", 0),
        repr(sorted((k, v) for k, v in ab.items() if isinstance(v, (int, float))))
        if c.base is None
        else "",
    )


def distinct_orders(items: list, limit: int = PERM_LIMIT) -> list[list]:
    """Distinct permutations up to signature equivalence (capped)."""
    out, seen = [], set()
    for p in itertools.permutations(range(len(items))):
        key = tuple(_sig(items[i]) for i in p)
        if key in seen:
            continue
        seen.add(key)
        out.append([items[i] for i in p])
        if len(out) >= limit:
            break
    return out


def _held_relevant(held: list, jokers: list) -> bool:
    """Held order can matter only if a joker acts on held cards; held steel (x1.5) and gold
    (money) effects on their own commute. Blueprint/Brainstorm can copy those jokers."""
    held_jokers = {"j_baron", "j_shoot_the_moon", "j_raised_fist", "j_mime", "j_reserved_parking"}
    return len(held) > 1 and any(j.center_key in held_jokers for j in jokers)


def _card_order_matters(played: list) -> bool:
    """Without jokers, played-card effects are +chips (commute), +mult and xmult. Order changes
    the score only when +mult and xmult cards are both present."""
    plus = any(
        c.center_key in ("m_mult", "m_lucky") or (c.edition or {}).get("holo") for c in played
    )
    times = any(c.center_key == "m_glass" or (c.edition or {}).get("polychrome") for c in played)
    return plus and times


def _better(a: float, b: float | None, objective: str) -> bool:
    return b is None or (a > b if objective == "max" else a < b)


def _neighbours(order: list) -> list[list]:
    """All orders one swap or one move (remove + reinsert) away."""
    n, out = len(order), []
    for i in range(n):
        for k in range(i + 1, n):
            o = list(order)
            o[i], o[k] = o[k], o[i]
            out.append(o)
    for i in range(n):
        for k in range(n):
            if k in (i, i + 1):
                continue
            o = list(order)
            x = o.pop(i)
            o.insert(k if k < i else k - 1, x)
            out.append(o)
    return out


def arrange(
    gs: dict[str, Any],
    played: list,
    held: list,
    jokers: list,
    objective: str = "max",
    *,
    exhaustive: bool | None = None,
) -> dict[str, Any]:
    """Best (played order, held order, joker order) for the objective, by expected score.

    1. Lists whose order can't change the score are left alone: no jokers and no +mult/xmult card
       mix means nothing to search; otherwise the played and joker lists are probed (every
       rotation of the order and of its reverse) and kept fixed if no probe changes the score.
       Held order (with a held-card joker) and joker order (with Blueprint/Brainstorm) are always
       searched.
    2. The remaining lists are searched exhaustively over distinct orders if the joint space is at
       most EXHAUSTIVE_LIMIT, else by hill-climbing over swap/move neighbourhoods from two starts,
       within MAX_EVALS evaluations.
    3. Candidates are compared on SEARCH_SAMPLES common random draws; the winner is re-scored with
       SAMPLES draws for the reported expected/min/max.

    ``exhaustive=True`` skips the probes and searches every list fully (used by tests)."""
    if objective not in ("max", "min"):
        raise ValueError("objective must be 'max' or 'min'")
    cache: dict[tuple, dict] = {}
    held_matters = _held_relevant(held, jokers)

    def key(o):
        return tuple(_sig(x) for x in o)

    def ev(p, h, j):
        k = (key(p), key(h) if held_matters else (), key(j))
        if k not in cache:
            cache[k] = score_dist(gs, p, h, j, samples=SEARCH_SAMPLES)
        return cache[k]

    def result(p, h, j, space, exh):
        r = score_dist(gs, p, h, j)
        return {
            "played": [c.sort_id for c in p],
            "held": [c.sort_id for c in h],
            "jokers": [c.sort_id for c in j],
            "objective": objective,
            "score": r,
            "evaluated": max(len(cache), 1),
            "search_space": space,
            "exhaustive": exh,
        }

    p0, h0, j0 = list(played), list(held), list(jokers)
    if not exhaustive and not jokers and not _card_order_matters(played):
        return result(p0, h0, j0, 1, True)

    # which lists can change the score?
    free = {"p": len(played) > 1, "h": held_matters, "j": len(jokers) > 1}
    if not exhaustive:
        base = ev(p0, h0, j0)["expected"]
        # held order is already gated on a held-card joker being present and is always searched.
        # Copy jokers make joker order matter through adjacency, which probes can't see, so with
        # Blueprint/Brainstorm the joker order is always searched too.
        copiers = any(j.center_key in ("j_blueprint", "j_brainstorm") for j in jokers)
        for name, lst in (("p", p0), ("j", j0)):
            if not free[name] or (name == "j" and copiers):
                continue
            rev = list(reversed(lst))
            probes = [lst[i:] + lst[:i] for i in range(1, len(lst))]
            probes += [rev[i:] + rev[:i] for i in range(len(rev))]
            same = True
            for o in probes:
                cand = {"p": p0, "h": h0, "j": j0}
                cand[name] = o
                if ev(cand["p"], cand["h"], cand["j"])["expected"] != base:
                    same = False
                    break
            free[name] = not same
        if not any(free.values()):
            return result(p0, h0, j0, 1, False)

    p_opts = distinct_orders(played) if free["p"] else [p0]
    h_opts = distinct_orders(held, limit=120) if free["h"] else [h0]
    j_opts = distinct_orders(jokers) if free["j"] else [j0]
    space = len(p_opts) * len(j_opts) * len(h_opts)
    if exhaustive is None:
        exhaustive = space <= EXHAUSTIVE_LIMIT

    best, best_v = None, None

    def consider(p, h, j):
        nonlocal best, best_v
        v = ev(p, h, j)["expected"]
        if _better(v, best_v, objective):
            best, best_v = (p, h, j), v
        return v

    if exhaustive:
        for p in p_opts:
            for h in h_opts:
                for j in j_opts:
                    consider(p, h, j)
    else:
        slots = [i for i, n in ((2, "j"), (0, "p"), (1, "h")) if free[n]]
        for start in ((p0, h0, j0), (p0, h0, list(reversed(j0)))):
            cur = start
            cur_v = consider(*cur)
            improved = True
            while improved and len(cache) < MAX_EVALS:
                improved = False
                for slot in slots:
                    for o in _neighbours(cur[slot]):
                        cand = tuple(o if i == slot else cur[i] for i in range(3))
                        v = consider(*cand)
                        if _better(v, cur_v, objective):
                            cur, cur_v, improved = cand, v, True
                        if len(cache) >= MAX_EVALS:
                            break
    return result(*best, space, exhaustive)
