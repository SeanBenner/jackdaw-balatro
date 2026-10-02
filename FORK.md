# balatro_bot fork of jackdaw

Forked from [TylerFlar/jackdaw-balatro](https://github.com/TylerFlar/jackdaw-balatro) at `e66de78`
(2026-09-19). Remote `upstream` points there; pull fixes with `git fetch upstream && git merge upstream/main`.

Why we forked, and what needs changing: see `docs/sim_evaluation.md` in the balatro_bot project.
In short, the rules are right (89/89 real-game scoring scenarios), but the interface has to be brought
up to the balatro_bot state/action schema: separate observable and hidden state, `load`/`snapshot`,
legal-action masks that encode consumable targets, a side-effect-free `preview`, `arrange_for_score`,
and `score_distribution`.

Additions in this fork:
- `tests/engine/test_game_scenarios.py` + `tests/fixtures/game_scenarios/`: the 89 real-game scoring
  fixtures (recorded with BalatroBot from Balatro 1.0.1o). They must keep passing on every change.

Licensing note: upstream is MIT, but the engine is a close port of the game's decompiled code and
`jackdaw/engine/data/*.json` is extracted from the game. Keep this fork private until that's resolved.

## Schema v0.4 interface: `jackdaw.schema.SchemaSim`

```python
from jackdaw.schema import SchemaSim
sim = SchemaSim()
snap = sim.reset("SEED", "b_blue", 1)          # Blue Deck, White Stake
masks = sim.legal_actions()                    # {"phase", "types": {type: argument masks}}
snap, events = sim.step({"type": "select_blind"})
sim.preview([12, 31])                          # exact score after the best arrangement; pure
snap, events = sim.step({"type": "play", "cards": [12, 31], "objective": "max"})
```

| Contract item | Status |
|---|---|
| `reset`, `step`, `snapshot`, `clone` | done. Entity ids are the engine's `sort_id`; each sim keeps its own id counter |
| `load` | done. Exact for sim snapshots made with `include_engine_state=True`; otherwise rebuilt from `observable` (draw order from `hidden.draw_order` or a seeded shuffle; voucher side effects not visible as run numbers aren't re-applied). Tested on SELECTING_HAND states and the 89 real-game fixtures |
| `legal_actions` | done. Per-type masks with ids, min/max lengths, `must_include` (Cerulean Bell), consumable/pack targets with min/max. 12 random runs: every sampled action accepted |
| `preview`, `score_arrangement` | done. Side-effect free (tested under The Hook). Random effects: 32 samples on fresh RNG streams → `expected/min/max` |
| `arrange_for_score` | done. Lists whose order can't change the score are skipped (no jokers and no +mult/xmult card mix; otherwise played and joker order are probed over all rotations of the order and its reverse). Held order is searched when a held-card joker is present, and joker order is always searched with Blueprint/Brainstorm. Exhaustive when ≤200 distinct orders, else hill-climbing within 300 evaluations. Candidates are compared on 4 common random draws (`SEARCH_SAMPLES`), and the winner is re-scored with 32 (`SAMPLES`). Matches exhaustive on all 89 fixtures (max and min) and on 100/100 random 4–5-joker builds; forced hill-climbing alone gets 99/100 (`tests/schema/arrangement_stress.py`) |
| `score_distribution` | done. Reshuffles the observable deck with fresh RNG; caller supplies the play policy |
| `events` | minimal: score (with jackdaw's text breakdown and the arrangement), cards drawn, money, chips |

Known gaps: `hand_levels.times_played_ante` is null (the engine tracks per-round counts, exposed as
`played_this_round`); future boss requirements assume the usual x2 (The Wall, The Needle and Violet
Vessel differ); `tags_held` is inferred from jackdaw's per-tag fired flags; structured per-step scoring
events aren't emitted yet.

Speed (i9-9900K, one process, random legal actions, Blue/White): ~1,200 decisions/s through the
schema layer when runs end in ante 1, ~750/s on longer runs (random policies rarely hold jokers).
Per play, the arrangement costs ~1 ms with no jokers and roughly 20–80 ms with 4–5 order-sensitive
jokers. That's the main cost once a policy builds a joker line-up; the next step is a faster
scorer (see the balatro_bot sim evaluation's speed plan). The raw engine is ~5,300 decisions/s.
