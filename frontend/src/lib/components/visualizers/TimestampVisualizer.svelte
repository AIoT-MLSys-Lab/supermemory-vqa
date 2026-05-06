<script lang="ts">
	/**
	 * TimestampVisualizer
	 *
	 * Visualizes a single timestamp (MM:SS format) as a clickable button.
	 * This is a simpler version of TimeSpanVisualizer for single time points.
	 * Used for: BoundingBox timestamps, single time markers, etc.
	 */

	interface Props {
		value?: string; // MM:SS format
		videoPath?: string;
		currentVideoPath?: string;
		onSeek?: (timestamp: string) => void;
	}

	let { value, videoPath, currentVideoPath, onSeek }: Props = $props();

	function handleClick() {
		if (value && onSeek) {
			onSeek(value);
		}
	}

	const isClickable = $derived(!!value && !!onSeek);
	const isDifferentVideo = $derived(videoPath && currentVideoPath && videoPath !== currentVideoPath);

	// Get display name from video path
	function getVideoDisplayName(path?: string): string {
		if (!path) return '';
		const parts = path.split('/');
		return parts[parts.length - 1] || path;
	}
</script>

<div class="timestamp-visualizer">
	{#if value}
		<button
			type="button"
			class="inline-flex items-center gap-1 bg-secondary px-2 py-1 rounded text-foreground hover:bg-primary/10 hover:text-primary transition-colors"
			class:cursor-pointer={isClickable}
			class:underline={isClickable}
			onclick={handleClick}
			title={isClickable ? 'Click to seek to this time' : undefined}
		>
			<span>📍</span>
			<span>{value}</span>
			{#if isDifferentVideo}
				<span class="text-primary text-xs ml-1" title={videoPath}>
					📹 {getVideoDisplayName(videoPath)}
				</span>
			{/if}
		</button>
	{:else}
		<span class="text-muted-foreground italic">📍 No time specified</span>
	{/if}
</div>
