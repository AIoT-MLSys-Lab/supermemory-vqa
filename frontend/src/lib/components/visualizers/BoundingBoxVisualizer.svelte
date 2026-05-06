<script lang="ts">
	import type { LocationBox, TimeSpan } from "$lib/types";

	interface Props {
		boxes?: LocationBox[];
		defaultTimestamp?: string;
		activeVideoSource?: string;
		questionTimeSpan?: TimeSpan;
		questionVideoPath?: string;
		onSeek?: (timestamp: string) => void;
		onShowBox?: (box: LocationBox, index: number) => void;
	}

	let {
		boxes,
		defaultTimestamp = "00:00",
		activeVideoSource,
		questionTimeSpan,
		questionVideoPath,
		onSeek,
		onShowBox,
	}: Props = $props();

	// Helper to convert MM:SS to seconds
	function parseTime(time: string): number {
		const parts = time.split(":");
		if (parts.length !== 2) return 0;
		return parseInt(parts[0]) * 60 + parseInt(parts[1]);
	}

	function isQuestionBox(box: LocationBox): boolean {
		// Rule: Question if timestamp is within question timespan AND source is same as question
		if (!questionTimeSpan || !questionVideoPath) return false;

		const boxVideo = box.video_path || questionVideoPath; // Default to question video if not specified
		if (boxVideo !== questionVideoPath) return false;

		const ts = parseTime(box.timestamp || defaultTimestamp);
		const start = parseTime(questionTimeSpan.start || "00:00");
		const end = questionTimeSpan.end
			? parseTime(questionTimeSpan.end)
			: Infinity;

		return ts >= start && ts <= end;
	}

	// Filter boxes based on the active video source
	let filteredBoxes = $derived(
		(boxes || []).filter((box) => {
			if (!activeVideoSource) return true; // Show all if no source selected
			// strict match if path is present
			if (box.video_path) return box.video_path === activeVideoSource;
			// if path missing, assume it belongs to question video?
			// if activeVideoSource is questionVideoPath, show it.
			if (questionVideoPath && activeVideoSource === questionVideoPath)
				return true;

			return false;
		}),
	);

	function handleBoxClick(box: LocationBox, index: number) {
		if (onShowBox) {
			onShowBox(box, index);
		} else if (onSeek) {
			const timestamp = box.timestamp || defaultTimestamp;
			onSeek(timestamp);
		}
	}

	function getBoxIcon(box: LocationBox): string {
		return isQuestionBox(box) ? "❓" : "💡";
	}
</script>

<div class="bounding-box-visualizer">
	{#if boxes && boxes.length > 0}
		<div class="flex items-center gap-1 flex-wrap">
			<span class="text-[10px] text-muted-foreground uppercase font-medium">
				Boxes ({filteredBoxes.length}):
			</span>
			{#if filteredBoxes.length > 0}
				{#each filteredBoxes as box}
					{@const originalIndex = boxes.indexOf(box)}
					<button
						type="button"
						class="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded transition-colors border bg-secondary hover:bg-secondary/80 border-border"
						onclick={() => handleBoxClick(box, originalIndex)}
						title={`Box ${originalIndex + 1} @ ${box.timestamp || defaultTimestamp}${box.description ? " - " + box.description : ""}`}
					>
						<span class="font-medium">B{originalIndex + 1}</span>
						<span>{getBoxIcon(box)}</span>
						<span class="text-muted-foreground"
							>@ {box.timestamp || defaultTimestamp}</span
						>
					</button>
				{/each}
			{:else}
				<span class="text-muted-foreground italic text-[10px]"
					>None for this video</span
				>
			{/if}
		</div>
	{:else}
		<span class="text-muted-foreground italic text-sm">📦 No bounding boxes</span>
	{/if}
</div>
