<script lang="ts">
	import { unescapeHtml } from "$lib/utils";

	interface Props {
		value?: string;
	}

	let { value }: Props = $props();
</script>

<div class="annotation-answer">
	{#if value && value.trim()}
		<p class="text-sm text-foreground">
			<span class="text-primary font-medium">A:</span>
			{unescapeHtml(value)}
		</p>
	{:else}
		<p class="text-muted-foreground italic">A: <em>No answer provided</em></p>
	{/if}
</div>
