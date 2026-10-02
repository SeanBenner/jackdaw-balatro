"""Hill-climbing vs exhaustive arrangement on random builds with many order-sensitive jokers.

uv run python tests/schema/arrangement_stress.py [cases]
"""

import random
import sys
import time

from jackdaw.engine.card_factory import create_joker, create_playing_card
from jackdaw.schema import SchemaSim, scoring
from jackdaw.schema.entities import LETTER_RANK, LETTER_SUIT

POOL = [
    "j_joker",
    "j_jolly",
    "j_duo",
    "j_cavendish",
    "j_blueprint",
    "j_brainstorm",
    "j_hanging_chad",
    "j_greedy_joker",
    "j_photograph",
    "j_abstract",
    "j_stencil",
    "j_scholar",
    "j_smiley",
    "j_triboulet",
    "j_sock_and_buskin",
    "j_bull",
]
HELD_POOL = [
    "j_baron",
    "j_shoot_the_moon",
    "j_raised_fist",
    "j_mime",
    "j_blueprint",
    "j_duo",
    "j_joker",
]
ENH = [None, None, "m_glass", "m_mult", "m_steel", "m_bonus"]
ED = [None, None, None, {"polychrome": True}, {"holo": True}]


def build(rng, held_mode=False):
    sim = SchemaSim()
    sim.reset(f"STRESS{rng.random()}", "b_blue", 1)
    sim.step({"type": "select_blind"})
    gs = sim.gs
    hand = []
    for _ in range(8):
        c = create_playing_card(
            LETTER_SUIT[rng.choice("HDCS")],
            LETTER_RANK[rng.choice("23456789TJQKA")],
            enhancement=rng.choice(ENH) or "c_base",
            edition=rng.choice(ED),
            seal=rng.choice([None, None, None, "Red"]),
        )
        hand.append(c)
    if held_mode:
        hand = hand[:6]  # 2-3 played, 3-4 held
        keys = rng.sample(HELD_POOL, 3)
    else:
        keys = rng.sample(POOL, rng.choice([4, 5]))
    gs["hand"] = hand
    gs["jokers"] = [create_joker(k, edition=rng.choice(ED)) for k in keys]
    sim._exit()
    return sim


MODE = None  # None = production default (exhaustive when small); False = force hill-climbing


def main(cases, held_mode=False):
    rng = random.Random(7)
    agree = total = 0
    gaps = []
    t_hc = t_ex = 0.0
    for _ in range(cases):
        sim = build(rng, held_mode)
        played = rng.sample(sim.gs["hand"], rng.choice([2, 3]))
        held = [c for c in sim.gs["hand"] if c not in played]
        for obj in ("max", "min"):
            t = time.perf_counter()
            hc = scoring.arrange(sim.gs, played, held, sim.gs["jokers"], obj, exhaustive=MODE)
            t_hc += time.perf_counter() - t
            t = time.perf_counter()
            ex = scoring.arrange(sim.gs, played, held, sim.gs["jokers"], obj, exhaustive=True)
            t_ex += time.perf_counter() - t
            total += 1
            a, b = hc["score"]["expected"], ex["score"]["expected"]
            if a == b:
                agree += 1
            else:
                gaps.append((obj, a, b, abs(a - b) / max(abs(b), 1)))
    print(
        f"{'held-joker builds' if held_mode else 'many-joker builds'}: agree {agree}/{total}; "
        f"search {1000 * t_hc / total:.0f} ms/arrangement, "
        f"exhaustive {1000 * t_ex / total:.0f} ms"
    )
    for g in sorted(gaps, key=lambda g: -g[3])[:10]:
        print("  gap", g)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    for MODE in (None, False):
        print("default search" if MODE is None else "forced hill-climbing")
        main(n)
        main(n, held_mode=True)
