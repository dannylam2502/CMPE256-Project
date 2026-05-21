<script lang="ts">
  import type { LogEntry } from '$lib/types';
  import { tick } from 'svelte';

  interface Props {
    entries: LogEntry[];
  }

  let { entries }: Props = $props();
  let listEl: HTMLDivElement;

  $effect(() => {
    // Auto-scroll to bottom on new entry.
    void entries.length;
    tick().then(() => {
      if (listEl) listEl.scrollTop = listEl.scrollHeight;
    });
  });

  function kindColor(kind: LogEntry['kind']): string {
    switch (kind) {
      case 'turn': return 'var(--accent)';
      case 'faint': return 'var(--danger)';
      case 'damage': return 'var(--hp-low)';
      case 'heal': return 'var(--hp-good)';
      case 'status': return 'var(--warning)';
      case 'field': return 'var(--info)';
      default: return 'var(--text-secondary)';
    }
  }
</script>

<section class="log">
  <header>
    <span class="label">BATTLE LOG</span>
    <span class="count mono">{entries.length} events</span>
  </header>
  <div class="entries" bind:this={listEl}>
    {#if entries.length === 0}
      <div class="empty mono">// log empty</div>
    {:else}
      {#each entries as entry (entry.id)}
        <div class="entry">
          <span class="kind mono" style="color: {kindColor(entry.kind)}">
            {entry.kind.toUpperCase().padEnd(6)}
          </span>
          <span class="text">{entry.text}</span>
        </div>
      {/each}
    {/if}
  </div>
</section>

<style>
  .log {
    background: var(--bg-overlay);
    border: 1px solid var(--border-faint);
    border-radius: var(--radius-xs);
    padding: 12px;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 8px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border-faint);
  }
  .count { font-size: 10px; color: var(--text-muted); }
  .entries {
    flex: 1;
    overflow-y: auto;
    font-family: var(--font-mono);
    font-size: 11px;
    line-height: 1.6;
  }
  .empty {
    color: var(--text-faded);
    font-size: 11px;
    text-align: center;
    padding: 24px 0;
  }
  .entry {
    display: flex;
    gap: 10px;
    padding: 2px 0;
  }
  .kind {
    font-size: 9px;
    letter-spacing: 0.08em;
    white-space: pre;
    flex-shrink: 0;
  }
  .text {
    color: var(--text-secondary);
  }
</style>
