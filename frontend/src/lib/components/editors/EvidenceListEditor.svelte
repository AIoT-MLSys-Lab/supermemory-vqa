<script lang="ts">
	/**
	 * EvidenceListEditor
	 *
	 * Editor for a list of evidence items, each containing multiple timespans.
	 * Reuses TimeSpanEditor for each individual timespan.
	 * This demonstrates reusability: the same editor component is used for each timespan.
	 */

	import TimeSpanEditor from "./TimeSpanEditor.svelte";
	import CaptionSearchPanel from "./CaptionSearchPanel.svelte";
	import Button from "$lib/components/ui/button/Button.svelte";
	import Label from "$lib/components/ui/label/Label.svelte";
	import type { EvidenceListData, TimeSpanData } from "$lib/types/annotation-data-types";
	import { AnnotationDataType } from "$lib/types/annotation-data-types";

	interface Props {
		data: EvidenceListData;
		label?: string;
		currentVideoPath?: string;
		showCaptionSearch?: boolean;
		onChange: (newData: EvidenceListData) => void;
		onRequestVideoBrowser?: (evidenceIndex: number) => void;
	}

	let {
		data,
		label = "Answer Evidence",
		currentVideoPath,
		showCaptionSearch = false,
		onChange,
		onRequestVideoBrowser,
	}: Props = $props();

	function addEvidence() {
		const newValue = [
			...(data.value || []),
			{
				time_spans: [{ start: "00:00", end: "00:00" }],
				video_path: undefined,
			},
		];
		onChange({ ...data, value: newValue });
	}

	function removeEvidence(index: number) {
		const newValue = (data.value || []).filter((_, i) => i !== index);
		onChange({ ...data, value: newValue });
	}

	function addTimeSpan(evidenceIndex: number) {
		if (!data.value?.[evidenceIndex]) return;
		const newValue = [...data.value];
		if (!newValue[evidenceIndex].time_spans) {
			newValue[evidenceIndex].time_spans = [];
		}
		newValue[evidenceIndex].time_spans!.push({ start: "00:00", end: "00:00" });
		onChange({ ...data, value: newValue });
	}

	function removeTimeSpan(evidenceIndex: number, timeSpanIndex: number) {
		if (!data.value?.[evidenceIndex]?.time_spans) return;
		const newValue = [...data.value];
		newValue[evidenceIndex].time_spans = newValue[evidenceIndex].time_spans!.filter(
			(_, i) => i !== timeSpanIndex
		);
		onChange({ ...data, value: newValue });
	}

	function updateTimeSpan(evidenceIndex: number, timeSpanIndex: number, timeSpanData: TimeSpanData) {
		if (!data.value?.[evidenceIndex]?.time_spans?.[timeSpanIndex]) return;
		const newValue = [...data.value];
		newValue[evidenceIndex].time_spans![timeSpanIndex] = timeSpanData.value!;
		onChange({ ...data, value: newValue });
	}

	function getVideoDisplayName(path?: string): string {
		if (!path) return "Current video";
		const parts = path.split("/");
		return parts[parts.length - 1] || path;
	}

	function applyCaptionSelectionToEvidence(
		evidenceIndex: number,
		selection: { video_id: string; video_path?: string; start_time: string; end_time: string }
	) {
		if (!data.value?.[evidenceIndex]) return;
		const newValue = [...data.value];
		newValue[evidenceIndex].video_path = selection.video_path || `${selection.video_id}.mp4`;
		if (!newValue[evidenceIndex].time_spans || newValue[evidenceIndex].time_spans!.length === 0) {
			newValue[evidenceIndex].time_spans = [{ start: selection.start_time, end: selection.end_time }];
		} else {
			newValue[evidenceIndex].time_spans![0] = { start: selection.start_time, end: selection.end_time };
		}
		onChange({ ...data, value: newValue });
	}
</script>

<div class="evidence-list-editor space-y-4">
	{#if label}
		<div class="flex items-center justify-between">
			<Label>{label}</Label>
			<Button size="sm" variant="outline" onclick={addEvidence}>
				➕ Add Evidence
			</Button>
		</div>
	{/if}

	{#if data.value && data.value.length > 0}
		{#each data.value as evidence, i}
			<div class="border rounded-lg p-4 bg-secondary/50 space-y-4 relative">
				<div class="flex items-center justify-between">
					<span class="text-sm font-medium">Evidence #{i + 1}</span>
					{#if data.value.length > 1}
						<Button
							size="sm"
							variant="ghost"
							class="text-destructive hover:text-destructive/80 h-6 px-2"
							onclick={() => removeEvidence(i)}
						>
							Remove
						</Button>
					{/if}
				</div>

				<!-- Video Selection -->
				<div class="space-y-2">
					<Label>Video File</Label>
					<div class="flex items-center gap-2">
						<div
							class="flex-1 p-2 bg-white rounded border text-sm font-mono truncate"
							title={evidence.video_path || currentVideoPath}
						>
							🎥 {getVideoDisplayName(evidence.video_path || currentVideoPath)}
							{#if evidence.video_path && evidence.video_path !== currentVideoPath}
								<span class="text-primary text-xs ml-1">(different video)</span>
							{:else if !evidence.video_path}
								<span class="text-muted-foreground text-xs ml-1">(current video)</span>
							{/if}
						</div>
						{#if onRequestVideoBrowser}
							<Button
								variant="secondary"
								size="sm"
								onclick={() => onRequestVideoBrowser?.(i)}
							>
								Change...
							</Button>
						{/if}
					</div>
				</div>

				<!-- Time Spans - REUSING TimeSpanEditor for each timespan -->
				<div class="space-y-3">
					<div class="flex items-center justify-between">
						<Label>Time Spans</Label>
						<Button
							size="sm"
							variant="ghost"
							class="h-6 text-xs"
							onclick={() => addTimeSpan(i)}
						>
							➕ Add Time Span
						</Button>
					</div>

					{#if evidence.time_spans && evidence.time_spans.length > 0}
						{#each evidence.time_spans as span, j}
							<div class="flex items-end gap-2">
								<div class="flex-1">
									<!-- REUSING TimeSpanEditor component -->
									<TimeSpanEditor
										data={{
											type: AnnotationDataType.TIMESPAN,
											value: span,
											editable: true,
											videoPath: evidence.video_path,
										}}
										label={evidence.time_spans.length > 1 ? `Span #${j + 1}` : undefined}
										{currentVideoPath}
										onChange={(newTimeSpanData) => updateTimeSpan(i, j, newTimeSpanData)}
									/>
								</div>
								{#if evidence.time_spans.length > 1}
									<Button
										size="sm"
										variant="ghost"
										class="text-destructive hover:text-destructive/80 h-8 w-8 p-0 mb-2"
										onclick={() => removeTimeSpan(i, j)}
										title="Remove time span"
									>
										🗑️
									</Button>
								{/if}
							</div>
						{/each}
					{:else}
						<div class="text-xs text-muted-foreground italic">No time spans added.</div>
					{/if}
				</div>
				{#if showCaptionSearch}
					<div class="space-y-2">
						<Label>Search Captions</Label>
						<CaptionSearchPanel onSelect={(selection) => applyCaptionSelectionToEvidence(i, selection)} />
					</div>
				{/if}
			</div>
		{/each}
	{:else}
		<div class="text-sm text-muted-foreground italic p-4 border-2 border-dashed rounded-lg text-center">
			No evidence items. Click "Add Evidence" to create one.
		</div>
	{/if}
</div>
