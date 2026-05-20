# Battle Recommender — Bot

poke-env bot that scores legal actions every turn, streams the battle state +
ranked recommendations to the Svelte UI over WebSocket, and plays the
top-scored action.

## Layout

```
bot/
├── pyproject.toml
├── main.py             ← entry point (two bots, self-play)
├── recommender.py      ← THE plug-in point: implement `Recommender`
├── serializer.py       ← poke-env Battle → UI's BattleUpdate JSON
├── bridge.py           ← WebSocket server on :8765
└── player.py           ← RecommenderPlayer (poke-env subclass)
```

## Run

In **three separate terminals**:

```bash
# Terminal 1 — Showdown
cd ~/PokemonProject/pokemon-showdown
node pokemon-showdown start --no-security

# Terminal 2 — UI
cd ~/PokemonProject/pokemon-recommender-ui
bun run dev

# Terminal 3 — bot
cd ~/PokemonProject/bot
source .venv/bin/activate
python main.py
```

Open the UI in your browser, click **PYTHON BOT** in the top right. You should
see the connection indicator turn green and battle state stream in.

## Adding Your ML Model

Everything in `bot/` is one abstraction away from your model.

1. Open `recommender.py`.
2. Implement a class with `name: str` and `score(battle) -> list[ScoredAction]`.
3. In `main.py`, replace `RandomRecommender()` with `YourRecommender()`.

That's it. No other file needs to change.

Example skeleton:

```python
class ReplayTrainedRecommender:
    name = "xgb-v1"

    def __init__(self, model_path: str):
        self.model = joblib.load(model_path)

    def score(self, battle: AbstractBattle) -> list[ScoredAction]:
        features = extract_features(battle)              # your feature extractor
        scored = []
        for move in battle.available_moves:
            x = features_for_action(features, move)      # your per-action features
            p = float(self.model.predict_proba([x])[0, 1])
            scored.append(ScoredAction(move, p, f"P(win|use)={p:.2f}"))
        for switch in battle.available_switches:
            x = features_for_action(features, switch)
            p = float(self.model.predict_proba([x])[0, 1])
            scored.append(ScoredAction(switch, p, f"pivot · P(win|switch)={p:.2f}"))
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored
```

## Why two bots?

Self-play gives you an infinite stream of turns to watch in the UI without
needing a Showdown ladder account. Only `p1` streams to the UI (`bridge=bridge`);
`p2` plays without telemetry (`bridge=None`).

If you want to play the bot against yourself instead, swap out the self-play
in `main.py` for `await p1.accept_challenges(opponent="your_username", n_challenges=10)`.

## Troubleshooting

**`Connection refused` to ws://localhost:8000** — Showdown isn't running, or
it bound to a different port. Look for `Worker 1 now listening on 0.0.0.0:8000`
in Terminal 1.

**`Username RecBot1-xxxx already taken`** — Showdown holds onto disconnected
sessions briefly. Wait 30 seconds or restart Showdown. The bot already adds a
random suffix per launch, so this is usually transient.

**UI shows DISCONNECTED with red dot** — verify `WS_PORT` in `main.py` matches
the URL in `pokemon-recommender-ui/src/App.svelte` (both default to `8765`).

**`AttributeError` in serializer.py** — poke-env API changed between versions.
The serializer is defensive but not exhaustive. The bot continues running;
check the log and add a `getattr` guard for the missing field.

**Bot freezes after the first turn** — the recommender returned an illegal
action. Make sure `score()` only includes items from `battle.available_moves`
and `battle.available_switches`.
