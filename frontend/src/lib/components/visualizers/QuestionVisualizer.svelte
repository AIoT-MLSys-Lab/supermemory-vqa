<script lang="ts">
	import { unescapeHtml } from "$lib/utils";

	interface Props {
		value?: string;
	}

	let { value }: Props = $props();
</script>

<div class="annotation-question">
	{#if value && value.trim()}
		<p class="text-sm font-medium">
			<span class="text-primary">Q:</span>
			{unescapeHtml(value)}
		</p>
	{:else}
		<p class="text-muted-foreground italic">Q: <em>No question provided</em></p>
	{/if}
</div>
