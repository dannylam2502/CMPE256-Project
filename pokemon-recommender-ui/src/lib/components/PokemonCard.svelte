<script lang="ts">
  import type { PokemonState } from '$lib/types';
  import { STATUS_LABELS } from '$lib/data/typeColors';
  import TypeBadge from './TypeBadge.svelte';

  interface Props {
    mon: PokemonState;
    side: 'player' | 'opponent';
    compact?: boolean;
  }

  let { mon, side, compact = false }: Props = $props();

  const hpPct = $derived(Math.round(mon.hp.fraction * 100));
  const hpColor = $derived(
    hpPct > 50 ? 'var(--hp-good)' : hpPct > 20 ? 'var(--hp-mid)' : 'var(--hp-low)'
  );
  const showActualHp = $derived(side === 'player' && mon.hp.max > 1);
</script>

<div
  class="card"
  class:active={mon.isActive}
  class:fainted={mon.fainted}
  class:unrevealed={!mon.revealed}
  class:compact
>
  <div class="header">
    <div class="species">
      {#if !mon.revealed}
        <span class="unknown">???</span>
      {:else}
        {mon.species}
      {/if}
    </div>
    {#if mon.isActive}
      <span class="active-dot" aria-label="active"></span>
    {/if}
  </div>

  {#if mon.revealed}
    <div class="types">
      {#each mon.types as type}
        <TypeBadge {type} size="sm" />
      {/each}
    </div>

    <div class="hp-row">
      <div class="hp-track">
        <div class="hp-fill" style="width: {hpPct}%; background: {hpColor};"></div>
      </div>
      <div class="hp-text mono">
        {#if showActualHp}
          {mon.hp.current}<span class="muted">/{mon.hp.max}</span>
        {:else}
          {hpPct}<span class="muted">%</span>
        {/if}
      </div>
    </div>

    {#if mon.status !== 'healthy' && STATUS_LABELS[mon.status]}
      <span class="status-pill" style="--status-color: {STATUS_LABELS[mon.status].color};">
        {STATUS_LABELS[mon.status].label}
      </span>
    {/if}

    {#if side === 'player' && mon.item}
      <div class="meta mono">{mon.item}</div>
    {/if}
  {/if}
</div>

<style>
  .card {
    background: var(--bg-panel);
    border: 1px solid var(--border-faint);
    border-radius: var(--radius-xs);
    padding: 10px 12px;
    position: relative;
    transition: border-color 150ms ease, background 150ms ease;
  }
  .card.active {
    background: var(--bg-panel-2);
    border-color: var(--accent-dim);
    box-shadow: inset 2px 0 0 var(--accent);
  }
  .card.fainted {
    opacity: 0.35;
    filter: grayscale(0.8);
  }
  .card.unrevealed {
    background: repeating-linear-gradient(
      45deg,
      var(--bg-panel),
      var(--bg-panel) 6px,
      transparent 6px,
      transparent 12px
    );
    background-color: var(--bg-overlay);
  }
  .card.compact { padding: 6px 8px; }

  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
  }
  .species {
    font-weight: 500;
    font-size: 13px;
    letter-spacing: -0.01em;
  }
  .unknown {
    color: var(--text-muted);
    font-family: var(--font-mono);
  }
  .active-dot {
    width: 6px;
    height: 6px;
    background: var(--accent);
    border-radius: 50%;
    box-shadow: 0 0 8px var(--accent);
  }
  .types {
    display: flex;
    gap: 3px;
    margin-bottom: 8px;
  }
  .hp-row {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .hp-track {
    flex: 1;
    height: 4px;
    background: var(--bg-overlay);
    border-radius: 2px;
    overflow: hidden;
    border: 1px solid var(--border-faint);
  }
  .hp-fill {
    height: 100%;
    transition: width 300ms ease, background 300ms ease;
  }
  .hp-text {
    font-size: 11px;
    color: var(--text-primary);
    min-width: 44px;
    text-align: right;
  }
  .muted { color: var(--text-muted); }
  .status-pill {
    display: inline-block;
    margin-top: 6px;
    font-family: var(--font-mono);
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.1em;
    padding: 1px 5px;
    background: var(--status-color);
    color: var(--bg-base);
    border-radius: 1px;
  }
  .meta {
    margin-top: 6px;
    font-size: 10px;
    color: var(--text-muted);
    letter-spacing: 0.02em;
  }
</style>
