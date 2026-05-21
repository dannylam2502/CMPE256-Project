<script lang="ts">
  import { onMount } from 'svelte';
  import { battleStore } from '$lib/stores/battle.svelte';
  import { MockConnector, WebSocketConnector } from '$lib/connectors';
  import type { BattleConnector } from '$lib/connectors';

  import TeamPanel from '$lib/components/TeamPanel.svelte';
  import RecommendationPanel from '$lib/components/RecommendationPanel.svelte';
  import FieldStatus from '$lib/components/FieldStatus.svelte';
  import BattleLog from '$lib/components/BattleLog.svelte';
  import ConnectionIndicator from '$lib/components/ConnectionIndicator.svelte';

  // ---- Connector wiring ------------------------------------------------------
  // To swap in the Python WebSocket backend, change `mode` to 'ws' (or wire it
  // to a UI toggle). The rest of the app does not care which connector is live.

  type Mode = 'mock' | 'ws';
  let mode = $state<Mode>('mock');

  function makeConnector(m: Mode): BattleConnector {
    return m === 'mock'
      ? new MockConnector()
      : new WebSocketConnector({ url: 'ws://localhost:8765' });
  }

  async function switchTo(m: Mode) {
    mode = m;
    await battleStore.setConnector(makeConnector(m));
  }

  onMount(() => {
    void battleStore.setConnector(makeConnector(mode));
  });

  // ---- Action handling -------------------------------------------------------
  function handleSelect(action: import('$lib/types').BattleAction) {
    void battleStore.sendAction(action);
  }
</script>

<div class="app-shell">
  <header class="topbar">
    <div class="brand">
      <span class="brand-mark">◢◣</span>
      <span class="brand-name">BATTLE/REC</span>
      <span class="brand-tag mono">v0.1 · local</span>
    </div>

    <div class="topbar-right">
      <div class="mode-toggle" role="tablist">
        <button
          role="tab"
          aria-selected={mode === 'mock'}
          class:active={mode === 'mock'}
          onclick={() => switchTo('mock')}
        >
          MOCK
        </button>
        <button
          role="tab"
          aria-selected={mode === 'ws'}
          class:active={mode === 'ws'}
          onclick={() => switchTo('ws')}
        >
          PYTHON BOT
        </button>
      </div>
      <ConnectionIndicator status={battleStore.status} lastUpdateAt={battleStore.lastUpdateAt} />
    </div>
  </header>

  {#if battleStore.state}
    <div class="grid">
      <div class="field-bar">
        <FieldStatus
          field={battleStore.state.field}
          turn={battleStore.state.turn}
          format={battleStore.state.format}
        />
      </div>

      <div class="teams">
        <TeamPanel side={battleStore.state.opponent} perspective="opponent" />
        <TeamPanel side={battleStore.state.player} perspective="player" />
      </div>

      <div class="rec">
        <RecommendationPanel
          recommendations={battleStore.recommendations}
          canSubmit={battleStore.canSendActions}
          awaitingResponse={battleStore.awaitingResponse}
          onSelect={handleSelect}
        />
      </div>

      <div class="log">
        <BattleLog entries={battleStore.log} />
      </div>
    </div>
  {:else}
    <div class="loading">
      <span class="mono">// awaiting first snapshot from {battleStore.status.source ?? 'connector'}</span>
    </div>
  {/if}
</div>

<style>
  .app-shell {
    display: flex;
    flex-direction: column;
    min-height: 100vh;
  }

  .topbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 14px 24px;
    border-bottom: 1px solid var(--border-faint);
    background: var(--bg-overlay);
    backdrop-filter: blur(8px);
    position: sticky;
    top: 0;
    z-index: 10;
  }

  .brand {
    display: flex;
    align-items: baseline;
    gap: 12px;
  }
  .brand-mark {
    font-family: var(--font-mono);
    color: var(--accent);
    font-size: 14px;
    letter-spacing: -0.05em;
  }
  .brand-name {
    font-family: var(--font-mono);
    font-weight: 700;
    font-size: 14px;
    letter-spacing: 0.1em;
    color: var(--text-primary);
  }
  .brand-tag {
    font-size: 10px;
    color: var(--text-muted);
    letter-spacing: 0.08em;
  }

  .topbar-right {
    display: flex;
    align-items: center;
    gap: 20px;
  }

  .mode-toggle {
    display: inline-flex;
    border: 1px solid var(--border-faint);
    border-radius: var(--radius-xs);
    overflow: hidden;
  }
  .mode-toggle button {
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.1em;
    padding: 6px 12px;
    border: none;
    border-radius: 0;
    background: transparent;
    color: var(--text-muted);
  }
  .mode-toggle button:not(:last-child) {
    border-right: 1px solid var(--border-faint);
  }
  .mode-toggle button.active {
    background: var(--bg-panel);
    color: var(--accent);
  }
  .mode-toggle button:hover:not(.active) {
    color: var(--text-secondary);
  }

  .grid {
    flex: 1;
    display: grid;
    grid-template-columns: minmax(0, 1.2fr) minmax(380px, 1fr);
    grid-template-rows: auto 1fr auto;
    grid-template-areas:
      "field field"
      "teams rec"
      "log   rec";
    gap: 12px;
    padding: 16px 24px;
    max-width: 1600px;
    width: 100%;
    margin: 0 auto;
  }
  .field-bar { grid-area: field; }
  .teams {
    grid-area: teams;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .rec { grid-area: rec; display: flex; min-height: 0; }
  .rec :global(> *) { flex: 1; }
  .log { grid-area: log; min-height: 200px; max-height: 240px; display: flex; }
  .log :global(> *) { flex: 1; }

  .loading {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-muted);
    font-size: 12px;
    letter-spacing: 0.05em;
  }

  @media (max-width: 1100px) {
    .grid {
      grid-template-columns: 1fr;
      grid-template-areas:
        "field"
        "rec"
        "teams"
        "log";
    }
  }
</style>
