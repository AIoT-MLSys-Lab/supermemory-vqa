<script lang="ts">
	interface TimeSpan {
		start?: string;
		end?: string;
	}

	interface Props {
		value?: TimeSpan;
		videoPath?: string;
		currentVideoPath?: string;
		onSeek?: (timestamp: string) => void;
	}

	let { value, videoPath, currentVideoPath, onSeek }: Props = $props();

	function handleClick() {
		if (value?.start && onSeek) {
			onSeek(value.start);
		}
	}

	const isClickable = $derived(!!value?.start && !!onSeek);
	const isDifferentVideo = $derived(videoPath && currentVideoPath && videoPath !== currentVideoPath);

	// Get display name from video path
	function getVideoDisplayName(path?: string): string {
		if (!path) return '';
		const parts = path.split('/');
		return parts[parts.length - 1] || path;
	}
</script>

<div class="time-span-visualizer">
	{#if value && (value.start || value.end)}
		<button
			type="button"
			class="inline-flex items-center gap-1 bg-secondary px-2 py-1 rounded text-foreground hover:bg-primary/10 hover:text-primary transition-colors"
			class:cursor-pointer={isClickable}
			class:underline={isClickable}
			onclick={handleClick}
			title={isClickable ? 'Click to seek to start time' : undefined}
		>
			<span>⏱️</span>
			<span>{value.start || '??:??'}</span>
			<span>-</span>
			<span>{value.end || '??:??'}</span>
			{#if isDifferentVideo}
				<span class="text-primary text-xs ml-1" title={videoPath}>
					📹 {getVideoDisplayName(videoPath)}
				</span>
			{/if}
		</button>
	{:else}
		<span class="text-muted-foreground italic">⏱️ No time specified</span>
	{/if}
</div>
