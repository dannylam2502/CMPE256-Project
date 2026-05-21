<script lang="ts">
  import type { SideState } from '$lib/types';
  import PokemonCard from './PokemonCard.svelte';

  interface Props {
    side: SideState;
    perspective: 'player' | 'opponent';
  }

  let { side, perspective }: Props = $props();

  const revealedCount = $derived(side.team.filter((m) => m.revealed).length);
  const faintedCount = $derived(side.team.filter((m) => m.fainted).length);
</script>

<section class="team-panel">
  <header>
    <div class="title-row">
      <span class="label">{perspective === 'player' ? 'YOUR TEAM' : 'OPPONENT'}</span>
      <span class="name">{side.name}</span>
    </div>
    <div class="stats mono">
      <span>{revealedCount}<span class="muted">/6</span> revealed</span>
      <span class="dot">·</span>
      <span>{6 - faintedCount}<span class="muted">/6</span> standing</span>
    </div>
  </header>

  <div class="grid">
    {#each side.team as mon (mon.species)}
      <PokemonCard {mon} side={perspective} />
    {/each}
  </div>
</section>

<style>
  .team-panel {
    background: var(--bg-overlay);
    border: 1px solid var(--border-faint);
    border-radius: var(--radius-xs);
    padding: 12px;
  }
  header {
    margin-bottom: 12px;
  }
  .title-row {
    display: flex;
    align-items: baseline;
    gap: 10px;
    margin-bottom: 4px;
  }
  .name {
    font-family: var(--font-display);
    font-size: 16px;
    font-weight: 500;
    letter-spacing: -0.01em;
  }
  .stats {
    font-size: 10px;
    color: var(--text-secondary);
    display: flex;
    gap: 6px;
    align-items: center;
  }
  .muted { color: var(--text-muted); }
  .dot { color: var(--text-muted); }
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
  }
  @media (max-width: 900px) {
    .grid { grid-template-columns: 1fr; }
  }
</style>
