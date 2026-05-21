import type { BattleAction, BattleUpdate, ConnectionStatus } from '../types';

/**
 * BattleConnector — the contract between the UI and any recommender backend.
 *
 * To plug in a new backend (Python WebSocket, HTTP polling, local JS, replay
 * playback, etc.) implement this interface and pass an instance into the
 * battle store via `setConnector()`. The UI is completely agnostic to where
 * battle state and recommendations come from.
 *
 * Design notes:
 *  - Snapshots over deltas: every `BattleUpdate` carries the full BattleState.
 *    Simpler protocol, simpler reconnect, simpler debugging.
 *  - Push, don't pull: the connector decides when to emit. Recommendations
 *    typically arrive once per turn from the Python side.
 *  - `sendAction` is optional. A pure-observer connector (e.g. watching a
 *    bot play itself) can leave it undefined and the UI will hide controls.
 */
export interface BattleConnector {
  /** Human-readable identifier shown in the connection indicator. */
  readonly name: string;

  /** Open the connection. Resolves once the connector reaches `connected`. */
  connect(): Promise<void>;

  /** Close the connection and release resources. Safe to call multiple times. */
  disconnect(): Promise<void>;

  /**
   * Subscribe to battle updates. Returns an unsubscribe function.
   * The connector may immediately invoke the callback with the latest snapshot.
   */
  onUpdate(callback: (update: BattleUpdate) => void): () => void;

  /**
   * Subscribe to connection-status changes. Returns an unsubscribe function.
   * Should always fire at least once on subscribe with current status.
   */
  onStatus(callback: (status: ConnectionStatus) => void): () => void;

  /**
   * Optional: submit an action chosen by the user. Only implement this when
   * the backend supports human-in-the-loop control. If undefined, the UI
   * renders as observer-only.
   */
  sendAction?(action: BattleAction): Promise<void>;
}
