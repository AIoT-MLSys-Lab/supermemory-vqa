<script lang="ts">
	import Input from "$lib/components/ui/input/Input.svelte";
	import Label from "$lib/components/ui/label/Label.svelte";
	import CaptionSearchPanel from "$lib/components/editors/CaptionSearchPanel.svelte";
	import type { TimeSpanData } from "$lib/types/annotation-data-types";

	interface Props {
		data: TimeSpanData;
		label?: string;
		showVideoPath?: boolean;
		showCaptionSearch?: boolean;
		currentVideoPath?: string;
		onChange: (newData: TimeSpanData) => void;
		onRequestProgressBarEdit?: () => void; // Callback to enable progress bar editing mode
	}

	let {
		data,
		label = "Time Span",
		showVideoPath = false,
		showCaptionSearch = false,
		currentVideoPath,
		onChange,
		onRequestProgressBarEdit,
	}: Props = $props();

	function handleStartChange(e: Event) {
		const target = e.currentTarget as HTMLInputElement;
		onChange({
			...data,
			value: {
				...data.value,
				start: target.value,
			},
		});
	}

	function handleEndChange(e: Event) {
		const target = e.currentTarget as HTMLInputElement;
		onChange({
			...data,
			value: {
				...data.value,
				end: target.value,
			},
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
			value: {
				start: selection.start_time,
				end: selection.end_time,
			},
		});
	}
</script>

<div class="timespan-editor space-y-2">
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
	<div class="grid grid-cols-2 gap-4">
		<div class="space-y-1">
			<span class="text-xs text-muted-foreground">Start</span>
			<Input
				type="text"
				value={data.value?.start || ""}
				oninput={handleStartChange}
				placeholder="00:00"
			/>
		</div>
		<div class="space-y-1">
			<span class="text-xs text-muted-foreground">End</span>
			<Input
				type="text"
				value={data.value?.end || ""}
				oninput={handleEndChange}
				placeholder="00:00"
			/>
		</div>
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
