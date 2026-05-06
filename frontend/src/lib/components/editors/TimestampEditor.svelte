<script lang="ts">
	/**
	 * TimestampEditor
	 *
	 * Editor for a single timestamp (MM:SS format).
	 * Supports both manual input and progress bar dragging.
	 * Reuses similar UI patterns from TimeSpanEditor but for a single time point.
	 */

	import Input from "$lib/components/ui/input/Input.svelte";
	import Label from "$lib/components/ui/label/Label.svelte";
	import CaptionSearchPanel from "$lib/components/editors/CaptionSearchPanel.svelte";
	import type { TimestampData } from "$lib/types/annotation-data-types";

	interface Props {
		data: TimestampData;
		label?: string;
		showVideoPath?: boolean;
		showCaptionSearch?: boolean;
		currentVideoPath?: string;
		onChange: (newData: TimestampData) => void;
		onRequestProgressBarEdit?: () => void; // Callback to enable progress bar editing mode
	}

	let {
		data,
		label = "Timestamp",
		showVideoPath = false,
		showCaptionSearch = false,
		currentVideoPath,
		onChange,
		onRequestProgressBarEdit,
	}: Props = $props();

	function handleValueChange(e: Event) {
		const target = e.currentTarget as HTMLInputElement;
		onChange({
			...data,
			value: target.value,
		});
	}

	function handleCaptionSelection(selection: {
		video_id: string;
		video_path?: string;
		start_time: string;
		end_time: string;
	}) {
		onChange({
			...data,
			videoPath: selection.video_path || `${selection.video_id}.mp4`,
			value: selection.start_time,
		});
	}
</script>

<div class="timestamp-editor space-y-2">
	{#if label}
		<div class="flex items-center justify-between">
			<Label>{label}</Label>
			{#if data.editable && onRequestProgressBarEdit}
				<button
					type="button"
					class="text-xs text-primary hover:underline"
					onclick={onRequestProgressBarEdit}
					title="Edit by dragging on the progress bar"
				>
					📊 Drag on timeline
				</button>
			{/if}
		</div>
	{/if}
	<div class="space-y-1">
		<span class="text-xs text-muted-foreground">Time</span>
		<Input
			type="text"
			value={data.value || ""}
			oninput={handleValueChange}
			placeholder="00:00"
		/>
	</div>
	{#if showVideoPath && data.videoPath}
		<div class="text-xs text-muted-foreground">
			Video: {data.videoPath === currentVideoPath ? "Current video" : data.videoPath}
		</div>
	{/if}
	{#if showCaptionSearch}
		<CaptionSearchPanel onSelect={handleCaptionSelection} />
	{/if}
</div>
