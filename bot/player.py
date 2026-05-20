"""
RecommenderPlayer — human-in-the-loop poke-env Player.

Flow per turn:
  1. Score legal actions with the Recommender.
  2. Broadcast battle state + ranked recommendations to the UI.
  3. Await the user's chosen action from the UI.
  4. Play that action (or fall back to the top recommendation on timeout).

With `bridge=None` the player is autonomous (plays the top score immediately).
This lets you use the same class as the opponent if desired.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from poke_env.battle.abstract_battle import AbstractBattle
from poke_env.battle.move import Move
from poke_env.battle.pokemon import Pokemon
from poke_env.player.player import Player

from bridge import UIBridge
from recommender import Recommender
from serializer import serialize_battle

log = logging.getLogger(__name__)


class RecommenderPlayer(Player):
    def __init__(
        self,
        *args,
        recommender: Recommender,
        bridge: Optional[UIBridge] = None,
        decision_timeout: float = 120.0,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._recommender = recommender
        self._bridge = bridge
        self._decision_timeout = decision_timeout

    async def choose_move(self, battle: AbstractBattle):
        scored = self._recommender.score(battle)
        fallback = self._fallback_order(battle, scored)

        # No bridge → autonomous (play top-scored action immediately).
        if self._bridge is None:
            return fallback

        # Register a future BEFORE we broadcast, so any action the UI sends
        # in response to this update lands in the right place.
        decision = self._bridge.await_user_decision()

        try:
            payload = serialize_battle(battle, scored)
            await self._bridge.broadcast(payload)
        except Exception:
            log.exception("failed to serialize / broadcast battle update")
            return fallback

        # No UI client connected — don't block the battle forever.
        if not self._bridge.has_clients():
            log.info("no UI client connected; playing top recommendation on turn %d", battle.turn)
            return fallback

        log.info("turn %d — waiting for user decision (timeout %ds)", battle.turn, int(self._decision_timeout))
        try:
            action_msg = await asyncio.wait_for(decision, timeout=self._decision_timeout)
        except asyncio.TimeoutError:
            log.warning("decision timeout on turn %d; playing top recommendation", battle.turn)
            return fallback
        except asyncio.CancelledError:
            raise

        resolved = self._resolve_action(battle, action_msg)
        if resolved is None:
            log.warning("could not resolve UI action %r; playing top recommendation", action_msg)
            return fallback
        return self.create_order(resolved)

    # ----- helpers -----------------------------------------------------------

    def _fallback_order(self, battle: AbstractBattle, scored):
        if scored:
            return self.create_order(scored[0].action)
        return self.choose_random_move(battle)

    def _resolve_action(self, battle: AbstractBattle, msg) -> Optional[object]:
        if not isinstance(msg, dict):
            return None
        atype = msg.get("type")

        if atype == "move":
            move_id = msg.get("moveId")
            if move_id:
                for m in battle.available_moves:
                    if m.id == move_id:
                        return m

        elif atype == "switch":
            # UI sends the display species (e.g. "Landorus-Therian"); poke-env
            # uses the slug form ("landorus-therian"). Normalize both sides.
            species_raw = msg.get("species") or ""
            target = species_raw.lower().replace(" ", "")
            for p in battle.available_switches:
                if p.species.lower() == target:
                    return p

        return None
