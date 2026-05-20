import type {
  BattleAction,
  BattleState,
  ConnectionStatus,
  LogEntry,
  Recommendation
} from '../types';
import type { BattleConnector } from '../connectors/connector';

/**
 * battleStore — the single source of UI truth.
 *
 * Owns the active connector, the latest battle snapshot, recommendations,
 * accumulated log, and connection status. Components subscribe via the
 * exported getters (Svelte 5 runes thread reactivity automatically).
 *
 * Swap connector at runtime with `setConnector(new MyConnector())` — the
 * store handles teardown of the old one.
 */
function createBattleStore() {
  let connector = $state<BattleConnector | null>(null);
  let battleState = $state<BattleState | null>(null);
  let recommendations = $state<Recommendation[]>([]);
  let status = $state<ConnectionStatus>({ state: 'disconnected' });
  let log = $state<LogEntry[]>([]);
  let lastUpdateAt = $state<number | null>(null);
  let awaitingResponse = $state(false);

  let unsubUpdate: (() => void) | null = null;
  let unsubStatus: (() => void) | null = null;

  async function setConnector(next: BattleConnector): Promise<void> {
    // Tear down the previous one.
    if (unsubUpdate) unsubUpdate();
    if (unsubStatus) unsubStatus();
    if (connector) await connector.disconnect().catch(() => {});

    connector = next;
    battleState = null;
    recommendations = [];
    log = [];
    lastUpdateAt = null;
    awaitingResponse = false;

    unsubStatus = next.onStatus((s) => {
      status = s;
    });
    unsubUpdate = next.onUpdate((u) => {
      battleState = u.state;
      recommendations = u.recommendations;
      lastUpdateAt = u.timestamp;
      // Any new update clears the "awaiting" flag — the bot has moved on.
      awaitingResponse = false;
      if (u.newLogEntries && u.newLogEntries.length > 0) {
        log = [...log, ...u.newLogEntries];
      }
    });

    await next.connect();
  }

  async function sendAction(action: BattleAction): Promise<void> {
    if (connector?.sendAction) {
      awaitingResponse = true;
      try {
        await connector.sendAction(action);
      } catch (err) {
        awaitingResponse = false;
        throw err;
      }
    }
  }

  function clearLog(): void {
    log = [];
  }

  return {
    get connector() { return connector; },
    get state() { return battleState; },
    get recommendations() { return recommendations; },
    get status() { return status; },
    get log() { return log; },
    get lastUpdateAt() { return lastUpdateAt; },
    get awaitingResponse() { return awaitingResponse; },
    get canSendActions() { return connector?.sendAction !== undefined; },
    setConnector,
    sendAction,
    clearLog
  };
}

export const battleStore = createBattleStore();
