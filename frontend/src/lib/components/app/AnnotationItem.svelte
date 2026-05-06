<script lang="ts">
	import { IconButton } from "./ui";
	import {
		TextVisualizer,
		TimeSpanVisualizer,
		QuestionTimeSpanVisualizer,
		SkillVisualizer,
		RoomVisualizer,
		ModalitiesVisualizer,
		HumanReviewVisualizer,
		BoundingBoxVisualizer,
	} from "$lib/components/visualizers";
	import MultipleChoiceAnswerVisualizer from "$lib/components/visualizers/MultipleChoiceAnswerVisualizer.svelte";
	import type { Annotation, LocationBox } from "$lib/types";
	import { getReviewStatus } from "$lib/stores";

	// ...
	interface Props {
		annotation: Annotation;
		index: number;
		isSelected?: boolean;
		currentVideoPath?: string;
		sourceFile?: string;
		onSeek?: (timestamp: string, stream?: string) => void;
		onShowBox?: (
			box: LocationBox,
			index: number,
			evidenceIndex?: number,
		) => void;
		onEdit?: (index: number) => void;
		onReview?: (index: number) => void;
		onDelete?: (index: number) => void;
		onSelect?: (index: number) => void;
		onQuickAdd?: (index: number) => void;
		activeVideoSource?: string;
		onNext?: () => void;
		onPrevious?: () => void;
	}

	let {
		annotation,
		index,
		isSelected = false,
		currentVideoPath,
		sourceFile,
		onSeek,
		onShowBox,
		onEdit,
		onReview,
		onDelete,
		onSelect,
		onQuickAdd,
		activeVideoSource,
		onNext,
		onPrevious,
	}: Props = $props();

	const reviewStatus = $derived(getReviewStatus(annotation.human_review));
	const vs = $derived(annotation.verification_score);
	let showVerificationDetails = $state(false);
	let showEvidenceDetails = $state(false);

	// Normalize pipeline_v2 data structures
	const questionTimeSpans = $derived(
		annotation.question_time_spans?.length 
			? annotation.question_time_spans 
			: (annotation.question as any)?.time_spans?.map((ts: any) => ({
				start: ts.start_time || ts.start,
				end: ts.end_time || ts.end,
				video_id: ts.video_id
			})) || (annotation.question_time_span ? [annotation.question_time_span] : [])
	);

	const questionBoxes = $derived(
		annotation.location?.boxes ||
			(annotation.question as any)?.bounding_boxes?.map((b: any) => ({
				box_2d: [b.ymin, b.xmin, b.ymax, b.xmax],
				label: b.label,
				timestamp: b.time_offset,
				description: b.label,
			})) ||
			[],
	);

	const evidenceList = $derived(
		annotation.answer_evidence ||
			(annotation.answer as any)?.evidence_list?.map((e: any) => ({
				reason: e.reason,
				room: e.room,
				modalities: e.modalities,
				video_path: e.video_id,
				time_spans: e.time_span
					? [
							{
								start: e.time_span.start_time,
								end: e.time_span.end_time,
							},
						]
					: [],
				bounding_boxes: e.bounding_boxes?.map((b: any) => ({
					box_2d: [b.ymin, b.xmin, b.ymax, b.xmax],
					label: b.label,
					timestamp: b.time_offset,
					description: b.label,
				})),
			})) ||
			[],
	);
</script>

<div
	class="border rounded-lg p-5 hover:shadow-md transition-all {isSelected
		? 'ring-2 ring-primary bg-primary/5'
		: 'bg-card'}"
	data-annotation-index={index}
>
	<!-- Header -->
	<div class="flex items-center justify-between mb-3">
		<div class="flex items-center gap-2">
			<SkillVisualizer value={annotation.skill} />
			<HumanReviewVisualizer value={annotation.human_review} />
			{#if annotation.annotation_type}
				{@const typeClass =
					annotation.annotation_type === "verified"
						? "bg-emerald-100 text-emerald-700 border border-emerald-300"
						: "bg-red-100 text-red-700 border border-red-300"}
				<span
					class="text-[10px] font-semibold px-1.5 py-0.5 rounded {typeClass}"
				>
					{annotation.annotation_type}
				</span>
			{/if}
		</div>
		<div class="flex items-center gap-2">
			{#if vs && vs.factual_correctness_score !== undefined}
				<span
					class="text-[10px] font-mono px-1.5 py-0.5 rounded border {(vs.factual_correctness_score ??
						0) >= 0.7
						? 'bg-emerald-50 text-emerald-700 border-emerald-300'
						: 'bg-red-50 text-red-700 border-red-300'}"
					title="Factual Correctness"
				>
					F:{vs.factual_correctness_score?.toFixed(1)}
				</span>
			{/if}
			{#if vs && vs.causal_answerability_score !== undefined}
				<span
					class="text-[10px] font-mono px-1.5 py-0.5 rounded border {(vs.causal_answerability_score ??
						0) >= 0.7
						? 'bg-emerald-50 text-emerald-700 border-emerald-300'
						: 'bg-red-50 text-red-700 border-red-300'}"
					title="Causal Answerability"
				>
					C:{vs.causal_answerability_score?.toFixed(1)}
				</span>
			{/if}
			{#if vs && vs.question_naturalness_score !== undefined}
				<span
					class="text-[10px] font-mono px-1.5 py-0.5 rounded border {(vs.question_naturalness_score ??
						0) >= 0.7
						? 'bg-emerald-50 text-emerald-700 border-emerald-300'
						: 'bg-red-50 text-red-700 border-red-300'}"
					title="Question Naturalness"
				>
					N:{vs.question_naturalness_score?.toFixed(1)}
				</span>
			{/if}
			{#if vs && vs.temporal_grounding_score !== undefined}
				<span
					class="text-[10px] font-mono px-1.5 py-0.5 rounded border {(vs.temporal_grounding_score ??
						0) >= 0.7
						? 'bg-emerald-50 text-emerald-700 border-emerald-300'
						: 'bg-red-50 text-red-700 border-red-300'}"
					title="Temporal Grounding"
				>
					T:{vs.temporal_grounding_score?.toFixed(1)}
				</span>
			{/if}
			{#if vs && vs.privacy_violation}
				<span
					class="text-[10px] font-bold px-1.5 py-0.5 rounded border bg-red-600 text-white border-red-700"
					title="Privacy Violation Detected"
				>
					PRIVACY
				</span>
			{/if}
			{#if vs && vs.objective_correctness_score !== undefined}
				<span
					class="text-[10px] font-mono px-1.5 py-0.5 rounded border {(vs.objective_correctness_score ??
						0) >= 0.7
						? 'bg-emerald-50 text-emerald-700 border-emerald-300'
						: 'bg-red-50 text-red-700 border-red-300'}"
					title="Objective Score (Deprecated)"
				>
					O:{vs.objective_correctness_score?.toFixed(1)}
				</span>
			{/if}
			{#if isSelected}
				<span
					class="text-xs text-primary font-semibold bg-primary/10 px-2 py-1 rounded"
					>Selected for drawing</span
				>
			{/if}
			{#if sourceFile}
				<span
					class="text-xs text-muted-foreground bg-secondary px-2 py-1 rounded"
					title={sourceFile}
				>
					{sourceFile.length > 20
						? sourceFile.slice(0, 17) + "..."
						: sourceFile}
				</span>
			{/if}
			<span class="text-muted-foreground text-base font-mono"
				>#{index + 1}</span
			>
		</div>
	</div>

	<!-- Question -->
	<div class="mb-2">
		<TextVisualizer
			value={annotation.question}
			prefix="Q:"
			placeholder="No question provided"
			style="question"
		/>
	</div>

	<!-- Answer -->
	<div class="mb-3">
		{#if annotation.answer_choices && annotation.answer_choices.length > 0}
			<MultipleChoiceAnswerVisualizer
				value={annotation.answer_choices}
				isAnswerable={annotation.is_answerable}
				showExplanations={true}
			/>
		{:else}
			<TextVisualizer
				value={annotation.answer}
				prefix="A:"
				placeholder="No answer provided"
				style="answer"
			/>
		{/if}
	</div>

	<!-- Timestamps & Evidence -->
	<div class="flex flex-wrap gap-2 mb-3 text-base">
		{#if questionTimeSpans.length > 0}
			<QuestionTimeSpanVisualizer 
				value={questionTimeSpans} 
				onSeek={(ts, vid) => onSeek?.(ts, vid || currentVideoPath)} 
			/>
		{/if}
		{#if evidenceList.length > 0}
			{#each evidenceList as evidence, i}
				{#if evidence.time_spans && evidence.time_spans.length > 0}
					{#each evidence.time_spans as span, j}
						<div
							class="flex items-center gap-1.5 bg-secondary rounded px-2 py-1 border border-border"
						>
							<span
								class="text-xs text-muted-foreground font-bold uppercase"
								>Ev {i + 1}.{j + 1}</span
							>
							<TimeSpanVisualizer
								value={span}
								videoPath={evidence.video_path}
								{currentVideoPath}
								onSeek={(ts) =>
									onSeek?.(ts, evidence.video_path)}
							/>
						</div>
					{/each}
				{:else if evidence?.time_spans}
					<div
						class="flex items-center gap-1.5 bg-secondary rounded px-2 py-1 border border-border"
					>
						<span
							class="text-xs text-muted-foreground font-bold uppercase"
							>Ev {i + 1}</span
						>
						<TimeSpanVisualizer
							value={evidence?.time_spans[0]}
							videoPath={evidence.video_path}
							{currentVideoPath}
							onSeek={(ts) => onSeek?.(ts, evidence.video_path)}
						/>
					</div>
				{/if}
			{/each}
		{:else}
			<TimeSpanVisualizer
				value={annotation.time_span}
				videoPath={annotation.answer_video_path}
				{currentVideoPath}
				{onSeek}
			/>
		{/if}
	</div>

	<!-- Metadata: Location & Modality -->
	<div class="flex flex-col gap-2 mb-3 text-base">
		{#if annotation.room}
			<div class="flex items-center">
				<RoomVisualizer value={annotation.room} />
			</div>
		{/if}
		{#if annotation.modalities && annotation.modalities.length > 0}
			<div class="flex items-center gap-1">
				<span class="text-xs font-medium text-muted-foreground"
					>Q Modalities:</span
				>
				<ModalitiesVisualizer value={annotation.modalities} />
			</div>
		{/if}
		{#if annotation.confidence !== undefined}
			<div class="flex items-center gap-1 text-xs">
				<span class="font-medium text-muted-foreground"
					>Confidence:</span
				>
				<span class="font-mono"
					>{typeof annotation.confidence === "number"
						? annotation.confidence.toFixed(2)
						: annotation.confidence}</span
				>
			</div>
		{/if}
		{#if annotation.confidence_reasoning}
			<div class="text-xs text-muted-foreground italic">
				{annotation.confidence_reasoning}
			</div>
		{/if}
	</div>

	<!-- Location / Bounding boxes (question-level) -->
	{#if questionBoxes.length > 0}
		<div class="mb-2">
			<BoundingBoxVisualizer
				boxes={questionBoxes}
				defaultTimestamp={annotation.time_span?.start}
				{onSeek}
				onShowBox={(box, boxIndex) => onShowBox?.(box, boxIndex)}
				{activeVideoSource}
				questionTimeSpan={annotation.question_time_span}
				questionVideoPath={currentVideoPath}
			/>
		</div>
	{/if}

	<!-- Answer Evidence Details (reason, room, modalities, bounding boxes) -->
	{#if evidenceList.length > 0 && evidenceList.some((e: any) => e.reason || e.room || (e.modalities && e.modalities.length > 0) || (e.bounding_boxes && e.bounding_boxes.length > 0))}
		<div class="mb-3">
			<button
				class="text-xs font-medium text-muted-foreground hover:text-foreground flex items-center gap-1 mb-1"
				onclick={() => {
					showEvidenceDetails = !showEvidenceDetails;
				}}
			>
				<svg
					xmlns="http://www.w3.org/2000/svg"
					class="h-3 w-3 transition-transform {showEvidenceDetails
						? 'rotate-90'
						: ''}"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="2"><path d="M9 18l6-6-6-6" /></svg
				>
				Evidence Details ({evidenceList.length})
			</button>
			{#if showEvidenceDetails}
				<div class="space-y-2 pl-3 border-l-2 border-border">
					{#each evidenceList as evidence, i}
						<div
							class="text-xs bg-secondary/50 rounded p-2 space-y-1"
						>
							<div class="font-semibold text-muted-foreground">
								Evidence {i + 1}
							</div>
							{#if evidence.reason}
								<div>
									<span
										class="font-medium text-muted-foreground"
										>Reason:</span
									>
									{evidence.reason}
								</div>
							{/if}
							{#if evidence.room}
								<div>
									<span
										class="font-medium text-muted-foreground"
										>Room:</span
									>
									{evidence.room}
								</div>
							{/if}
							{#if evidence.modalities && evidence.modalities.length > 0}
								<div class="flex items-center gap-1 flex-wrap">
									<span
										class="font-medium text-muted-foreground"
										>Modalities:</span
									>
									{#each evidence.modalities as mod}
										<span
											class="text-[10px] bg-secondary px-1.5 py-0.5 rounded border border-border"
											>{mod}</span
										>
									{/each}
								</div>
							{/if}
							{#if evidence.bounding_boxes && evidence.bounding_boxes.length > 0}
								<div class="mt-1">
									<BoundingBoxVisualizer
										boxes={evidence.bounding_boxes}
										defaultTimestamp={evidence
											.time_spans?.[0]?.start}
										{onSeek}
										onShowBox={(box, boxIndex) =>
											onShowBox?.(box, boxIndex, i)}
										questionVideoPath={evidence.video_path ||
											currentVideoPath}
									/>
								</div>
							{/if}
						</div>
					{/each}
				</div>
			{/if}
		</div>
	{/if}

	<!-- Verification Score Details -->
	{#if vs}
		<div class="mb-2">
			<button
				class="text-xs font-medium text-muted-foreground hover:text-foreground flex items-center gap-1"
				onclick={() => {
					showVerificationDetails = !showVerificationDetails;
				}}
			>
				<svg
					xmlns="http://www.w3.org/2000/svg"
					class="h-3 w-3 transition-transform {showVerificationDetails
						? 'rotate-90'
						: ''}"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="2"><path d="M9 18l6-6-6-6" /></svg
				>
				Verification Details
				{#if vs.is_correct !== undefined}
					<span
						class="ml-1 {vs.is_correct
							? 'text-emerald-600'
							: 'text-red-600'}"
					>
						{vs.is_correct ? "✓ Correct" : "✗ Incorrect"}
					</span>
				{/if}
			</button>
			{#if showVerificationDetails}
				<div
					class="mt-1 text-xs bg-secondary/50 rounded p-3 space-y-2 border border-border"
				>
					{#if vs.factual_correctness_score !== undefined}
						<div class="flex items-center gap-2">
							<span class="font-medium text-muted-foreground w-32"
								>Factual Score:</span
							>
							<div
								class="flex-1 bg-muted rounded-full h-2 overflow-hidden"
							>
								<div
									class="h-full rounded-full {(vs.factual_correctness_score ??
										0) >= 0.7
										? 'bg-emerald-500'
										: 'bg-red-500'}"
									style="width: {(vs.factual_correctness_score ??
										0) * 100}%"
								></div>
							</div>
							<span class="font-mono w-10 text-right"
								>{vs.factual_correctness_score?.toFixed(
									2,
								)}</span
							>
						</div>
					{/if}
					{#if vs.causal_answerability_score !== undefined}
						<div class="flex items-center gap-2">
							<span class="font-medium text-muted-foreground w-32"
								>Causal Score:</span
							>
							<div
								class="flex-1 bg-muted rounded-full h-2 overflow-hidden"
							>
								<div
									class="h-full rounded-full {(vs.causal_answerability_score ??
										0) >= 0.7
										? 'bg-emerald-500'
										: 'bg-red-500'}"
									style="width: {(vs.causal_answerability_score ??
										0) * 100}%"
								></div>
							</div>
							<span class="font-mono w-10 text-right"
								>{vs.causal_answerability_score?.toFixed(
									2,
								)}</span
							>
						</div>
					{/if}
					{#if vs.question_naturalness_score !== undefined}
						<div class="flex items-center gap-2">
							<span class="font-medium text-muted-foreground w-32"
								>Naturalness Score:</span
							>
							<div
								class="flex-1 bg-muted rounded-full h-2 overflow-hidden"
							>
								<div
									class="h-full rounded-full {(vs.question_naturalness_score ??
										0) >= 0.7
										? 'bg-emerald-500'
										: 'bg-red-500'}"
									style="width: {(vs.question_naturalness_score ??
										0) * 100}%"
								></div>
							</div>
							<span class="font-mono w-10 text-right"
								>{vs.question_naturalness_score?.toFixed(
									2,
								)}</span
							>
						</div>
					{/if}
					{#if vs.temporal_grounding_score !== undefined}
						<div class="flex items-center gap-2">
							<span class="font-medium text-muted-foreground w-32"
								>Temporal Score:</span
							>
							<div
								class="flex-1 bg-muted rounded-full h-2 overflow-hidden"
							>
								<div
									class="h-full rounded-full {(vs.temporal_grounding_score ??
										0) >= 0.7
										? 'bg-emerald-500'
										: 'bg-red-500'}"
									style="width: {(vs.temporal_grounding_score ??
										0) * 100}%"
								></div>
							</div>
							<span class="font-mono w-10 text-right"
								>{vs.temporal_grounding_score?.toFixed(
									2,
								)}</span
							>
						</div>
					{/if}
					{#if vs.objective_correctness_score !== undefined}
						<div class="flex items-center gap-2 opacity-50">
							<span class="font-medium text-muted-foreground w-32"
								>Objective (Old):</span
							>
							<div
								class="flex-1 bg-muted rounded-full h-2 overflow-hidden"
							>
								<div
									class="h-full rounded-full {(vs.objective_correctness_score ??
										0) >= 0.7
										? 'bg-emerald-500'
										: 'bg-red-500'}"
									style="width: {(vs.objective_correctness_score ??
										0) * 100}%"
								></div>
							</div>
							<span class="font-mono w-10 text-right"
								>{vs.objective_correctness_score?.toFixed(
									2,
								)}</span
							>
						</div>
					{/if}
					{#if vs.factual_correctness_reasoning}
						<div>
							<span class="font-medium text-muted-foreground"
								>Factual Reasoning:</span
							>
							<span class="text-foreground"
								>{vs.factual_correctness_reasoning}</span
							>
						</div>
					{/if}
					{#if vs.causal_answerability_reasoning}
						<div>
							<span class="font-medium text-muted-foreground"
								>Causal Reasoning:</span
							>
							<span class="text-foreground"
								>{vs.causal_answerability_reasoning}</span
							>
						</div>
					{/if}
					{#if vs.question_naturalness_reasoning}
						<div>
							<span class="font-medium text-muted-foreground"
								>Naturalness Reasoning:</span
							>
							<span class="text-foreground"
								>{vs.question_naturalness_reasoning}</span
							>
						</div>
					{/if}
					{#if vs.temporal_grounding_reasoning}
						<div>
							<span class="font-medium text-muted-foreground"
								>Temporal Reasoning:</span
							>
							<span class="text-foreground"
								>{vs.temporal_grounding_reasoning}</span
							>
						</div>
					{/if}
					{#if vs.objective_correctness_reasoning}
						<div class="opacity-50">
							<span class="font-medium text-muted-foreground"
								>Objective Reasoning (Old):</span
							>
							<span class="text-foreground"
								>{vs.objective_correctness_reasoning}</span
							>
						</div>
					{/if}
					{#if vs.suggestions && vs.suggestions.length > 0}
						<div>
							<span class="font-medium text-muted-foreground"
								>Suggestions:</span
							>
							<ul
								class="list-disc list-inside ml-2 mt-0.5 text-foreground"
							>
								{#each vs.suggestions as sug}
									<li>{sug}</li>
								{/each}
							</ul>
						</div>
					{/if}
					{#if vs.suggested_chunks && vs.suggested_chunks.length > 0}
						<div>
							<span class="font-medium text-muted-foreground"
								>Suggested Chunks:</span
							>
							<div class="space-y-1 mt-0.5">
								{#each vs.suggested_chunks as sc}
									<div
										class="bg-secondary p-1.5 rounded text-foreground"
									>
										<span class="font-mono"
											>Chunk #{sc.chunk_index}</span
										>
										{#if sc.relevance_score !== undefined}
											<span
												class="ml-1 text-muted-foreground"
												>(relevance: {sc.relevance_score?.toFixed(
													2,
												)})</span
											>
										{/if}
										{#if sc.relevance_reason}
											<div
												class="mt-0.5 text-muted-foreground"
											>
												{sc.relevance_reason}
											</div>
										{/if}
									</div>
								{/each}
							</div>
						</div>
					{/if}
				</div>
			{/if}
		</div>
	{/if}

	<!-- Actions -->
	<div class="flex items-center gap-1 pt-2 border-t mt-2">
		<IconButton
			label="Previous Annotation"
			onclick={() => onPrevious?.()}
			disabled={!onPrevious}
		>
			{#snippet icon()}
				<svg
					xmlns="http://www.w3.org/2000/svg"
					class="h-4 w-4"
					fill="none"
					stroke="currentColor"
					stroke-width="2"
					viewBox="0 0 24 24"><path d="M15 18l-6-6 6-6" /></svg
				>
			{/snippet}
		</IconButton>
		<IconButton
			label="Play"
			onclick={() => {
				let start = "00:00";
				if (questionTimeSpans?.[0]?.start)
					start = questionTimeSpans[0].start;
				else if (evidenceList?.[0]?.time_spans?.[0]?.start)
					start = evidenceList[0].time_spans[0].start;
				else if (annotation.time_span?.start)
					start = annotation.time_span.start;
				onSeek?.(start);
			}}
		>
			{#snippet icon()}
				<svg
					xmlns="http://www.w3.org/2000/svg"
					class="h-4 w-4"
					viewBox="0 0 24 24"
					fill="currentColor"><path d="M8 5v14l11-7z" /></svg
				>
			{/snippet}
		</IconButton>
		<IconButton
			label="Next Annotation"
			onclick={() => onNext?.()}
			disabled={!onNext}
		>
			{#snippet icon()}
				<svg
					xmlns="http://www.w3.org/2000/svg"
					class="h-4 w-4"
					fill="none"
					stroke="currentColor"
					stroke-width="2"
					viewBox="0 0 24 24"><path d="M9 18l6-6-6-6" /></svg
				>
			{/snippet}
		</IconButton>
		<div class="w-px h-4 bg-border mx-1"></div>
		<IconButton label="Edit" onclick={() => onEdit?.(index)}>
			{#snippet icon()}
				<svg
					xmlns="http://www.w3.org/2000/svg"
					class="h-4 w-4"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="2"
					><path
						d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"
					/><path
						d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"
					/></svg
				>
			{/snippet}
		</IconButton>
		<IconButton
			label={reviewStatus !== "pending" ? "Change Review" : "Review"}
			onclick={() => onReview?.(index)}
			class={reviewStatus !== "pending" ? "text-emerald-600" : ""}
		>
			{#snippet icon()}
				<svg
					xmlns="http://www.w3.org/2000/svg"
					class="h-4 w-4"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="2"><polyline points="20 6 9 17 4 12" /></svg
				>
			{/snippet}
		</IconButton>
		<IconButton
			label={isSelected ? "Selected" : "Add New Box"}
			onclick={() => onSelect?.(index)}
			class={isSelected ? "text-primary bg-primary/10" : ""}
		>
			{#snippet icon()}
				<svg
					xmlns="http://www.w3.org/2000/svg"
					class="h-4 w-4"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="2"
					><rect x="3" y="3" width="18" height="18" rx="2" /><line
						x1="12"
						y1="8"
						x2="12"
						y2="16"
					/><line x1="8" y1="12" x2="16" y2="12" /></svg
				>
			{/snippet}
		</IconButton>
		<IconButton
			label="Quick Add Box"
			onclick={() => onQuickAdd?.(index)}
			title="Add box at current time with default coordinates"
		>
			{#snippet icon()}
				<svg
					xmlns="http://www.w3.org/2000/svg"
					class="h-4 w-4"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="2"
				>
					<path d="M12 2v20M2 12h20" />
					<circle cx="12" cy="12" r="3" />
				</svg>
			{/snippet}
		</IconButton>
		<IconButton
			label="Delete"
			onclick={() => onDelete?.(index)}
			variant="ghost"
			class="ml-auto text-muted-foreground hover:text-destructive"
		>
			{#snippet icon()}
				<svg
					xmlns="http://www.w3.org/2000/svg"
					class="h-4 w-4"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="2"
					><polyline points="3 6 5 6 21 6" /><path
						d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"
					/></svg
				>
			{/snippet}
		</IconButton>
	</div>
</div>
