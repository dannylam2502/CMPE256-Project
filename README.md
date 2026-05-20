# Battle Recommender — UI

Svelte 5 + Bun + Vite. Localhost-only for now. The UI is built against a
typed `BattleConnector` contract so the recommender backend can be swapped
without touching any component.

## Run

```bash
bun install
bun run dev
```

Open http://localhost:5173. The UI boots with the **mock connector** so you
can iterate on look and feel without a backend running. Use the toggle in the
top-right to switch to `PYTHON BOT` once your bot is up.

## The Contract

Everything UI-facing flows through one type (`src/lib/types.ts → BattleUpdate`)
and one interface (`src/lib/connectors/connector.ts → BattleConnector`).

```ts
interface BattleConnector {
  readonly name: string;
  connect(): Promise<void>;
  disconnect(): Promise<void>;
  onUpdate(cb: (u: BattleUpdate) => void): () => void;
  onStatus(cb: (s: ConnectionStatus) => void): () => void;
  sendAction?(action: BattleAction): Promise<void>; // optional
}
```

The store (`src/lib/stores/battle.ts`) accepts any implementation:

```ts
await battleStore.setConnector(new MyCustomConnector());
```

## Wire Format (for the Python side)

`WebSocketConnector` expects JSON messages over a plain WebSocket at
`ws://localhost:8765` (configurable). Snapshots, not deltas.

**Server → Client**
```json
{ "type": "update", "payload": <BattleUpdate> }
{ "type": "status", "payload": <ConnectionStatus> }
{ "type": "error",  "payload": { "message": "..." } }
```

**Client → Server** (only when human-in-the-loop)
```json
{ "type": "action", "payload": { "type": "move", "moveId": "earthquake", "terastallize": false } }
{ "type": "action", "payload": { "type": "switch", "species": "Heatran" } }
```

The `BattleUpdate` shape is the source of truth — see `src/lib/types.ts`.
JSON-serialize the same field names from poke-env's `Battle` object and you're done.

## Project Layout

```
src/
├── App.svelte                     ← root, picks the connector
├── main.ts                        ← Svelte 5 mount
├── app.css                        ← design tokens, dark terminal aesthetic
└── lib/
    ├── types.ts                   ← BattleState, MoveInfo, Recommendation, BattleUpdate
    ├── connectors/
    │   ├── connector.ts           ← BattleConnector interface
    │   ├── mock.ts                ← simulated battle for local UI iteration
    │   ├── websocket.ts           ← Python bot client (with auto-reconnect)
    │   └── index.ts
    ├── stores/
    │   └── battle.ts              ← reactive store (Svelte 5 runes)
    ├── data/
    │   └── typeColors.ts          ← authentic Pokémon type palette
    └── components/
        ├── PokemonCard.svelte
        ├── TeamPanel.svelte
        ├── RecommendationPanel.svelte
        ├── FieldStatus.svelte
        ├── BattleLog.svelte
        ├── TypeBadge.svelte
        └── ConnectionIndicator.svelte
```

## Adding a Backend

Two options when your Python bot is ready:

**Option A — match the existing wire format.** Have the bot expose a
WebSocket server at `ws://localhost:8765`, send `{"type": "update", "payload": ...}`
messages with the `BattleUpdate` shape. Zero UI changes.

**Option B — write your own connector.** Implement `BattleConnector` for
HTTP polling, SSE, gRPC-web, or whatever fits. Add it to the mode toggle in
`App.svelte` and you're done.

## Design Choices Worth Knowing

- **Snapshots, not deltas.** Every update carries the full battle state. The
  protocol is trivially debuggable and reconnects are stateless.
- **No `sendAction` ≠ broken.** If the connector doesn't implement
  `sendAction`, the UI silently switches to observer mode (no EXEC buttons).
  Useful for bot-vs-bot spectating.
- **Type colors are functional.** The 18 Pokémon type colors aren't a theme
  choice — competitive players read matchups by color. They stay.
