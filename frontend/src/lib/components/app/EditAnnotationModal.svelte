<script lang="ts">
	// NEW MODULAR ARCHITECTURE: Using editor components from the visualizer registry system
	import TextEditor from "$lib/components/editors/TextEditor.svelte";
	import TimeSpanEditor from "$lib/components/editors/TimeSpanEditor.svelte";
	import SkillTypeEditor from "$lib/components/editors/SkillTypeEditor.svelte";
	import ModalityEditor from "$lib/components/editors/ModalityEditor.svelte";
	import HumanReviewEditor from "$lib/components/editors/HumanReviewEditor.svelte";
	import AnswerChoicesEditor from "$lib/components/editors/AnswerChoicesEditor.svelte";

	// Legacy UI components still needed for complex sections
	import Button from "$lib/components/ui/button/Button.svelte";
	import Input from "$lib/components/ui/input/Input.svelte";
	import Label from "$lib/components/ui/label/Label.svelte";
	import VideoBrowser from "./VideoBrowser.svelte";
	import CaptionSearchPanel from "$lib/components/editors/CaptionSearchPanel.svelte";

	// Types and utilities
	import type { Annotation, BoundingBox, SkillType } from "$lib/types";
	import { deepClone } from "$lib/utils";
	import { untrack } from "svelte";
	import {
		annotationFieldToData,
		updateAnnotationFromData,
	} from "$lib/utils/annotation-converter";
	import type {
		TextData,
		TimeSpanData,
		SkillTypeData,
		ModalityListData,
		HumanReviewData,
		AnswerChoicesData,
	} from "$lib/types/annotation-data-types";

	interface Props {
		annotation: Annotation | null;
		open: boolean;
		currentVideoPath?: string;
		onSave: (annotation: Annotation) => void;
		onCancel: () => void;
	}

	let { annotation, open, currentVideoPath, onSave, onCancel }: Props =
		$props();

	// Local state for editing
	let editedAnnotation: Annotation | null = $state(null);
	let newBoxTimestamp = $state("00:00");
	let newBoxVideoPath = $state<string>("");
	let newBoxCoords = $state([0, 0, 100, 100]); // [x1, y1, x2, y2]

	// Video browser state
	let showVideoBrowser = $state(false);
	let browserTargetEvidenceIndex = $state(-1); // -1 means none, >=0 means updating specific evidence

	// Reset form when annotation changes
	$effect(() => {
		if (annotation && open) {
			untrack(() => {
				editedAnnotation = deepClone(annotation);

				// Migrate legacy fields to answer_evidence if needed
				if (
					!editedAnnotation?.answer_evidence ||
					editedAnnotation.answer_evidence.length === 0
				) {
					if (
						editedAnnotation?.time_span ||
						editedAnnotation?.answer_video_path
					) {
						if (!editedAnnotation) return; // Should not happen
						editedAnnotation.answer_evidence = [
							{
								time_spans: [
									editedAnnotation.time_span || {
										start: "",
										end: "",
									},
								],
								video_path: editedAnnotation.answer_video_path,
							},
						];
					} else if (editedAnnotation) {
						editedAnnotation.answer_evidence = [
							{
								time_spans: [{ start: "", end: "" }],
								video_path: undefined,
							},
						];
					}
				} else {
					// Check if existing evidence needs migration (legacy time_span to time_spans)
					// Use any cast to check legacy prop
					editedAnnotation.answer_evidence =
						editedAnnotation.answer_evidence.map((ev) => {
							const legacyEv = ev as any;
							if (legacyEv.time_span && !ev.time_spans) {
								return {
									...ev,
									time_spans: [legacyEv.time_span],
									time_span: undefined, // clean up
								};
							}
							// Ensure time_spans exists
							if (!ev.time_spans) {
								return {
									...ev,
									time_spans: [{ start: "", end: "" }],
								};
							}
							return ev;
						});
				}

				// Ensure all boxes have a stream value
				if (editedAnnotation?.location?.boxes) {
					editedAnnotation.location.boxes.forEach((box) => {
						if (!box.stream) box.stream = "question";
					});
				}

				// Backfill video_path for boxes if missing (assume question stream -> current video)
				if (editedAnnotation?.location?.boxes && currentVideoPath) {
					editedAnnotation.location.boxes.forEach((box) => {
						if (!box.video_path) {
							// For now, default to current if unknown
							box.video_path = currentVideoPath;
						}
					});
				}

				// Initialize new box video path to current video
				if (currentVideoPath) {
					newBoxVideoPath = currentVideoPath;
				}
			});
		}
	});

	// Compute available unique video sources
	const availableVideoSources = $derived.by(() => {
		const sources = new Set<string>();
		// Always include current video (question source)
		if (currentVideoPath) sources.add(currentVideoPath);

		// Add evidence videos
		if (editedAnnotation?.answer_evidence) {
			editedAnnotation.answer_evidence.forEach((ev) => {
				if (ev.video_path) sources.add(ev.video_path);
				else if (currentVideoPath) sources.add(currentVideoPath);
			});
		}

		return Array.from(sources);
	});

	const editingEvidenceList = $derived(
		(editedAnnotation as any)?.answer_evidence &&
			(editedAnnotation as any).answer_evidence.length > 0
			? (editedAnnotation as any).answer_evidence
			: (editedAnnotation as any)?.answer?.evidence_list || [],
	);

	/** Collect all existing evidence time spans for overlap detection */
	const allEvidenceTimeSpans = $derived.by(() => {
		const spans: import('$lib/types').TimeSpan[] = [];
		for (const ev of editingEvidenceList) {
			if (ev.time_spans) {
				for (const ts of ev.time_spans) {
					if (ts.start || ts.end) spans.push(ts);
				}
			}
		}
		return spans;
	});

	function ensureEvBBox2d(evidenceIndex: number, boxIndex: number) {
		const ev = editingEvidenceList[evidenceIndex];
		if (
			ev?.bounding_boxes?.[boxIndex] &&
			!(ev.bounding_boxes[boxIndex] as any).box_2d
		) {
			// Check if it's pipeline_v2 format (ymin, xmin, etc)
			const bb = ev.bounding_boxes[boxIndex] as any;
			if (bb.ymin !== undefined) {
				bb.box_2d = [bb.ymin, bb.xmin, bb.ymax, bb.xmax];
			} else {
				bb.box_2d = [0, 0, 100, 100];
			}
		}
	}

	function updateEvBBoxCoord(
		evidenceIndex: number,
		boxIndex: number,
		coordIndex: number,
		value: number,
	) {
		if (!editedAnnotation) return;

		const ev = editingEvidenceList[evidenceIndex];
		if (!ev?.bounding_boxes?.[boxIndex]) return;

		ensureEvBBox2d(evidenceIndex, boxIndex);

		const bb = ev.bounding_boxes[boxIndex] as any;
		if (bb.box_2d) {
			bb.box_2d[coordIndex] = value;
		}

		// Also update pipeline_v2 fields for sync
		if (bb.ymin !== undefined || bb.xmin !== undefined) {
			if (coordIndex === 0) bb.ymin = value;
			if (coordIndex === 1) bb.xmin = value;
			if (coordIndex === 2) bb.ymax = value;
			if (coordIndex === 3) bb.xmax = value;
		}

		// Force reactivity by creating a new reference to the edited annotation
		// This ensures Svelte detects the change
		editedAnnotation = { ...editedAnnotation };
	}

	function addEvBoundingBox(evidenceIndex: number) {
		const ev = editingEvidenceList[evidenceIndex];
		if (!ev) return;

		if (!ev.bounding_boxes) {
			ev.bounding_boxes = [];
		}

		// Detect schema
		const isPipelineV2 =
			(ev as any).video_id !== undefined ||
			(editedAnnotation?.answer as any)?.evidence_list;

		if (isPipelineV2) {
			ev.bounding_boxes = [
				...ev.bounding_boxes,
				{
					ymin: 0,
					xmin: 0,
					ymax: 100,
					xmax: 100,
					label: "",
					time_offset: "",
					// Add box_2d for UI compatibility
					box_2d: [0, 0, 100, 100],
					description: "",
				} as any,
			];
		} else {
			ev.bounding_boxes = [
				...ev.bounding_boxes,
				{
					box_2d: [0, 0, 100, 100],
					timestamp: "",
					description: "",
					video_path: ev.video_path || currentVideoPath,
				},
			];
		}
	}

	function handleSave() {
		if (editedAnnotation) {
			// Back-fill legacy fields for compatibility if needed (optional)
			if (
				editedAnnotation.answer_evidence &&
				editedAnnotation.answer_evidence.length > 0
			) {
				const primary = editedAnnotation.answer_evidence[0];
				if (primary.time_spans && primary.time_spans.length > 0) {
					editedAnnotation.time_span = primary.time_spans[0];
				}
				editedAnnotation.answer_video_path = primary.video_path;
			}
			onSave(editedAnnotation);
		}
	}

	function addEvidence() {
		if (!editedAnnotation) return;
		if (!editedAnnotation.answer_evidence)
			editedAnnotation.answer_evidence = [];
		editedAnnotation.answer_evidence = [
			...editedAnnotation.answer_evidence,
			{
				time_spans: [{ start: "", end: "" }],
				video_path: undefined, // Defaults to current video
			},
		];
	}

	function addTimeSpan(evidenceIndex: number) {
		const ev = editingEvidenceList[evidenceIndex] as any;
		if (ev) {
			if (!ev.time_spans) ev.time_spans = [];
			ev.time_spans = [...ev.time_spans, { start: "", end: "" }];
		}
	}

	function removeTimeSpan(evidenceIndex: number, timeSpanIndex: number) {
		const ev = editingEvidenceList[evidenceIndex] as any;
		if (ev?.time_spans) {
			ev.time_spans = ev.time_spans.filter(
				(_: any, i: number) => i !== timeSpanIndex,
			);
		} else if (ev?.time_span && timeSpanIndex === 0) {
			delete ev.time_span;
		}
	}

	function removeEvidence(index: number) {
		if ((editedAnnotation as any)?.answer_evidence) {
			(editedAnnotation as any).answer_evidence = (
				editedAnnotation as any
			).answer_evidence.filter((_: any, i: number) => i !== index);
		} else if ((editedAnnotation as any)?.answer?.evidence_list) {
			(editedAnnotation as any).answer.evidence_list = (
				editedAnnotation as any
			).answer.evidence_list.filter((_: any, i: number) => i !== index);
		}
	}

	function addBoundingBox() {
		if (!editedAnnotation) return;

		// Legacy
		if (editedAnnotation.location) {
			if (!editedAnnotation.location.boxes)
				editedAnnotation.location.boxes = [];
			editedAnnotation.location.boxes = [
				...editedAnnotation.location.boxes,
				{
					timestamp: newBoxTimestamp,
					video_path: newBoxVideoPath,
					box_2d: [...newBoxCoords],
				},
			];
		}
		// pipeline_v2
		else if (
			editedAnnotation &&
			(editedAnnotation.question as any)?.bounding_boxes
		) {
			const q = (editedAnnotation as any).question;
			q.bounding_boxes = [
				...q.bounding_boxes,
				{
					ymin: newBoxCoords[0],
					xmin: newBoxCoords[1],
					ymax: newBoxCoords[2],
					xmax: newBoxCoords[3],
					label: "",
					time_offset: newBoxTimestamp,
				},
			];
		}
		// Reset form
		newBoxCoords = [0, 0, 100, 100];
	}

	function removeBoundingBox(index: number) {
		if (editedAnnotation?.location?.boxes) {
			editedAnnotation.location.boxes =
				editedAnnotation.location.boxes.filter((_, i) => i !== index);
		} else if (
			editedAnnotation &&
			(editedAnnotation as any).question?.bounding_boxes
		) {
			const q = (editedAnnotation as any).question;
			q.bounding_boxes = q.bounding_boxes.filter(
				(_: any, i: number) => i !== index,
			);
		}
	}

	function updateBoxCoord(
		boxIndex: number,
		coordIndex: number,
		value: number,
	) {
		if (editedAnnotation?.location?.boxes?.[boxIndex]) {
			const box = editedAnnotation.location.boxes[boxIndex];
			if (!box.box_2d) box.box_2d = [0, 0, 100, 100];
			box.box_2d[coordIndex] = value;
		} else if (
			(editedAnnotation?.question as any)?.bounding_boxes?.[boxIndex]
		) {
			const bb = (editedAnnotation?.question as any).bounding_boxes[
				boxIndex
			];
			if (coordIndex === 0) bb.ymin = value;
			if (coordIndex === 1) bb.xmin = value;
			if (coordIndex === 2) bb.ymax = value;
			if (coordIndex === 3) bb.xmax = value;
		}
	}

	function updateBoxVideoPath(boxIndex: number, path: string) {
		if (editedAnnotation?.location?.boxes?.[boxIndex]) {
			editedAnnotation.location.boxes[boxIndex].video_path = path;
		} else if (
			editedAnnotation &&
			(editedAnnotation.question as any)?.video_id !== undefined
		) {
			(editedAnnotation.question as any).video_id = path;
		}
	}

	function openVideoBrowser(evidenceIndex: number) {
		browserTargetEvidenceIndex = evidenceIndex;
		showVideoBrowser = true;
	}

	function handleVideoSelect(videoPath: string) {
		if (editedAnnotation && browserTargetEvidenceIndex >= 0) {
			const ev = editingEvidenceList[browserTargetEvidenceIndex] as any;
			if (ev) {
				ev.video_path = videoPath;
				if (ev.video_id !== undefined) ev.video_id = videoPath;
			}
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
		if (!editedAnnotation) return;
		editedAnnotation.question_time_span = {
			start: selection.start_time,
			end: selection.end_time,
		};
		const selectedVideoPath = selection.video_path || `${selection.video_id}.mp4`;
		editedAnnotation.video_filename = selectedVideoPath.split("/").pop() || selectedVideoPath;
		editedAnnotation = { ...editedAnnotation };
	}

	function applyCaptionToEvidence(
		evidenceIndex: number,
		selection: { video_id: string; video_path?: string; start_time: string; end_time: string }
	) {
		if (!editedAnnotation) return;
		const ev = editingEvidenceList[evidenceIndex] as any;
		if (!ev) return;
		const selectedVideoPath = selection.video_path || `${selection.video_id}.mp4`;
		ev.video_path = selectedVideoPath;
		if (ev.video_id !== undefined) ev.video_id = selectedVideoPath;
		if (!ev.time_spans || ev.time_spans.length === 0) {
			ev.time_spans = [{ start: selection.start_time, end: selection.end_time }];
		} else {
			ev.time_spans[0] = { start: selection.start_time, end: selection.end_time };
		}
		if (evidenceIndex === 0) {
			editedAnnotation.answer_video_path = selectedVideoPath;
			editedAnnotation.time_span = { start: selection.start_time, end: selection.end_time };
		}
		editedAnnotation = { ...editedAnnotation };
	}
</script>

{#if open && editedAnnotation}
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
		class="fixed inset-4 md:inset-10 bg-white rounded-lg shadow-xl z-50 flex flex-col overflow-hidden"
	>
		<!-- Header -->
		<div
			class="p-4 bg-card border-b border-border flex justify-between items-center"
		>
			<h2 class="text-xl font-bold">Edit Annotation</h2>
			<button
				onclick={onCancel}
				class="text-muted-foreground hover:text-foreground text-2xl leading-none"
				>&times;</button
			>
		</div>

		<!-- Body - Scrollable -->
		<div class="flex-1 overflow-y-auto p-6 space-y-6">
			<!-- Skill - USING NEW MODULAR EDITOR -->
			<div class="space-y-2">
				<SkillTypeEditor
					data={annotationFieldToData(
						editedAnnotation,
						"skill",
					) as SkillTypeData}
					label="Skill Type"
					onChange={(newData) => {
						if (editedAnnotation) {
							editedAnnotation = updateAnnotationFromData(
								editedAnnotation,
								"skill",
								newData,
							);
						}
					}}
				/>
			</div>

			<!-- Question - USING NEW MODULAR EDITOR -->
			<div class="space-y-2">
				<TextEditor
					data={annotationFieldToData(
						editedAnnotation,
						"question",
					) as TextData}
					label="Question"
					multiline={true}
					placeholder="Enter the question..."
					onChange={(newData) => {
						if (editedAnnotation) {
							editedAnnotation = updateAnnotationFromData(
								editedAnnotation,
								"question",
								newData,
							);
						}
					}}
				/>
			</div>

			<!-- Question Reasoning -->
			{#if editedAnnotation.question_details}
				<div class="space-y-2">
					<Label>Question Reasoning</Label>
					<textarea
						class="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring min-h-[60px] resize-y"
						value={editedAnnotation.question_details?.question_reasoning || ""}
						oninput={(e) => {
							if (editedAnnotation && editedAnnotation.question_details) {
								(editedAnnotation.question_details as any).question_reasoning = e.currentTarget.value;
							}
						}}
						placeholder="Reasoning behind why this question was generated..."
					></textarea>
				</div>
			{/if}

			<!-- Question Time Span - USING NEW MODULAR EDITOR -->
			<div class="space-y-2">
				<TimeSpanEditor
					data={annotationFieldToData(
						editedAnnotation,
						"question_time_span",
					) as TimeSpanData}
					label="Question Time Span"
					onChange={(newData) => {
						if (editedAnnotation) {
							editedAnnotation = updateAnnotationFromData(
								editedAnnotation,
								"question_time_span",
								newData,
							);
						}
					}}
				/>
				<CaptionSearchPanel onSelect={applyCaptionToQuestion} />
			</div>

			<!-- Answer - USING NEW MODULAR EDITOR -->
			<div class="space-y-2">
				<TextEditor
					data={annotationFieldToData(
						editedAnnotation,
						"answer",
					) as TextData}
					label="Answer"
					multiline={true}
					placeholder="Enter the answer..."
					onChange={(newData) => {
						if (editedAnnotation) {
							editedAnnotation = updateAnnotationFromData(
								editedAnnotation,
								"answer",
								newData,
							);
						}
					}}
				/>
			</div>

			<!-- Answer Choices - NEW MODULAR EDITOR -->
			<div class="space-y-2">
				<AnswerChoicesEditor
					value={editedAnnotation?.answer_choices}
					isAnswerable={editedAnnotation?.is_answerable}
					onChange={(newChoices) => {
						if (editedAnnotation) {
							const choicesData: AnswerChoicesData = {
								type: 'ANSWER_CHOICES' as any,
								value: newChoices,
								isAnswerable: editedAnnotation.is_answerable ?? true,
							};
							editedAnnotation = updateAnnotationFromData(
								editedAnnotation,
								"answer_choices",
								choicesData,
							);
						}
					}}
					onAnswerableChange={(isAnswerable) => {
						if (editedAnnotation) {
							const choicesData: AnswerChoicesData = {
								type: 'ANSWER_CHOICES' as any,
								value: editedAnnotation.answer_choices,
								isAnswerable: isAnswerable,
							};
							editedAnnotation = updateAnnotationFromData(
								editedAnnotation,
								"answer_choices",
								choicesData,
							);
						}
					}}
				/>
			</div>

			<!-- Room - USING NEW MODULAR EDITOR -->
			<div class="space-y-2">
				<TextEditor
					data={annotationFieldToData(
						editedAnnotation,
						"room",
					) as TextData}
					label="Room / Location"
					placeholder="e.g., Kitchen, Living Room"
					onChange={(newData) => {
						if (editedAnnotation) {
							editedAnnotation = updateAnnotationFromData(
								editedAnnotation,
								"room",
								newData,
							);
						}
					}}
				/>
			</div>

			<!-- Modalities - USING NEW MODULAR EDITOR -->
			<div class="space-y-2">
				<ModalityEditor
					data={annotationFieldToData(
						editedAnnotation,
						"modalities",
					) as ModalityListData}
					label="Question Modalities"
					onChange={(newData) => {
						if (editedAnnotation) {
							editedAnnotation = updateAnnotationFromData(
								editedAnnotation,
								"modalities",
								newData,
							);
						}
					}}
				/>
			</div>

			<!-- Confidence -->
			<div class="space-y-2">
				<Label>Confidence</Label>
				<Input
					type="number"
					step="0.01"
					min="0"
					max="1"
					value={editedAnnotation.confidence !== undefined
						? String(editedAnnotation.confidence)
						: ""}
					oninput={(e) => {
						if (editedAnnotation) {
							const val = e.currentTarget.value;
							editedAnnotation.confidence = val
								? parseFloat(val)
								: undefined;
						}
					}}
					placeholder="0.0 - 1.0"
					class="h-8 text-sm"
				/>
			</div>

			<!-- Confidence Reasoning -->
			<div class="space-y-2">
				<Label>Confidence Reasoning</Label>
				<textarea
					class="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring min-h-[60px] resize-y"
					value={editedAnnotation.confidence_reasoning || ""}
					oninput={(e) => {
						if (editedAnnotation) {
							editedAnnotation.confidence_reasoning =
								e.currentTarget.value;
						}
					}}
					placeholder="Reasoning for the confidence score..."
				></textarea>
			</div>

			<!-- Verification Score (read-only) -->
			{#if editedAnnotation.verification_score}
				<div class="space-y-2 bg-secondary/50 rounded-lg p-4 border">
					<Label>🔍 Verification Score (read-only)</Label>
					<div class="text-sm space-y-2">
						{#if editedAnnotation.verification_score.factual_correctness_score !== undefined}
							<div class="flex items-center gap-2">
								<span class="text-muted-foreground w-24">Factual:</span>
								<div class="flex-1 bg-muted rounded-full h-2 overflow-hidden">
									<div
										class="h-full rounded-full {(editedAnnotation.verification_score.factual_correctness_score ?? 0) >= 0.7 ? 'bg-emerald-500' : 'bg-red-500'}"
										style="width: {(editedAnnotation.verification_score.factual_correctness_score ?? 0) * 100}%"
									></div>
								</div>
								<span class="font-mono w-10 text-right">{editedAnnotation.verification_score.factual_correctness_score?.toFixed(2)}</span>
							</div>
						{/if}
						{#if editedAnnotation.verification_score.causal_answerability_score !== undefined}
							<div class="flex items-center gap-2">
								<span class="text-muted-foreground w-24">Causal:</span>
								<div class="flex-1 bg-muted rounded-full h-2 overflow-hidden">
									<div
										class="h-full rounded-full {(editedAnnotation.verification_score.causal_answerability_score ?? 0) >= 0.7 ? 'bg-emerald-500' : 'bg-red-500'}"
										style="width: {(editedAnnotation.verification_score.causal_answerability_score ?? 0) * 100}%"
									></div>
								</div>
								<span class="font-mono w-10 text-right">{editedAnnotation.verification_score.causal_answerability_score?.toFixed(2)}</span>
							</div>
						{/if}
						{#if editedAnnotation.verification_score.question_naturalness_score !== undefined}
							<div class="flex items-center gap-2">
								<span class="text-muted-foreground w-24">Naturalness:</span>
								<div class="flex-1 bg-muted rounded-full h-2 overflow-hidden">
									<div
										class="h-full rounded-full {(editedAnnotation.verification_score.question_naturalness_score ?? 0) >= 0.7 ? 'bg-emerald-500' : 'bg-red-500'}"
										style="width: {(editedAnnotation.verification_score.question_naturalness_score ?? 0) * 100}%"
									></div>
								</div>
								<span class="font-mono w-10 text-right">{editedAnnotation.verification_score.question_naturalness_score?.toFixed(2)}</span>
							</div>
						{/if}
						{#if editedAnnotation.verification_score.temporal_grounding_score !== undefined}
							<div class="flex items-center gap-2">
								<span class="text-muted-foreground w-24">Temporal:</span>
								<div class="flex-1 bg-muted rounded-full h-2 overflow-hidden">
									<div
										class="h-full rounded-full {(editedAnnotation.verification_score.temporal_grounding_score ?? 0) >= 0.7 ? 'bg-emerald-500' : 'bg-red-500'}"
										style="width: {(editedAnnotation.verification_score.temporal_grounding_score ?? 0) * 100}%"
									></div>
								</div>
								<span class="font-mono w-10 text-right">{editedAnnotation.verification_score.temporal_grounding_score?.toFixed(2)}</span>
							</div>
						{/if}
						{#if editedAnnotation.verification_score.objective_correctness_score !== undefined}
							<div class="flex items-center gap-2 opacity-50">
								<span class="text-muted-foreground w-24">Objective (O):</span>
								<div class="flex-1 bg-muted rounded-full h-2 overflow-hidden">
									<div
										class="h-full rounded-full {(editedAnnotation.verification_score.objective_correctness_score ?? 0) >= 0.7 ? 'bg-emerald-500' : 'bg-red-500'}"
										style="width: {(editedAnnotation.verification_score.objective_correctness_score ?? 0) * 100}%"
									></div>
								</div>
								<span class="font-mono w-10 text-right">{editedAnnotation.verification_score.objective_correctness_score?.toFixed(2)}</span>
							</div>
						{/if}
						{#if editedAnnotation.verification_score.is_correct !== undefined}
							<div class="flex items-center gap-1">
								<span class="text-muted-foreground">Correct:</span>
								<span class="{editedAnnotation.verification_score.is_correct ? 'text-emerald-600' : 'text-red-600'} font-semibold">
									{editedAnnotation.verification_score.is_correct ? '✓ Yes' : '✗ No'}
								</span>
							</div>
						{/if}
						{#if editedAnnotation.verification_score.factual_correctness_reasoning}
							<div class="text-xs text-muted-foreground"><strong>Factual:</strong> {editedAnnotation.verification_score.factual_correctness_reasoning}</div>
						{/if}
						{#if editedAnnotation.verification_score.causal_answerability_reasoning}
							<div class="text-xs text-muted-foreground"><strong>Causal:</strong> {editedAnnotation.verification_score.causal_answerability_reasoning}</div>
						{/if}
						{#if editedAnnotation.verification_score.question_naturalness_reasoning}
							<div class="text-xs text-muted-foreground"><strong>Naturalness:</strong> {editedAnnotation.verification_score.question_naturalness_reasoning}</div>
						{/if}
						{#if editedAnnotation.verification_score.temporal_grounding_reasoning}
							<div class="text-xs text-muted-foreground"><strong>Temporal:</strong> {editedAnnotation.verification_score.temporal_grounding_reasoning}</div>
						{/if}
						{#if editedAnnotation.verification_score.objective_correctness_reasoning}
							<div class="text-xs text-muted-foreground opacity-50"><strong>Objective (Old):</strong> {editedAnnotation.verification_score.objective_correctness_reasoning}</div>
						{/if}
						{#if editedAnnotation.verification_score.privacy_violation}
							<div class="text-xs font-bold text-red-600 bg-red-50 p-1 border border-red-200 rounded">PRIVACY VIOLATION DETECTED</div>
						{/if}
					</div>
				</div>
			{/if}

			<!-- Bounding Boxes (question-level) -->
			<div class="space-y-4">
				<div class="flex items-center justify-between">
					<Label>📦 Bounding Boxes</Label>
					<span class="text-sm text-muted-foreground">
						{editedAnnotation.location?.boxes?.length || 0} boxes
					</span>
				</div>

				<!-- Existing boxes -->
				{#if editedAnnotation.location?.boxes && editedAnnotation.location.boxes.length > 0}
					<div class="space-y-3">
						{#each editedAnnotation.location.boxes as box, i}
							<div class="border rounded-lg p-3 bg-secondary">
								<div
									class="flex items-center justify-between mb-2"
								>
									<span class="font-medium text-sm"
										>Box #{i + 1}</span
									>
									<Button
										size="sm"
										variant="destructive"
										onclick={() => removeBoundingBox(i)}
									>
										Remove
									</Button>
								</div>
								<div class="grid grid-cols-6 gap-2 text-sm">
									<div>
										<Label>Timestamp</Label>
										<Input
											type="text"
											value={box.timestamp || ""}
											oninput={(e) => {
												if (
													editedAnnotation?.location
														?.boxes?.[i]
												) {
													editedAnnotation.location.boxes[
														i
													].timestamp =
														e.currentTarget.value;
												}
											}}
											placeholder="00:00"
										/>
									</div>
									<div>
										<Label>Video Source</Label>
										<select
											class="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
											value={box.video_path ||
												currentVideoPath}
											onchange={(e) =>
												updateBoxVideoPath(
													i,
													e.currentTarget.value,
												)}
										>
											{#each availableVideoSources as source}
												<option value={source}>
													{getVideoDisplayName(
														source,
													)}
													{source === currentVideoPath
														? "(Question)"
														: ""}
												</option>
											{/each}
										</select>
									</div>
									<div>
										<Label>Y1</Label>
										<Input
											type="text"
											value={String(box.box_2d?.[0] || 0)}
											oninput={(e) =>
												updateBoxCoord(
													i,
													0,
													parseInt(
														e.currentTarget.value,
													) || 0,
												)}
										/>
									</div>
									<div>
										<Label>X1</Label>
										<Input
											type="text"
											value={String(box.box_2d?.[1] || 0)}
											oninput={(e) =>
												updateBoxCoord(
													i,
													1,
													parseInt(
														e.currentTarget.value,
													) || 0,
												)}
										/>
									</div>
									<div>
										<Label>Y2</Label>
										<Input
											type="text"
											value={String(box.box_2d?.[2] || 0)}
											oninput={(e) =>
												updateBoxCoord(
													i,
													2,
													parseInt(
														e.currentTarget.value,
													) || 0,
												)}
										/>
									</div>
									<div>
										<Label>X2</Label>
										<Input
											type="text"
											value={String(box.box_2d?.[3] || 0)}
											oninput={(e) =>
												updateBoxCoord(
													i,
													3,
													parseInt(
														e.currentTarget.value,
													) || 0,
												)}
										/>
									</div>
								</div>
							</div>
						{/each}
					</div>
				{/if}

				<!-- Add new box -->
				<div class="border-2 border-dashed rounded-lg p-4 bg-secondary">
					<p class="text-sm font-medium mb-3">Add New Bounding Box</p>
					<div class="grid grid-cols-6 gap-2 text-sm mb-3">
						<div>
							<Label>Timestamp</Label>
							<Input
								type="text"
								bind:value={newBoxTimestamp}
								placeholder="00:00"
							/>
						</div>
						<div>
							<Label>Video Source</Label>
							<select
								class="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
								bind:value={newBoxVideoPath}
							>
								{#each availableVideoSources as source}
									<option value={source}>
										{getVideoDisplayName(source)}
										{source === currentVideoPath
											? "(Question)"
											: ""}
									</option>
								{/each}
							</select>
						</div>
						<div>
							<Label>Y1</Label>
							<Input
								type="text"
								value={String(newBoxCoords[0])}
								oninput={(e) => {
									newBoxCoords[0] =
										parseInt(e.currentTarget.value) || 0;
								}}
							/>
						</div>
						<div>
							<Label>X1</Label>
							<Input
								type="text"
								value={String(newBoxCoords[1])}
								oninput={(e) => {
									newBoxCoords[1] =
										parseInt(e.currentTarget.value) || 0;
								}}
							/>
						</div>
						<div>
							<Label>Y2</Label>
							<Input
								type="text"
								value={String(newBoxCoords[2])}
								oninput={(e) => {
									newBoxCoords[2] =
										parseInt(e.currentTarget.value) || 0;
								}}
							/>
						</div>
						<div>
							<Label>X2</Label>
							<Input
								type="text"
								value={String(newBoxCoords[3])}
								oninput={(e) => {
									newBoxCoords[3] =
										parseInt(e.currentTarget.value) || 0;
								}}
							/>
						</div>
					</div>
					<Button size="sm" onclick={addBoundingBox}
						>➕ Add Box</Button
					>
				</div>
			</div>

			<!-- Answer Evidence Segments -->
			<div class="space-y-4">
				<div class="flex items-center justify-between">
					<Label>Answer Evidence</Label>
					<Button size="sm" variant="outline" onclick={addEvidence}>
						➕ Add Evidence
					</Button>
				</div>

				{#if editingEvidenceList.length > 0}
					{#each editingEvidenceList as evidence, i}
						<div
							class="border rounded-lg p-4 bg-secondary space-y-4 relative"
						>
							<div class="flex items-center justify-between">
								<span class="text-sm font-medium"
									>Evidence #{i + 1}</span
								>
								{#if editingEvidenceList.length > 1}
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

							<!-- Reason -->
							<div class="space-y-1">
								<Label>Reason</Label>
								<textarea
									class="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring min-h-[60px] resize-y"
									value={evidence.reason || ""}
									oninput={(e) => {
										evidence.reason = e.currentTarget.value;
									}}
									placeholder="Explanation for this evidence..."
								></textarea>
							</div>

							<!-- Room -->
							<div class="space-y-1">
								<Label>Room</Label>
								<Input
									type="text"
									value={evidence.room || ""}
									oninput={(e) => {
										evidence.room = e.currentTarget.value;
									}}
									placeholder="e.g., Kitchen, Hallway"
									class="h-8 text-sm"
								/>
							</div>

							<!-- Modalities -->
							<div class="space-y-1">
								<Label>Modalities</Label>
								<div class="flex flex-wrap gap-2">
									{#each ["Gaze", "Audio", "Trajectory", "Depth", "Video", "OCR"] as mod}
										<label
											class="flex items-center gap-1.5 text-sm cursor-pointer"
										>
											<input
												type="checkbox"
												checked={evidence.modalities?.includes(
													mod,
												) || false}
												onchange={() => {
													const current =
														evidence.modalities ||
														[];
													if (current.includes(mod)) {
														evidence.modalities =
															current.filter(
																(m: string) =>
																	m !== mod,
															);
													} else {
														evidence.modalities = [
															...current,
															mod,
														];
													}
												}}
												class="rounded border-border"
											/>
											{mod}
										</label>
									{/each}
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
										➕ Add Time Span
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
														class="text-xs text-muted-foreground"
														>Start</span
													>
													<Input
														type="text"
														value={span.start || ""}
														oninput={(e) => {
															span.start =
																e.currentTarget.value;
														}}
														placeholder="MM:SS"
														class="h-8 text-sm"
													/>
												</div>
												<div class="space-y-1">
													<span
														class="text-xs text-muted-foreground"
														>End</span
													>
													<Input
														type="text"
														value={span.end || ""}
														oninput={(e) => {
															span.end =
																e.currentTarget.value;
														}}
														placeholder="MM:SS"
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
														><polyline
															points="3 6 5 6 21 6"
														/><path
															d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"
														/></svg
													>
												</Button>
											{/if}
										</div>
									{/each}
								{:else}
									<div
										class="text-xs text-muted-foreground italic"
									>
										No time spans added.
									</div>
								{/if}
							</div>
							<div class="space-y-2">
								<Label>Search Evidence Time Span</Label>
								<CaptionSearchPanel
									mode="evidence"
									questionStartTime={editedAnnotation?.question_time_span?.start}
									existingEvidenceSpans={allEvidenceTimeSpans}
									onSelect={(selection) => applyCaptionToEvidence(i, selection)}
								/>
							</div>

							<!-- Evidence Bounding Boxes -->
							<div class="space-y-2">
								<div class="flex items-center justify-between">
									<Label
										>📦 Bounding Boxes ({evidence
											.bounding_boxes?.length ||
											0})</Label
									>
									<Button
										size="sm"
										variant="ghost"
										class="h-6 text-xs"
										onclick={() => addEvBoundingBox(i)}
									>
										➕ Add Box
									</Button>
								</div>
								{#if evidence.bounding_boxes && evidence.bounding_boxes.length > 0}
									{#each evidence.bounding_boxes as bb, bi}
										<div
											class="border rounded p-2 bg-white text-xs space-y-1"
										>
											<div
												class="flex items-center justify-between"
											>
												<span class="font-medium"
													>Box #{bi + 1}</span
												>
												<Button
													size="sm"
													variant="ghost"
													class="text-destructive hover:text-destructive/80 h-5 px-1 text-xs"
													onclick={() => {
														if (
															evidence.bounding_boxes
														) {
															evidence.bounding_boxes =
																evidence.bounding_boxes.filter(
																	(
																		_: any,
																		idx: number,
																	) =>
																		idx !==
																		bi,
																);
														}
													}}
												>
													Remove
												</Button>
											</div>
											<div class="grid grid-cols-5 gap-1">
												<div>
													<span
														class="text-muted-foreground"
														>Timestamp</span
													>
													<Input
														type="text"
														value={bb.timestamp ||
															""}
														oninput={(e) => {
															bb.timestamp =
																e.currentTarget.value;
														}}
														placeholder="MM:SS"
														class="h-6 text-xs"
													/>
												</div>
												{#each [0, 1, 2, 3] as ci}
													{@const labels = [
														"Y1",
														"X1",
														"Y2",
														"X2",
													]}
													<div>
														<span
															class="text-muted-foreground"
															>{labels[ci]}</span
														>
														<Input
															type="text"
															value={String(
																bb.box_2d?.[
																	ci
																] ?? "",
															)}
															oninput={(e: any) =>
																updateEvBBoxCoord(
																	i,
																	bi,
																	ci,
																	parseInt(
																		e
																			.currentTarget
																			.value,
																	) || 0,
																)}
															class="h-6 text-xs"
														/>
													</div>
												{/each}
											</div>
											<div>
												<span
													class="text-muted-foreground"
													>Description</span
												>
												<Input
													type="text"
													value={bb.description || ""}
													oninput={(e: any) => {
														bb.description =
															e.currentTarget.value;
													}}
													placeholder="Description"
													class="h-6 text-xs"
												/>
											</div>
										</div>
									{/each}
								{:else}
									<div
										class="text-xs text-muted-foreground italic"
									>
										No bounding boxes. Click "Add Box" to
										create one.
									</div>
								{/if}
							</div>
						</div>
					{/each}
				{/if}
			</div>

			<!-- Human Review - USING NEW MODULAR EDITOR -->
			<div class="space-y-2">
				<HumanReviewEditor
					data={annotationFieldToData(
						editedAnnotation,
						"human_review",
					) as HumanReviewData}
					label="Human Review"
					onChange={(newData) => {
						if (editedAnnotation) {
							editedAnnotation = updateAnnotationFromData(
								editedAnnotation,
								"human_review",
								newData,
							);
						}
					}}
				/>
			</div>
		</div>

		<!-- Footer -->
		<div class="border-t px-6 py-4 flex justify-end gap-3 bg-secondary">
			<Button variant="secondary" onclick={onCancel}>Cancel</Button>
			<Button onclick={handleSave}>💾 Save Changes</Button>
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
