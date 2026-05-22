<script lang="ts">
	interface TimeSpan {
		start?: string;
		end?: string;
		video_id?: string;
	}

	interface Props {
		value?: TimeSpan | TimeSpan[];
		onSeek?: (timestamp: string, video_id?: string) => void;
	}

	let { value, onSeek }: Props = $props();

	// Normalize to array
	const spans = $derived(
		Array.isArray(value)
			? value
			: value
				? [value]
				: []
	);

	function handleClick(span: TimeSpan) {
		if (span?.start && onSeek) {
			onSeek(span.start, span.video_id);
		}
	}
</script>

<div class="question-time-span-visualizer flex flex-wrap gap-1">
	{#if spans.length > 0}
		{#each spans as span, i}
			{@const isClickable = !!span?.start && !!onSeek}
			<button
				type="button"
				class="inline-flex items-center gap-1 bg-secondary px-2 py-1 rounded text-foreground hover:bg-primary/10 hover:text-primary transition-colors"
				class:cursor-pointer={isClickable}
				class:underline={isClickable}
				onclick={() => handleClick(span)}
				title={isClickable ? `Click to seek to question time${spans.length > 1 ? ` (${i + 1}/${spans.length})` : ''}` : 'When this question might be asked'}
			>
				<span>❓</span>
				<span>{span.start || '??:??'}</span>
				<span>-</span>
				<span>{span.end || '??:??'}</span>
				{#if span.video_id}
					<span class="text-[10px] ml-1 bg-background/50 px-1 rounded truncate max-w-[100px]" title={span.video_id}>
						{span.video_id}
					</span>
				{/if}
			</button>
		{/each}
	{:else}
		<span class="text-muted-foreground italic">❓ No question time specified</span>
	{/if}
</div>
