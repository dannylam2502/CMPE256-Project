// ============================================================================
// CORE BATTLE TYPES
// ============================================================================
// These mirror what poke-env exposes on its `Battle` object so the Python side
// can serialize them with minimal mapping. Keep them stable — the connector
// contract depends on this shape.

export type StatusCondition =
  | 'healthy'
  | 'brn' // burn
  | 'par' // paralysis
  | 'slp' // sleep
  | 'frz' // freeze
  | 'psn' // poison
  | 'tox' // bad poison
  | 'fnt'; // fainted

export type PokemonType =
  | 'normal' | 'fire' | 'water' | 'electric' | 'grass' | 'ice'
  | 'fighting' | 'poison' | 'ground' | 'flying' | 'psychic' | 'bug'
  | 'rock' | 'ghost' | 'dragon' | 'dark' | 'steel' | 'fairy';

export type MoveCategory = 'physical' | 'special' | 'status';

export type StatName = 'atk' | 'def' | 'spa' | 'spd' | 'spe' | 'accuracy' | 'evasion';

export interface MoveInfo {
  id: string;
  name: string;
  type: PokemonType;
  category: MoveCategory;
  basePower: number;
  accuracy: number; // 0–100, 0 means doesn't check
  pp: { current: number; max: number };
  priority?: number;
  description?: string;
}

export interface PokemonState {
  species: string;
  level: number;
  hp: { current: number; max: number; fraction: number }; // fraction 0–1; opponent often only exposes fraction
  status: StatusCondition;
  types: PokemonType[];
  ability?: string;
  item?: string | null;
  teraType?: PokemonType;
  terastallized?: boolean;
  moves?: MoveInfo[]; // own team: full info. opponent: only revealed moves, possibly empty.
  isActive: boolean;
  fainted: boolean;
  boosts?: Partial<Record<StatName, number>>; // -6..+6, only meaningful when active
  revealed: boolean; // for opponent team: have we seen this mon yet?
}

export interface SideConditions {
  hazards: Array<'stealthrock' | 'spikes' | 'toxicspikes' | 'stickyweb'>;
  spikesLayers?: number;
  toxicSpikesLayers?: number;
  screens: Array<'reflect' | 'lightscreen' | 'auroraveil'>;
  tailwind?: boolean;
  tailwindTurnsLeft?: number;
}

export interface FieldState {
  weather?: 'sun' | 'rain' | 'sand' | 'snow' | 'hail' | null;
  weatherTurnsLeft?: number;
  terrain?: 'electric' | 'grassy' | 'misty' | 'psychic' | null;
  terrainTurnsLeft?: number;
  trickRoom?: boolean;
  trickRoomTurnsLeft?: number;
  player: SideConditions;
  opponent: SideConditions;
}

export interface SideState {
  name: string;
  team: PokemonState[]; // length up to 6
  active: PokemonState | null; // alias to the active mon in `team`
}

export interface BattleState {
  turn: number;
  format: string; // e.g. "gen9randombattle"
  player: SideState;
  opponent: SideState;
  field: FieldState;
  availableActions: BattleAction[]; // legal options THIS turn
  finished: boolean;
  winner?: 'player' | 'opponent' | 'tie';
}

// ============================================================================
// ACTIONS — the discrete choices the player can make on a turn.
// ============================================================================

export interface MoveAction {
  type: 'move';
  move: MoveInfo;
  terastallize?: boolean;
}

export interface SwitchAction {
  type: 'switch';
  pokemon: PokemonState;
}

export type BattleAction = MoveAction | SwitchAction;

/** Stable identifier so the UI can compare actions across updates. */
export function actionKey(action: BattleAction): string {
  if (action.type === 'move') return `move:${action.move.id}${action.terastallize ? ':tera' : ''}`;
  return `switch:${action.pokemon.species}`;
}

// ============================================================================
// RECOMMENDATIONS
// ============================================================================

export interface Recommendation {
  action: BattleAction;
  /** Score in [0, 1]. Higher is better. The connector decides what the scale means
   *  (logit-softmax, expected damage, win probability...) — UI just renders it. */
  score: number;
  /** Optional human-readable reasoning shown under the action. */
  reasoning?: string;
  /** Optional structured signals — flexible bag the model can populate.
   *  e.g. { expectedDamageFrac: 0.42, koProbability: 0.8 } */
  signals?: Record<string, number | string | boolean>;
}

// ============================================================================
// LOG
// ============================================================================

export type LogEntryKind =
  | 'turn'
  | 'move'
  | 'switch'
  | 'damage'
  | 'heal'
  | 'status'
  | 'faint'
  | 'field'
  | 'system';

export interface LogEntry {
  id: string; // stable id, often `${turn}:${seq}`
  turn: number;
  kind: LogEntryKind;
  text: string;
  side?: 'player' | 'opponent';
}

// ============================================================================
// THE UPDATE THE CONNECTOR PUSHES TO THE UI
// ============================================================================

export interface BattleUpdate {
  /** Full snapshot of current battle state. Connectors push snapshots, not deltas
   *  — keeps the wire format dead simple. UI does its own diffing. */
  state: BattleState;
  /** Ranked best-first. Empty array means "no recommendation this turn" (forced switch etc). */
  recommendations: Recommendation[];
  /** Newly appended log entries since the previous update. Empty on first update is fine. */
  newLogEntries?: LogEntry[];
  /** Wall-clock timestamp for ordering / latency tracking. */
  timestamp: number;
}

export interface ConnectionStatus {
  state: 'disconnected' | 'connecting' | 'connected' | 'error';
  message?: string;
  /** Connector identifier so the UI can show which backend is live. */
  source?: string;
}
