<script lang="ts">
  import type { ConnectionStatus } from '$lib/types';

  interface Props {
    status: ConnectionStatus;
    lastUpdateAt: number | null;
  }

  let { status, lastUpdateAt }: Props = $props();

  let now = $state(Date.now());
  $effect(() => {
    const id = setInterval(() => (now = Date.now()), 1000);
    return () => clearInterval(id);
  });

  const sinceUpdate = $derived(lastUpdateAt ? Math.floor((now - lastUpdateAt) / 1000) : null);

  const dotColor = $derived.by(() => {
    switch (status.state) {
      case 'connected': return 'var(--accent)';
      case 'connecting': return 'var(--warning)';
      case 'error': return 'var(--danger)';
      default: return 'var(--text-muted)';
    }
  });
</script>

<div class="indicator">
  <span class="dot" style="background: {dotColor}; box-shadow: 0 0 6px {dotColor};"
    class:pulse={status.state === 'connecting'}></span>
  <span class="state mono">{status.state.toUpperCase()}</span>
  {#if status.source}
    <span class="source mono">{status.source}</span>
  {/if}
  {#if sinceUpdate !== null && status.state === 'connected'}
    <span class="age mono">+{sinceUpdate}s</span>
  {/if}
  {#if status.message}
    <span class="msg">— {status.message}</span>
  {/if}
</div>

<style>
  .indicator {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: 10px;
    color: var(--text-secondary);
    letter-spacing: 0.05em;
  }
  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
  }
  .pulse { animation: pulse 1.2s ease-in-out infinite; }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
  }
  .state { color: var(--text-primary); font-weight: 500; letter-spacing: 0.08em; }
  .source { color: var(--text-muted); }
  .age { color: var(--text-muted); }
  .msg { color: var(--text-muted); font-family: var(--font-mono); }
</style>
