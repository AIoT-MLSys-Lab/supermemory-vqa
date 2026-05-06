<script lang="ts">
	import { Chip } from "$lib/components/app/ui";

	interface Props {
		value?: string[];
	}

	let { value }: Props = $props();
</script>

<div class="modalities-visualizer flex flex-wrap gap-1">
	{#if value && value.length > 0}
		{#each value as modality}
			<Chip value={modality} kind="modality" />
		{/each}
	{:else}
		<span class="text-muted-foreground italic text-sm">No modalities</span>
	{/if}
</div>
