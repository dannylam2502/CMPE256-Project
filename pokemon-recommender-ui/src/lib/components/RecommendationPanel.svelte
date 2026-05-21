<script lang="ts">
  import type { Recommendation, BattleAction } from '$lib/types';
  import { actionKey } from '$lib/types';
  import TypeBadge from './TypeBadge.svelte';

  interface Props {
    recommendations: Recommendation[];
    canSubmit: boolean;
    awaitingResponse?: boolean;
    onSelect?: (action: BattleAction) => void;
  }

  let { recommendations, canSubmit, awaitingResponse = false, onSelect }: Props = $props();

  function categoryGlyph(cat: 'physical' | 'special' | 'status'): string {
    if (cat === 'physical') return '◆';
    if (cat === 'special') return '◇';
    return '○';
  }

  function formatScore(score: number): string {
    return (score * 100).toFixed(1);
  }

  function handle(action: BattleAction) {
    if (!canSubmit || awaitingResponse) return;
    onSelect?.(action);
  }

  const top = $derived(recommendations[0] ?? null);
  const rest = $derived(recommendations.slice(1));
</script>

<aside class="rec-panel" class:awaiting={awaitingResponse}>
  <header>
    <span class="label">AI RECOMMENDATION</span>
    {#if rest.length > 0}
      <span class="mono count">{rest.length} other option{rest.length === 1 ? '' : 's'}</span>
    {/if}
  </header>

  {#if !top}
    <div class="empty">
      <span class="mono">awaiting battle state</span>
    </div>
  {:else}
    <!-- AI suggestion: big, highlighted -->
    <div class="top-pick">
      <div class="top-head">
        {#if top.action.type === 'move'}
          <div class="action-title">
            <span class="action-name">{top.action.move.name}</span>
            <div class="action-meta">
              <TypeBadge type={top.action.move.type} size="sm" />
              <span class="mono glyph" title={top.action.move.category}>
                {categoryGlyph(top.action.move.category)}
              </span>
              <span class="mono stat">
                {top.action.move.basePower > 0 ? `${top.action.move.basePower} BP` : '—'}
              </span>
              <span class="mono stat-dim">
                {top.action.move.pp.current}/{top.action.move.pp.max} pp
              </span>
            </div>
          </div>
        {:else}
          <div class="action-title">
            <span class="action-name">
              <span class="switch-arrow">→</span>
              Switch to {top.action.pokemon.species}
            </span>
            <div class="action-meta">
              {#each top.action.pokemon.types as t}
                <TypeBadge type={t} size="sm" />
              {/each}
            </div>
          </div>
        {/if}
      </div>

      {#if top.reasoning}
        <p class="reason">{top.reasoning}</p>
      {/if}

      <div class="confidence">
        <div class="conf-track">
          <div class="conf-fill" style="width: {top.score * 100}%"></div>
        </div>
        <span class="mono conf-val">
          {formatScore(top.score)}<span class="muted">%</span>
        </span>
      </div>

      {#if canSubmit}
        <button
          class="accept-btn"
          onclick={() => handle(top.action)}
          disabled={awaitingResponse}
        >
          {awaitingResponse ? 'WAITING…' : 'ACCEPT RECOMMENDATION'}
        </button>
      {/if}
    </div>

    {#if rest.length > 0}
      <div class="override">
        <div class="override-label">
          <span class="label">OR PICK YOUR OWN</span>
        </div>
        <ul class="override-list">
          {#each rest as rec, i (actionKey(rec.action))}
            <li class="override-row">
              <div class="orow-body">
                {#if rec.action.type === 'move'}
                  <div class="orow-head">
                    <span class="orow-name">{rec.action.move.name}</span>
                    <div class="orow-meta">
                      <TypeBadge type={rec.action.move.type} size="sm" />
                      <span class="mono glyph">{categoryGlyph(rec.action.move.category)}</span>
                      <span class="mono stat">
                        {rec.action.move.basePower > 0 ? `${rec.action.move.basePower}` : '—'}
                      </span>
                    </div>
                  </div>
                {:else}
                  <div class="orow-head">
                    <span class="orow-name">
                      <span class="switch-arrow">→</span>
                      {rec.action.pokemon.species}
                    </span>
                    <div class="orow-meta">
                      {#each rec.action.pokemon.types as t}
                        <TypeBadge type={t} size="sm" />
                      {/each}
                    </div>
                  </div>
                {/if}
                <div class="orow-score">
                  <div class="orow-track">
                    <div class="orow-fill" style="width: {rec.score * 100}%"></div>
                  </div>
                  <span class="mono orow-val">{formatScore(rec.score)}<span class="muted">%</span></span>
                </div>
              </div>
              {#if canSubmit}
                <button
                  class="use-btn"
                  onclick={() => handle(rec.action)}
                  disabled={awaitingResponse}
                  aria-label="Use this action instead"
                >
                  USE
                </button>
              {/if}
            </li>
          {/each}
        </ul>
      </div>
    {/if}
  {/if}
</aside>

<style>
  .rec-panel {
    background: var(--bg-overlay);
    border: 1px solid var(--border-faint);
    border-radius: var(--radius-xs);
    padding: 14px;
    display: flex;
    flex-direction: column;
    min-height: 0;
    transition: opacity 200ms ease;
  }
  .rec-panel.awaiting {
    opacity: 0.7;
  }

  header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 12px;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--border-faint);
  }
  .count { font-size: 10px; color: var(--text-muted); }

  .empty {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-muted);
    font-size: 11px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }

  /* ---- Top pick (the AI recommendation) ---- */
  .top-pick {
    background: linear-gradient(180deg, rgba(196, 242, 85, 0.08), rgba(196, 242, 85, 0.02));
    border: 1px solid var(--accent-dim);
    border-left: 3px solid var(--accent);
    border-radius: var(--radius-xs);
    padding: 14px;
    margin-bottom: 14px;
  }
  .top-head { margin-bottom: 8px; }
  .action-title {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }
  .action-name {
    font-family: var(--font-display);
    font-size: 18px;
    font-weight: 500;
    letter-spacing: -0.01em;
    color: var(--text-primary);
  }
  .switch-arrow { color: var(--accent); margin-right: 4px; }
  .action-meta {
    display: flex;
    gap: 6px;
    align-items: center;
  }
  .glyph { font-size: 13px; color: var(--text-secondary); }
  .stat { font-size: 11px; color: var(--text-secondary); letter-spacing: 0.04em; }
  .stat-dim { font-size: 11px; color: var(--text-muted); }
  .reason {
    margin: 6px 0 12px;
    font-size: 12px;
    line-height: 1.5;
    color: var(--text-secondary);
  }
  .confidence {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 12px;
  }
  .conf-track {
    flex: 1;
    height: 4px;
    background: var(--bg-overlay);
    border: 1px solid var(--border-faint);
    border-radius: 1px;
    overflow: hidden;
  }
  .conf-fill {
    height: 100%;
    background: var(--accent);
    transition: width 400ms cubic-bezier(0.2, 0.8, 0.2, 1);
  }
  .conf-val {
    font-size: 12px;
    color: var(--accent);
    min-width: 55px;
    text-align: right;
  }
  .muted { color: var(--text-muted); }

  .accept-btn {
    width: 100%;
    padding: 10px;
    font-family: var(--font-mono);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.12em;
    background: var(--accent);
    color: var(--accent-text);
    border: 1px solid var(--accent);
    border-radius: var(--radius-xs);
    cursor: pointer;
    transition: background 120ms ease, transform 80ms ease;
  }
  .accept-btn:hover:not(:disabled) {
    background: #d8ff7a;
  }
  .accept-btn:active:not(:disabled) {
    transform: translateY(1px);
  }
  .accept-btn:disabled {
    background: var(--bg-elev);
    color: var(--text-muted);
    border-color: var(--border-soft);
    cursor: not-allowed;
  }

  /* ---- Override list ---- */
  .override { flex: 1; min-height: 0; display: flex; flex-direction: column; }
  .override-label {
    margin-bottom: 8px;
  }
  .override-list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 3px;
    overflow-y: auto;
  }
  .override-row {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 10px;
    align-items: center;
    padding: 8px 10px;
    background: var(--bg-panel);
    border: 1px solid var(--border-faint);
    border-radius: var(--radius-xs);
    transition: border-color 120ms ease, background 120ms ease;
  }
  .override-row:hover {
    border-color: var(--border-soft);
    background: var(--bg-panel-2);
  }
  .orow-body {
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 5px;
  }
  .orow-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
  }
  .orow-name {
    font-size: 13px;
    color: var(--text-primary);
    letter-spacing: -0.005em;
  }
  .orow-meta {
    display: flex;
    align-items: center;
    gap: 5px;
  }
  .orow-score {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .orow-track {
    flex: 1;
    height: 2px;
    background: var(--bg-overlay);
    border: 1px solid var(--border-faint);
    border-radius: 1px;
    overflow: hidden;
  }
  .orow-fill {
    height: 100%;
    background: var(--text-muted);
    transition: width 350ms ease;
  }
  .orow-val {
    font-size: 10px;
    color: var(--text-secondary);
    min-width: 44px;
    text-align: right;
  }

  .use-btn {
    padding: 6px 10px;
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.08em;
    background: transparent;
    color: var(--text-secondary);
    border: 1px solid var(--border-soft);
    border-radius: var(--radius-xs);
    cursor: pointer;
    transition: all 120ms ease;
  }
  .use-btn:hover:not(:disabled) {
    color: var(--text-primary);
    border-color: var(--border-strong);
    background: var(--bg-elev);
  }
  .use-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
</style>
