<script lang="ts">
	import Button from "$lib/components/ui/button/Button.svelte";
	import Input from "$lib/components/ui/input/Input.svelte";
	import Label from "$lib/components/ui/label/Label.svelte";
	import Select from "$lib/components/ui/select/Select.svelte";
	import VideoBrowser from "./VideoBrowser.svelte";
	import CaptionSearchPanel from "$lib/components/editors/CaptionSearchPanel.svelte";
	import AnswerChoicesEditor from "$lib/components/editors/AnswerChoicesEditor.svelte";
	import type { Annotation, SkillType } from "$lib/types";

	interface Props {
		open: boolean;
		currentVideoPath?: string;
		currentTime?: string; // Current video time
		onAdd: (annotation: Annotation) => void;
		onCancel: () => void;
	}

	let {
		open,
		currentVideoPath,
		currentTime = "00:00",
		onAdd,
		onCancel,
	}: Props = $props();

	// Video browser state
	let showVideoBrowser = $state(false);

	// Validation state
	let errors = $state<Record<string, string>>({});

	// Default new annotation
	function createEmptyAnnotation(): Annotation {
		return {
			skill: "object_location_memory",
			question: "",
			answer: "",
			question_time_span: { start: currentTime || "00:00", end: "" },
			// Default evidence
			answer_evidence: [
				{
					time_spans: [{ start: "00:00", end: "00:00" }],
					video_path: currentVideoPath,
				},
			],
			time_span: { start: "00:00", end: "00:00" }, // Legacy backfill
			answer_video_path: currentVideoPath, // Legacy backfill
			room: "",
			modalities: [],
			location: { boxes: [] },
			human_review: { status: "pending", reviewed: false },
			video_filename: currentVideoPath
				? currentVideoPath.split("/").pop() || ""
				: "",
			// Answer choices and answerability
			is_answerable: true,
			answer_choices: [
				{ text: "", choice_type: "correct", explanation: "" },
				{ text: "", choice_type: "vague", explanation: "" },
				{ text: "", choice_type: "incorrect", explanation: "" },
			],
			confidence: undefined,
			confidence_reasoning: "",
		};
	}

	let newAnnotation: Annotation = $state(createEmptyAnnotation());

	// Reset form when modal opens
	$effect(() => {
		if (open) {
			newAnnotation = createEmptyAnnotation();
			// Reset validation errors
			errors = {};
		}
	});

	const skillOptions: SkillType[] = [
		"object_location_memory",
		"conversational_memory",
		"visual_recall",
		"timeline_reconstruction",
		"intent_recall",
		"in_context_retrieval",
	];

	function validateForm(): boolean {
		const newErrors: Record<string, string> = {};
		let isValid = true;

		if (!newAnnotation.question?.trim()) {
			newErrors.question = "Question is required";
			isValid = false;
		}

		if (!newAnnotation.answer?.trim()) {
			newErrors.answer = "Answer is required";
			isValid = false;
		}

		if (!newAnnotation.skill) {
			newErrors.skill = "Skill is required";
			isValid = false;
		}

		errors = newErrors;

		if (!isValid) {
			console.error("Validation failed:", newErrors, newAnnotation);
		}

		return isValid;
	}

	function handleAdd() {
		if (validateForm()) {
			onAdd(newAnnotation);
			newAnnotation = createEmptyAnnotation();
			errors = {};
		}
	}

	let browserTargetEvidenceIndex = $state(-1);

	function addEvidence() {
		if (!newAnnotation.answer_evidence) newAnnotation.answer_evidence = [];
		newAnnotation.answer_evidence = [
			...newAnnotation.answer_evidence,
			{
				time_spans: [{ start: "00:00", end: "00:00" }],
				video_path: currentVideoPath, // Defaults to current video
			},
		];
	}

	function removeEvidence(index: number) {
		if (!newAnnotation.answer_evidence) return;
		newAnnotation.answer_evidence = newAnnotation.answer_evidence.filter(
			(_, i) => i !== index,
		);
	}

	function addTimeSpan(evidenceIndex: number) {
		if (!newAnnotation.answer_evidence?.[evidenceIndex]) return;
		if (!newAnnotation.answer_evidence[evidenceIndex].time_spans) {
			newAnnotation.answer_evidence[evidenceIndex].time_spans = [];
		}
		newAnnotation.answer_evidence[evidenceIndex].time_spans.push({
			start: "00:00",
			end: "00:00",
		});
	}

	function removeTimeSpan(evidenceIndex: number, timeSpanIndex: number) {
		if (!newAnnotation.answer_evidence?.[evidenceIndex]?.time_spans) return;
		newAnnotation.answer_evidence[evidenceIndex].time_spans =
			newAnnotation.answer_evidence[evidenceIndex].time_spans!.filter(
				(_, i) => i !== timeSpanIndex,
			);
	}

	function openVideoBrowser(index: number) {
		browserTargetEvidenceIndex = index;
		showVideoBrowser = true;
	}

	function handleVideoSelect(videoPath: string) {
		if (browserTargetEvidenceIndex >= 0) {
			if (
				newAnnotation.answer_evidence &&
				newAnnotation.answer_evidence[browserTargetEvidenceIndex]
			) {
				newAnnotation.answer_evidence[
					browserTargetEvidenceIndex
				].video_path = videoPath;
			}
		}
		// Also update legacy field if it's the first one
		if (browserTargetEvidenceIndex === 0) {
			newAnnotation.answer_video_path = videoPath;
		}

		showVideoBrowser = false;
		browserTargetEvidenceIndex = -1;
	}

	function handleVideoBrowserCancel() {
		showVideoBrowser = false;
		browserTargetEvidenceIndex = -1;
	}

	function getVideoDisplayName(path?: string): string {
		if (!path) return "Current video";
		const parts = path.split("/");
		return parts[parts.length - 1] || path;
	}

	function applyCaptionToQuestion(selection: {
		video_id: string;
		video_path?: string;
		start_time: string;
		end_time: string;
	}) {
		if (!newAnnotation.question_time_span) {
			newAnnotation.question_time_span = { start: "", end: "" };
		}
		newAnnotation.question_time_span.start = selection.start_time;
		newAnnotation.question_time_span.end = selection.end_time;
		const selectedVideoPath = selection.video_path || `${selection.video_id}.mp4`;
		newAnnotation.video_filename = selectedVideoPath.split("/").pop() || selectedVideoPath;
	}

	function applyCaptionToEvidence(
		evidenceIndex: number,
		selection: { video_id: string; video_path?: string; start_time: string; end_time: string }
	) {
		if (!newAnnotation.answer_evidence?.[evidenceIndex]) return;
		const selectedVideoPath = selection.video_path || `${selection.video_id}.mp4`;
		newAnnotation.answer_evidence[evidenceIndex].video_path = selectedVideoPath;
		if (!newAnnotation.answer_evidence[evidenceIndex].time_spans || newAnnotation.answer_evidence[evidenceIndex].time_spans!.length === 0) {
			newAnnotation.answer_evidence[evidenceIndex].time_spans = [{ start: selection.start_time, end: selection.end_time }];
		} else {
			newAnnotation.answer_evidence[evidenceIndex].time_spans![0] = {
				start: selection.start_time,
				end: selection.end_time,
			};
		}
		if (evidenceIndex === 0) {
			newAnnotation.answer_video_path = selectedVideoPath;
			newAnnotation.time_span = { start: selection.start_time, end: selection.end_time };
		}
	}

	const availableModalities = [
		"Gaze",
		"Audio",
		"Trajectory",
		"Depth",
		"Video",
		"OCR",
	];

	function toggleModality(modality: string) {
		if (!newAnnotation.modalities) newAnnotation.modalities = [];

		if (newAnnotation.modalities.includes(modality)) {
			newAnnotation.modalities = newAnnotation.modalities.filter(
				(m) => m !== modality,
			);
		} else {
			newAnnotation.modalities = [...newAnnotation.modalities, modality];
		}
	}

	// Check if using a different video than current
	$effect(() => {
		// Update answer_video_path when currentVideoPath changes and annotation has no custom path
		if (currentVideoPath && !newAnnotation.answer_video_path) {
			newAnnotation.answer_video_path = currentVideoPath;
		}
	});
</script>

{#if open}
	<!-- Modal Backdrop -->
	<div
		class="fixed inset-0 bg-black/50 z-40"
		onclick={onCancel}
		onkeydown={(e) => e.key === "Escape" && onCancel()}
		role="button"
		tabindex="-1"
		aria-label="Close modal"
	></div>

	<!-- Modal Content -->
	<div
		class="fixed inset-4 md:inset-20 bg-white rounded-lg shadow-xl z-50 flex flex-col overflow-hidden max-w-2xl mx-auto"
	>
		<!-- Header -->
		<div
			class="p-4 bg-card border-b border-border flex justify-between items-center"
		>
			<h2 class="text-xl font-bold">Add New Annotation</h2>
			<button
				onclick={onCancel}
				class="text-muted-foreground hover:text-foreground text-2xl leading-none"
				>&times;</button
			>
		</div>

		<!-- Body - Scrollable -->
		<div class="flex-1 overflow-y-auto p-6 space-y-5">
			<!-- Skill -->
			<div class="space-y-2">
				<Label for="newSkill">Skill Type *</Label>
				<Select id="newSkill" bind:value={newAnnotation.skill}>
					{#each skillOptions as skill}
						<option value={skill}>{skill.replace(/_/g, " ")}</option
						>
					{/each}
				</Select>
			</div>

			<!-- Question -->
			<div class="space-y-2">
				<Label
					for="newQuestion"
					class={errors.question ? "text-destructive" : ""}
					>Question *</Label
				>
				<textarea
					id="newQuestion"
					bind:value={newAnnotation.question}
					class={`w-full border rounded-lg p-3 min-h-[80px] focus:ring-2 focus:ring-primary focus:outline-none ${errors.question ? "border-destructive ring-1 ring-destructive" : ""}`}
					placeholder="Enter the question..."
				></textarea>
				{#if errors.question}
					<p class="text-xs text-destructive">{errors.question}</p>
				{/if}
			</div>

			<!-- Question Time Span -->
			<div class="grid grid-cols-2 gap-4">
				<div class="space-y-2">
					<Label for="newQTimeStart">Question Time Start</Label>
					<Input
						id="newQTimeStart"
						type="text"
						value={newAnnotation.question_time_span?.start || ""}
						oninput={(e) => {
							if (!newAnnotation.question_time_span)
								newAnnotation.question_time_span = {
									start: "",
									end: "",
								};
							newAnnotation.question_time_span.start =
								e.currentTarget.value;
						}}
						placeholder="00:00"
					/>
				</div>
				<div class="space-y-2">
					<Label for="newQTimeEnd">Question Time End</Label>
					<Input
						id="newQTimeEnd"
						type="text"
						value={newAnnotation.question_time_span?.end || ""}
						oninput={(e) => {
							if (!newAnnotation.question_time_span)
								newAnnotation.question_time_span = {
									start: "",
									end: "",
								};
							newAnnotation.question_time_span.end =
								e.currentTarget.value;
						}}
						placeholder="00:00"
					/>
				</div>
			</div>
			<div class="space-y-2">
				<Label>Search Question Time Span</Label>
				<CaptionSearchPanel onSelect={applyCaptionToQuestion} />
			</div>

			<!-- Answer -->
			<div class="space-y-2">
				<Label
					for="newAnswer"
					class={errors.answer ? "text-destructive" : ""}>Answer *</Label
				>
				<textarea
					id="newAnswer"
					bind:value={newAnnotation.answer}
					class={`w-full border rounded-lg p-3 min-h-[80px] focus:ring-2 focus:ring-primary focus:outline-none ${errors.answer ? "border-destructive ring-1 ring-destructive" : ""}`}
					placeholder="Enter the answer..."
				></textarea>
				{#if errors.answer}
					<p class="text-xs text-destructive">{errors.answer}</p>
				{/if}
			</div>

			<!-- Answer Choices -->
			<div class="space-y-2">
				<AnswerChoicesEditor
					value={newAnnotation.answer_choices}
					isAnswerable={newAnnotation.is_answerable}
					onChange={(newChoices) => {
						newAnnotation.answer_choices = newChoices;
					}}
					onAnswerableChange={(isAnswerable) => {
						newAnnotation.is_answerable = isAnswerable;
					}}
				/>
			</div>

			<!-- Answer Video & Time Spans (Evidence) -->
			<div class="space-y-4">
				<div class="flex items-center justify-between">
					<Label>Answer Videos & Timespans</Label>
					<Button size="sm" variant="outline" onclick={addEvidence}>
						Add Video/Timespan
					</Button>
				</div>

				{#if newAnnotation.answer_evidence}
					{#each newAnnotation.answer_evidence as evidence, i}
						<div
							class="border rounded-lg p-4 bg-secondary space-y-4 relative"
						>
							<div class="flex items-center justify-between">
								<span class="text-sm font-medium"
									>Answer Segment #{i + 1}</span
								>
								{#if newAnnotation.answer_evidence.length > 1}
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
								<Label>Answer Video File</Label>
								<div class="flex items-center gap-2">
									<div
										class="flex-1 p-2 bg-white rounded border text-sm font-mono truncate"
										title={evidence.video_path ||
											currentVideoPath}
									>
										🎥 {getVideoDisplayName(
											evidence.video_path ||
												currentVideoPath,
										)}
										{#if evidence.video_path && evidence.video_path !== currentVideoPath}
											<span
												class="text-primary text-xs ml-1"
												>(different video)</span
											>
										{:else if !evidence.video_path}
											<span
												class="text-muted-foreground text-xs ml-1"
												>(current video)</span
											>
										{/if}
									</div>
									<Button
										variant="secondary"
										size="sm"
										onclick={() => openVideoBrowser(i)}
									>
										Change...
									</Button>
								</div>
							</div>

							<!-- Time Spans -->
							<div class="space-y-3">
								<div class="flex items-center justify-between">
									<Label>Time Spans</Label>
									<Button
										size="sm"
										variant="ghost"
										class="h-6 text-xs"
										onclick={() => addTimeSpan(i)}
									>
										Add Time Span
									</Button>
								</div>

								{#if evidence.time_spans && evidence.time_spans.length > 0}
									{#each evidence.time_spans as span, j}
										<div class="flex items-end gap-2">
											<div
												class="grid grid-cols-2 gap-2 flex-1"
											>
												<div class="space-y-1">
													<span
														class="text-xs text-gray-500"
														>Start</span
													>
													<Input
														type="text"
														value={span.start || ""}
														oninput={(e) => {
															if (
																newAnnotation
																	.answer_evidence?.[
																	i
																]?.time_spans?.[
																	j
																]
															) {
																newAnnotation.answer_evidence[
																	i
																].time_spans[
																	j
																].start =
																	e.currentTarget.value;
															}
														}}
														placeholder="00:00"
														class="h-8 text-sm"
													/>
												</div>
												<div class="space-y-1">
													<span
														class="text-xs text-gray-500"
														>End</span
													>
													<Input
														type="text"
														value={span.end || ""}
														oninput={(e) => {
															if (
																newAnnotation
																	.answer_evidence?.[
																	i
																]?.time_spans?.[
																	j
																]
															) {
																newAnnotation.answer_evidence[
																	i
																].time_spans[
																	j
																].end =
																	e.currentTarget.value;
															}
														}}
														placeholder="00:00"
														class="h-8 text-sm"
													/>
												</div>
											</div>
											{#if evidence.time_spans.length > 1}
												<Button
													size="sm"
													variant="ghost"
													class="text-destructive hover:text-destructive/80 h-8 w-8 p-0"
													onclick={() =>
														removeTimeSpan(i, j)}
													title="Remove time span"
												>
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
												</Button>
											{/if}
										</div>
									{/each}
								{:else}
									<div class="text-xs text-muted-foreground italic">
										No time spans added.
									</div>
								{/if}
							</div>
							<div class="space-y-2">
								<Label>Search Evidence Time Span</Label>
								<CaptionSearchPanel onSelect={(selection) => applyCaptionToEvidence(i, selection)} />
							</div>
						</div>
					{/each}
				{/if}
			</div>

			<!-- Confidence -->
			<div class="grid grid-cols-2 gap-4">
				<div class="space-y-2">
					<Label for="newConfidence">Confidence</Label>
					<Input
						id="newConfidence"
						type="number"
						step="0.01"
						min="0"
						max="1"
						value={newAnnotation.confidence !== undefined ? String(newAnnotation.confidence) : ""}
						oninput={(e) => {
							const val = e.currentTarget.value;
							newAnnotation.confidence = val ? parseFloat(val) : undefined;
						}}
						placeholder="0.0 - 1.0"
						class="h-8 text-sm"
					/>
				</div>
				<div class="space-y-2">
					<Label for="newConfidenceReasoning">Confidence Reasoning</Label>
					<Input
						id="newConfidenceReasoning"
						type="text"
						bind:value={newAnnotation.confidence_reasoning}
						placeholder="Reasoning for the confidence score..."
						class="h-8 text-sm"
					/>
				</div>
			</div>

			<!-- Room -->
			<div class="space-y-2">
				<Label for="newRoom">Room / Location</Label>
				<Input
					id="newRoom"
					type="text"
					bind:value={newAnnotation.room}
					placeholder="e.g., Kitchen, Living Room"
				/>
			</div>

			<!-- Modalities -->
			<div class="space-y-2">
				<Label>Modalities</Label>
				<div class="grid grid-cols-2 gap-2 mt-1">
					{#each availableModalities as modality}
						<div class="flex items-center space-x-2">
							<input
								type="checkbox"
								id={`new-modality-${modality}`}
								checked={newAnnotation.modalities?.includes(
									modality,
								)}
								onchange={() => toggleModality(modality)}
								class="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
							/>
							<Label
								for={`new-modality-${modality}`}
								class="font-normal cursor-pointer"
							>
								{modality}
							</Label>
						</div>
					{/each}
				</div>
			</div>
		</div>

		<!-- Footer -->
		<div class="border-t px-6 py-4 flex justify-end gap-3 bg-secondary">
			<Button variant="secondary" onclick={onCancel}>Cancel</Button>
			<Button onclick={handleAdd}>Add Annotation</Button>
		</div>
	</div>
{/if}

<!-- Video Browser Modal -->
{#if showVideoBrowser}
	<VideoBrowser
		onSelect={handleVideoSelect}
		onCancel={handleVideoBrowserCancel}
		{currentVideoPath}
	/>
{/if}
