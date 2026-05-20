import type { BattleAction, BattleUpdate, ConnectionStatus } from '../types';
import type { BattleConnector } from './connector';

/**
 * WebSocketConnector — connects to the Python recommender bot.
 *
 * Wire format (snapshots, JSON):
 *
 *   Server → Client:
 *     { "type": "update",  "payload": <BattleUpdate> }
 *     { "type": "status",  "payload": <ConnectionStatus> }
 *     { "type": "error",   "payload": { "message": string } }
 *
 *   Client → Server:
 *     { "type": "action",  "payload": <BattleAction> }
 *     { "type": "ping" }
 *
 * The Python side just needs to JSON-serialize the same field names used in
 * `types.ts` and `ws.send_text(json.dumps({"type": "update", "payload": ...}))`.
 *
 * Notes:
 *  - Auto-reconnects with exponential backoff (capped).
 *  - Emits latest snapshot to new subscribers (good for hot reload during dev).
 *  - sendAction is exposed only if the connection has been established at least
 *    once; UI can probe `connector.sendAction !== undefined` to render controls.
 */

export interface WebSocketConnectorOptions {
  url?: string;
  name?: string;
  /** Initial reconnect delay in ms. Doubles on each failure, capped at 30s. */
  reconnectDelayMs?: number;
  /** Set false to disable automatic reconnects. */
  autoReconnect?: boolean;
}

export class WebSocketConnector implements BattleConnector {
  readonly name: string;
  private url: string;
  private autoReconnect: boolean;
  private baseDelay: number;

  private ws: WebSocket | null = null;
  private shouldRun = false;
  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  private updateCallbacks = new Set<(u: BattleUpdate) => void>();
  private statusCallbacks = new Set<(s: ConnectionStatus) => void>();
  private status: ConnectionStatus = { state: 'disconnected' };
  private latestUpdate: BattleUpdate | null = null;

  constructor(opts: WebSocketConnectorOptions = {}) {
    this.url = opts.url ?? 'ws://localhost:8765';
    this.name = opts.name ?? 'python-bot';
    this.autoReconnect = opts.autoReconnect ?? true;
    this.baseDelay = opts.reconnectDelayMs ?? 1000;
    this.status.source = this.name;
  }

  async connect(): Promise<void> {
    this.shouldRun = true;
    this.openSocket();
    // Resolve as soon as we either connect or fail once — the caller doesn't
    // need to await every reconnect attempt.
    await new Promise<void>((resolve) => {
      const off = this.onStatus((s) => {
        if (s.state === 'connected' || s.state === 'error') {
          off();
          resolve();
        }
      });
    });
  }

  async disconnect(): Promise<void> {
    this.shouldRun = false;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    if (this.ws && this.ws.readyState <= WebSocket.OPEN) {
      this.ws.close(1000, 'client disconnect');
    }
    this.ws = null;
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
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new Error('Not connected');
    }
    this.ws.send(JSON.stringify({ type: 'action', payload: serializeAction(action) }));
  }

  // ---- internals ----

  private openSocket(): void {
    this.setStatus({ state: 'connecting', source: this.name });
    try {
      this.ws = new WebSocket(this.url);
    } catch (err) {
      this.setStatus({ state: 'error', source: this.name, message: String(err) });
      this.scheduleReconnect();
      return;
    }

    this.ws.addEventListener('open', () => {
      this.reconnectAttempt = 0;
      this.setStatus({ state: 'connected', source: this.name, message: this.url });
    });

    this.ws.addEventListener('message', (evt) => {
      try {
        const parsed = JSON.parse(evt.data);
        if (parsed?.type === 'update' && parsed.payload) {
          const update = parsed.payload as BattleUpdate;
          this.latestUpdate = update;
          for (const cb of this.updateCallbacks) cb(update);
        } else if (parsed?.type === 'status' && parsed.payload) {
          this.setStatus({ ...parsed.payload, source: this.name });
        } else if (parsed?.type === 'error' && parsed.payload) {
          this.setStatus({ state: 'error', source: this.name, message: parsed.payload.message });
        }
      } catch (err) {
        console.error('[ws] failed to parse message', err);
      }
    });

    this.ws.addEventListener('error', () => {
      this.setStatus({ state: 'error', source: this.name, message: `Failed to reach ${this.url}` });
    });

    this.ws.addEventListener('close', () => {
      this.ws = null;
      if (this.shouldRun && this.autoReconnect) {
        this.scheduleReconnect();
      } else {
        this.setStatus({ state: 'disconnected', source: this.name });
      }
    });
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    const delay = Math.min(30_000, this.baseDelay * 2 ** this.reconnectAttempt);
    this.reconnectAttempt += 1;
    this.reconnectTimer = setTimeout(() => {
      if (this.shouldRun) this.openSocket();
    }, delay);
  }

  private setStatus(s: ConnectionStatus): void {
    this.status = s;
    for (const cb of this.statusCallbacks) cb(s);
  }
}

function serializeAction(action: BattleAction) {
  if (action.type === 'move') {
    return { type: 'move', moveId: action.move.id, terastallize: action.terastallize ?? false };
  }
  return { type: 'switch', species: action.pokemon.species };
}
