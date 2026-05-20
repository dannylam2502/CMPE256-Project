import type {
  BattleAction,
  BattleState,
  BattleUpdate,
  ConnectionStatus,
  LogEntry,
  MoveInfo,
  PokemonState,
  PokemonType,
  Recommendation
} from '../types';
import type { BattleConnector } from './connector';

// ----------------------------------------------------------------------------
// Mock data — a single skirmish that loops, just enough to exercise the UI.
// ----------------------------------------------------------------------------

const MOVES: Record<string, MoveInfo> = {
  earthquake: { id: 'earthquake', name: 'Earthquake', type: 'ground', category: 'physical', basePower: 100, accuracy: 100, pp: { current: 10, max: 10 } },
  stoneedge: { id: 'stoneedge', name: 'Stone Edge', type: 'rock', category: 'physical', basePower: 100, accuracy: 80, pp: { current: 8, max: 8 } },
  icepunch: { id: 'icepunch', name: 'Ice Punch', type: 'ice', category: 'physical', basePower: 75, accuracy: 100, pp: { current: 15, max: 15 } },
  swordsdance: { id: 'swordsdance', name: 'Swords Dance', type: 'normal', category: 'status', basePower: 0, accuracy: 0, pp: { current: 20, max: 20 } },
  closecombat: { id: 'closecombat', name: 'Close Combat', type: 'fighting', category: 'physical', basePower: 120, accuracy: 100, pp: { current: 8, max: 8 } },
  flamethrower: { id: 'flamethrower', name: 'Flamethrower', type: 'fire', category: 'special', basePower: 90, accuracy: 100, pp: { current: 15, max: 15 } },
  thunderbolt: { id: 'thunderbolt', name: 'Thunderbolt', type: 'electric', category: 'special', basePower: 90, accuracy: 100, pp: { current: 15, max: 15 } },
  recover: { id: 'recover', name: 'Recover', type: 'normal', category: 'status', basePower: 0, accuracy: 0, pp: { current: 8, max: 8 } }
};

function mkMon(
  species: string,
  types: PokemonType[],
  hpMax: number,
  moveIds: string[],
  opts: Partial<PokemonState> = {}
): PokemonState {
  return {
    species,
    level: 80,
    hp: { current: hpMax, max: hpMax, fraction: 1 },
    status: 'healthy',
    types,
    ability: opts.ability,
    item: opts.item ?? null,
    moves: moveIds.map((id) => ({ ...MOVES[id] })),
    isActive: opts.isActive ?? false,
    fainted: false,
    revealed: true,
    boosts: opts.isActive ? {} : undefined,
    ...opts
  };
}

function buildInitialState(): BattleState {
  const playerTeam = [
    mkMon('Garchomp', ['dragon', 'ground'], 357, ['earthquake', 'stoneedge', 'icepunch', 'swordsdance'], { isActive: true, ability: 'Rough Skin', item: 'Choice Scarf' }),
    mkMon('Heatran', ['fire', 'steel'], 311, ['flamethrower', 'earthquake', 'stoneedge', 'flamethrower'], { ability: 'Flash Fire', item: 'Leftovers' }),
    mkMon('Tapu Koko', ['electric', 'fairy'], 261, ['thunderbolt', 'closecombat', 'flamethrower', 'icepunch'], { ability: 'Electric Surge', item: 'Life Orb' }),
    mkMon('Toxapex', ['poison', 'water'], 290, ['recover', 'flamethrower', 'icepunch', 'thunderbolt'], { ability: 'Regenerator', item: 'Black Sludge' }),
    mkMon('Landorus-Therian', ['ground', 'flying'], 319, ['earthquake', 'stoneedge', 'swordsdance', 'icepunch'], { ability: 'Intimidate', item: 'Rocky Helmet' }),
    mkMon('Clefable', ['fairy'], 322, ['recover', 'flamethrower', 'thunderbolt', 'icepunch'], { ability: 'Magic Guard', item: 'Leftovers' })
  ];

  const opponentTeam = [
    mkMon('Dragapult', ['dragon', 'ghost'], 1, ['thunderbolt', 'flamethrower', 'icepunch', 'closecombat'], { isActive: true, ability: 'Infiltrator' }),
    mkMon('Corviknight', ['flying', 'steel'], 1, [], { revealed: false, moves: [] }),
    mkMon('Ferrothorn', ['grass', 'steel'], 1, [], { revealed: false, moves: [] }),
    mkMon('Excadrill', ['ground', 'steel'], 1, [], { revealed: false, moves: [] }),
    mkMon('Slowking-Galar', ['poison', 'psychic'], 1, [], { revealed: false, moves: [] }),
    mkMon('Rillaboom', ['grass'], 1, [], { revealed: false, moves: [] })
  ];
  // For opponent we only know fractional HP.
  for (const m of opponentTeam) m.hp = { current: 100, max: 100, fraction: 1 };
  opponentTeam[0].hp = { current: 76, max: 100, fraction: 0.76 };

  const player = playerTeam[0];
  const opponent = opponentTeam[0];

  const availableActions: BattleAction[] = [
    ...(player.moves ?? []).map((m) => ({ type: 'move' as const, move: m })),
    ...playerTeam.filter((p) => !p.isActive && !p.fainted).map((p) => ({ type: 'switch' as const, pokemon: p }))
  ];

  return {
    turn: 7,
    format: 'gen9ou',
    player: { name: 'You', team: playerTeam, active: player },
    opponent: { name: 'Opponent', team: opponentTeam, active: opponent },
    field: {
      weather: null,
      terrain: 'electric',
      terrainTurnsLeft: 3,
      trickRoom: false,
      player: { hazards: ['stealthrock'], screens: [] },
      opponent: { hazards: ['stealthrock', 'spikes'], spikesLayers: 1, screens: [] }
    },
    availableActions,
    finished: false
  };
}

function mockRecommendations(state: BattleState): Recommendation[] {
  // Make-believe scores so the UI has something interesting to render.
  // Real connector will replace this entirely.
  const recs: Recommendation[] = state.availableActions.map((action, i) => {
    if (action.type === 'move') {
      const m = action.move;
      // Crude favoring of high-BP STAB.
      const stab = state.player.active?.types.includes(m.type) ? 1.2 : 1.0;
      const base = (m.basePower / 120) * stab * (m.accuracy === 0 ? 1 : m.accuracy / 100);
      return {
        action,
        score: Math.min(0.99, Math.max(0.05, base * (0.85 + Math.random() * 0.3))),
        reasoning:
          m.category === 'status'
            ? 'Sets up next turn — strong if you can survive the incoming hit.'
            : `Hits for ${m.basePower} BP${stab > 1 ? ' with STAB' : ''}. Likely 2HKO.`,
        signals: { expectedDamageFrac: Math.min(1, base * 0.6) }
      };
    }
    const switchRec: Recommendation = {
      action,
      score: 0.1 + Math.random() * 0.3,
      reasoning: `Pivot to ${action.pokemon.species} to absorb a likely hit.`
    };
    return switchRec;
  });
  recs.sort((a, b) => b.score - a.score);
  return recs;
}

// ----------------------------------------------------------------------------
// MockConnector
// ----------------------------------------------------------------------------

export class MockConnector implements BattleConnector {
  readonly name = 'mock';

  private updateCallbacks = new Set<(u: BattleUpdate) => void>();
  private statusCallbacks = new Set<(s: ConnectionStatus) => void>();
  private status: ConnectionStatus = { state: 'disconnected', source: this.name };
  private latestUpdate: BattleUpdate | null = null;
  private tickHandle: ReturnType<typeof setInterval> | null = null;
  private logSeq = 0;

  async connect(): Promise<void> {
    this.setStatus({ state: 'connecting', source: this.name });
    await new Promise((r) => setTimeout(r, 350));
    this.setStatus({ state: 'connected', source: this.name, message: 'Mock battle running' });
    this.pushSnapshot(buildInitialState(), [this.mkLog(7, 'turn', 'Turn 7')]);
    // Re-roll recommendations every few seconds so the UI feels alive.
    this.tickHandle = setInterval(() => {
      if (!this.latestUpdate) return;
      const recs = mockRecommendations(this.latestUpdate.state);
      this.emit({ ...this.latestUpdate, recommendations: recs, timestamp: Date.now() });
    }, 4000);
  }

  async disconnect(): Promise<void> {
    if (this.tickHandle) clearInterval(this.tickHandle);
    this.tickHandle = null;
    this.setStatus({ state: 'disconnected', source: this.name });
  }

  onUpdate(callback: (u: BattleUpdate) => void): () => void {
    this.updateCallbacks.add(callback);
    if (this.latestUpdate) callback(this.latestUpdate);
    return () => this.updateCallbacks.delete(callback);
  }

  onStatus(callback: (s: ConnectionStatus) => void): () => void {
    this.statusCallbacks.add(callback);
    callback(this.status);
    return () => this.statusCallbacks.delete(callback);
  }

  async sendAction(action: BattleAction): Promise<void> {
    if (!this.latestUpdate) return;
    const state = this.latestUpdate.state;
    const label =
      action.type === 'move'
        ? `${state.player.active?.species} used ${action.move.name}!`
        : `${state.player.name} switched to ${action.pokemon.species}.`;
    const newLog = [this.mkLog(state.turn, action.type === 'move' ? 'move' : 'switch', label, 'player')];
    this.emit({ ...this.latestUpdate, newLogEntries: newLog, timestamp: Date.now() });
  }

  // ---- internals ----

  private setStatus(s: ConnectionStatus): void {
    this.status = s;
    for (const cb of this.statusCallbacks) cb(s);
  }

  private emit(u: BattleUpdate): void {
    this.latestUpdate = u;
    for (const cb of this.updateCallbacks) cb(u);
  }

  private pushSnapshot(state: BattleState, newLog: LogEntry[]): void {
    this.emit({
      state,
      recommendations: mockRecommendations(state),
      newLogEntries: newLog,
      timestamp: Date.now()
    });
  }

  private mkLog(
    turn: number,
    kind: LogEntry['kind'],
    text: string,
    side?: LogEntry['side']
  ): LogEntry {
    return { id: `${turn}:${++this.logSeq}`, turn, kind, text, side };
  }
}
