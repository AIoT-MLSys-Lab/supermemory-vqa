<script lang="ts">
	/**
	 * EvidenceListVisualizer
	 *
	 * Visualizes a list of evidence items, each containing timespans.
	 * Reuses TimeSpanVisualizer for each individual timespan.
	 * This demonstrates reusability: multiple timespans use the same visualizer component.
	 */

	import TimeSpanVisualizer from "./TimeSpanVisualizer.svelte";
	import type { Evidence } from "$lib/types";

	interface Props {
		value?: Evidence[];
		currentVideoPath?: string;
		onSeek?: (timestamp: string, videoPath?: string) => void;
	}

	let { value, currentVideoPath, onSeek }: Props = $props();

	// Get display name from video path
	function getVideoDisplayName(path?: string): string {
		if (!path) return 'Current video';
		const parts = path.split('/');
		return parts[parts.length - 1] || path;
	}
</script>

<div class="evidence-list-visualizer space-y-2">
	{#if value && value.length > 0}
		{#each value as evidence, i}
			<div class="border-l-2 border-primary/30 pl-3 space-y-1">
				<div class="text-xs text-muted-foreground font-medium">
					Evidence #{i + 1}
					{#if evidence.video_path && evidence.video_path !== currentVideoPath}
						<span class="text-primary ml-1" title={evidence.video_path}>
							📹 {getVideoDisplayName(evidence.video_path)}
						</span>
					{/if}
				</div>

				{#if evidence.time_spans && evidence.time_spans.length > 0}
					<div class="space-y-1">
						{#each evidence.time_spans as timespan, j}
							<div class="flex items-center gap-2">
								{#if evidence.time_spans.length > 1}
									<span class="text-xs text-muted-foreground">#{j + 1}</span>
								{/if}
								<!-- REUSING TimeSpanVisualizer for each timespan -->
								<TimeSpanVisualizer
									value={timespan}
									videoPath={evidence.video_path}
									{currentVideoPath}
									onSeek={(timestamp) => {
										if (onSeek) {
											onSeek(timestamp, evidence.video_path);
										}
									}}
								/>
							</div>
						{/each}
					</div>
				{:else}
					<span class="text-xs text-muted-foreground italic">No timespans specified</span>
				{/if}
			</div>
		{/each}
	{:else}
		<span class="text-muted-foreground italic">No evidence provided</span>
	{/if}
</div>
