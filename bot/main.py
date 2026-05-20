"""
Entry point. Runs one human-in-the-loop RecommenderPlayer (gated on UI input)
against a simple bot opponent. Each turn the UI shows recommendations; the bot
waits for you to accept or override.

Prerequisites:
  1. Showdown server running:  cd ../pokemon-showdown && node pokemon-showdown start --no-security
  2. UI dev server running:    cd ../pokemon-recommender-ui && bun run dev
  3. This venv active:         source .venv/bin/activate

Run:
  python main.py
"""
from __future__ import annotations

import asyncio
import logging
import os

from poke_env import AccountConfiguration
from poke_env.player import MaxBasePowerPlayer

from bridge import UIBridge
from player import RecommenderPlayer
from recommender import HighestBasePowerRecommender
from ml_recommender import TransformerRecommender

# --- Config ---------------------------------------------------------------
# Model was trained on Gen 3 OU. Random Battle uses Gen 3 mons so the hash
# embeddings will hit familiar slots; team OU would be ideal but needs a team
# spec. Switch this to "gen3ou" once you wire in a team.
BATTLE_FORMAT = "gen3randombattle"
N_BATTLES = 3                 # smaller default; you're playing them by hand
WS_PORT = 8765                # matches WebSocketConnector URL in App.svelte
DECISION_TIMEOUT_S = 300.0    # bot waits 5 minutes per turn before falling back

MODEL_WEIGHTS_PATH = "20Epoch.pt"   # path to your trained model checkpoint

_SUFFIX = os.urandom(2).hex()


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    root = logging.getLogger("main")

    # Load model BEFORE the UI connects so any load errors surface early.
    if os.path.exists(MODEL_WEIGHTS_PATH):
        recommender = TransformerRecommender(MODEL_WEIGHTS_PATH)
        root.info("Using TransformerRecommender (%s)", MODEL_WEIGHTS_PATH)
    else:
        recommender = HighestBasePowerRecommender()
        root.warning("Model weights not found at %s — falling back to heuristic.", MODEL_WEIGHTS_PATH)

    bridge = UIBridge(port=WS_PORT)
    await bridge.start()
    root.info("→ Open http://localhost:4242 and click PYTHON BOT in the top-right.")
    root.info("   Waiting for the UI to connect before starting battles…")
    await bridge.wait_for_client()
    root.info("UI connected. Starting battles.")

    # You — the human-in-the-loop player. Gated on UI input each turn.
    you = RecommenderPlayer(
        account_configuration=AccountConfiguration(f"You-{_SUFFIX}", None),
        battle_format=BATTLE_FORMAT,
        recommender=recommender,
        bridge=bridge,
        decision_timeout=DECISION_TIMEOUT_S,
        log_level=logging.WARNING,
    )

    # Opponent — a stock poke-env baseline. Plays autonomously and fast.
    # Swap for `RandomPlayer` for easier games, `SimpleHeuristicsPlayer` for tougher.
    opponent = MaxBasePowerPlayer(
        account_configuration=AccountConfiguration(f"Foe-{_SUFFIX}", None),
        battle_format=BATTLE_FORMAT,
        log_level=logging.WARNING,
    )

    root.info("Starting %d battle(s) against %s", N_BATTLES, opponent.username)
    await you.battle_against(opponent, n_battles=N_BATTLES)
    root.info("Done. You won %d / %d.", you.n_won_battles, N_BATTLES)

    # Hold the bridge open so the final battle state stays on screen.
    # Ctrl+C in this terminal to exit.
    root.info("All battles complete. Bridge staying open — Ctrl+C to exit.")
    try:
        await asyncio.Event().wait()
    finally:
        await bridge.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down.")
