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
