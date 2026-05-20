"""
Recommender protocol — the plug-in point for action scoring.

To wire in your ML model (or a heuristic, search algorithm, etc.) implement
the `Recommender` protocol below and pass an instance into `RecommenderPlayer`
via the `recommender=` kwarg. Nothing else in the bot needs to change.

A `Recommender` is just one method: given a `Battle`, return the available
actions ranked best-first with a score in [0, 1] and optional reasoning.

The action is either:
  - a `Move`    → use this move
  - a `Pokemon` → switch to this Pokémon

`battle.available_moves` and `battle.available_switches` give you the legal
options for the current turn. Don't return illegal actions.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Protocol, Union

from poke_env.battle.abstract_battle import AbstractBattle
from poke_env.battle.move import Move
from poke_env.battle.pokemon import Pokemon


Action = Union[Move, Pokemon]


@dataclass
class ScoredAction:
    action: Action
    score: float        # 0.0 = worst, 1.0 = best
    reasoning: str = "" # one-line human-readable explanation; shown in UI


class Recommender(Protocol):
    """Plug-in interface. Implement this for any scoring strategy."""
    name: str

    def score(self, battle: AbstractBattle) -> list[ScoredAction]:
        """Score every legal action this turn. Return ranked best-first."""
        ...


# ---------------------------------------------------------------------------
# Placeholder implementation. Replace with your model once it's trained.
# ---------------------------------------------------------------------------

class RandomRecommender:
    """Random scoring so the pipe works end-to-end before the ML model lands."""
    name = "random"

    def score(self, battle: AbstractBattle) -> list[ScoredAction]:
        actions: list[Action] = []
        actions.extend(battle.available_moves)
        actions.extend(battle.available_switches)

        scored = [
            ScoredAction(action=a, score=random.uniform(0.1, 0.9), reasoning="random baseline")
            for a in actions
        ]
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored


# ---------------------------------------------------------------------------
# Example sketch — a one-line heuristic, shows what your ML version replaces.
# ---------------------------------------------------------------------------

class HighestBasePowerRecommender:
    """Toy heuristic: highest base power wins, switches scored lower than moves."""
    name = "highest-bp"

    def score(self, battle: AbstractBattle) -> list[ScoredAction]:
        scored: list[ScoredAction] = []

        for move in battle.available_moves:
            bp = move.base_power or 0
            stab = 1.5 if battle.active_pokemon and move.type in battle.active_pokemon.types else 1.0
            score = min(1.0, (bp * stab) / 180.0)
            scored.append(ScoredAction(
                action=move,
                score=score,
                reasoning=f"BP {bp}" + (" · STAB" if stab > 1 else ""),
            ))

        for switch in battle.available_switches:
            scored.append(ScoredAction(
                action=switch,
                score=0.15,
                reasoning=f"pivot to {switch.species}",
            ))

        scored.sort(key=lambda s: s.score, reverse=True)
        return scored
