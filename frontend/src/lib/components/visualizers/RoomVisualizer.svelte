<script lang="ts">
	interface Props {
		value?: string;
	}

	let { value }: Props = $props();
</script>

<div class="room-visualizer">
	{#if value && value.trim()}
		<span class="bg-secondary px-2 py-1 rounded text-foreground">📍 {value}</span>
	{:else}
		<span class="text-muted-foreground italic">📍 No room specified</span>
	{/if}
</div>
