<script lang="ts">
  import type { PokemonType } from '$lib/types';
  import { TYPE_COLORS } from '$lib/data/typeColors';

  interface Props {
    type: PokemonType;
    size?: 'sm' | 'md';
  }

  let { type, size = 'md' }: Props = $props();
</script>

<span class="badge" class:sm={size === 'sm'} style="--type-color: {TYPE_COLORS[type]}">
  {type}
</span>

<style>
  .badge {
    display: inline-flex;
    align-items: center;
    background: var(--type-color);
    color: rgba(0, 0, 0, 0.85);
    font-family: var(--font-mono);
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 2px 6px;
    border-radius: 1px;
    line-height: 1;
    white-space: nowrap;
  }
  .badge.sm {
    font-size: 9px;
    padding: 1px 4px;
  }
</style>
