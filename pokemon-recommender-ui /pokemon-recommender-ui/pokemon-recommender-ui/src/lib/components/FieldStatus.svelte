<script lang="ts">
  import type { FieldState } from '$lib/types';

  interface Props {
    field: FieldState;
    turn: number;
    format: string;
  }

  let { field, turn, format }: Props = $props();

  const weatherLabel = $derived.by(() => {
    if (!field.weather) return null;
    const map: Record<string, string> = { sun: 'Harsh sunlight', rain: 'Rain', sand: 'Sandstorm', snow: 'Snow', hail: 'Hail' };
    return map[field.weather] ?? field.weather;
  });
  const terrainLabel = $derived.by(() => {
    if (!field.terrain) return null;
    return `${field.terrain[0].toUpperCase() + field.terrain.slice(1)} terrain`;
  });

  const hazardName: Record<string, string> = {
    stealthrock: 'SR',
    spikes: 'Spikes',
    toxicspikes: 'T-Spikes',
    stickyweb: 'Web'
  };
</script>

<div class="field">
  <div class="left">
    <div class="turn-block">
      <span class="label">TURN</span>
      <span class="turn-num mono">{String(turn).padStart(2, '0')}</span>
    </div>
    <span class="format-chip mono">{format}</span>
  </div>

  <div class="conditions">
    {#if weatherLabel}
      <span class="condition">
        <span class="label">WEATHER</span>
        <span>{weatherLabel}{field.weatherTurnsLeft != null ? ` · ${field.weatherTurnsLeft}t` : ''}</span>
      </span>
    {/if}
    {#if terrainLabel}
      <span class="condition">
        <span class="label">TERRAIN</span>
        <span>{terrainLabel}{field.terrainTurnsLeft != null ? ` · ${field.terrainTurnsLeft}t` : ''}</span>
      </span>
    {/if}
    {#if field.trickRoom}
      <span class="condition">
        <span class="label">ROOM</span>
        <span>Trick Room</span>
      </span>
    {/if}
  </div>

  <div class="hazards">
    <div class="hazard-side">
      <span class="label">YOUR SIDE</span>
      <div class="hazard-list">
        {#each field.player.hazards as h}
          <span class="hazard">{hazardName[h] ?? h}</span>
        {/each}
        {#if field.player.hazards.length === 0}<span class="hazard empty">—</span>{/if}
      </div>
    </div>
    <div class="hazard-side">
      <span class="label">FOE SIDE</span>
      <div class="hazard-list">
        {#each field.opponent.hazards as h}
          <span class="hazard danger">{hazardName[h] ?? h}{h === 'spikes' && field.opponent.spikesLayers ? ` ×${field.opponent.spikesLayers}` : ''}</span>
        {/each}
        {#if field.opponent.hazards.length === 0}<span class="hazard empty">—</span>{/if}
      </div>
    </div>
  </div>
</div>

<style>
  .field {
    background: var(--bg-overlay);
    border: 1px solid var(--border-faint);
    border-radius: var(--radius-xs);
    padding: 12px 14px;
    display: grid;
    grid-template-columns: auto 1fr auto;
    gap: 24px;
    align-items: center;
  }
  .left { display: flex; align-items: center; gap: 14px; }
  .turn-block { display: flex; flex-direction: column; gap: 2px; }
  .turn-num {
    font-size: 24px;
    font-weight: 500;
    line-height: 1;
    color: var(--text-primary);
    letter-spacing: -0.02em;
  }
  .format-chip {
    font-size: 10px;
    color: var(--text-secondary);
    background: var(--bg-panel);
    padding: 4px 8px;
    border: 1px solid var(--border-faint);
    border-radius: 1px;
    letter-spacing: 0.04em;
  }
  .conditions {
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
  }
  .condition {
    display: flex;
    flex-direction: column;
    gap: 2px;
    font-size: 13px;
    color: var(--text-primary);
  }
  .hazards {
    display: flex;
    gap: 16px;
  }
  .hazard-side {
    display: flex;
    flex-direction: column;
    gap: 4px;
    align-items: flex-end;
  }
  .hazard-list { display: flex; gap: 4px; }
  .hazard {
    font-family: var(--font-mono);
    font-size: 10px;
    background: var(--bg-panel);
    border: 1px solid var(--border-soft);
    padding: 2px 6px;
    color: var(--text-secondary);
    border-radius: 1px;
  }
  .hazard.danger { color: var(--warning); border-color: rgba(245, 179, 66, 0.3); }
  .hazard.empty { color: var(--text-faded); border-color: transparent; }
</style>
