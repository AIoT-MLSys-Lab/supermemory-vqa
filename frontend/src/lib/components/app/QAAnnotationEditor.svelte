<script lang="ts">
	import {
		Box,
		Check,
		Clock,
		Film,
		ListChecks,
		MapPin,
		MessageSquare,
		Plus,
		Save,
		Search,
		ShieldCheck,
		Tags,
		Target,
		Trash2,
		X,
	} from "lucide-svelte";
	import Button from "$lib/components/ui/button/Button.svelte";
	import Input from "$lib/components/ui/input/Input.svelte";
	import Badge from "$lib/components/ui/badge/Badge.svelte";
	import CaptionSearchPanel from "$lib/components/editors/CaptionSearchPanel.svelte";
	import type { Annotation, AnswerChoice, Evidence, HumanReview, TimeSpan } from "$lib/types";
	import type { QAReviewClip } from "$lib/utils/qa-review";
	import { answerEvidence, questionTimeSpans, syncAnnotationForSave } from "$lib/utils/qa-review";
	import { deepClone, unescapeHtml } from "$lib/utils";

	interface Props {
		annotation: Annotation;
		clips: QAReviewClip[];
		activeClipKey: string;
		onChange: (annotation: Annotation) => void;
		onSave: () => void;
		onClipSelect: (clipKey: string) => void;
		onReloadCurrent?: () => void;
		saving?: boolean;
		isDirty?: boolean;
		validationErrors?: string[];
		conflictMessage?: string;
	}

	interface SearchSelection {
		video_id: string;
		video_path?: string;
		start_time: string;
		end_time: string;
	}

	let {
		annotation,
		clips,
		activeClipKey,
		onChange,
		onSave,
		onClipSelect,
		onReloadCurrent,
		saving = false,
		isDirty = false,
		validationErrors = [],
		conflictMessage = "",
	}: Props = $props();

	const modalities = ["Gaze", "Audio", "Trajectory", "Depth", "Video", "OCR"];
	const skills = [
		"object_location_memory",
		"conversational_memory",
		"visual_recall",
		"timeline_reconstruction",
		"intent_recall",
		"in_context_retrieval",
		"unknown",
	];
	const choiceTypes = ["correct", "vague", "incorrect"];

	const qSpans = $derived(questionTimeSpans(annotation));
	const evidenceList = $derived(answerEvidence(annotation));
	const reviewStatus = $derived(annotation.human_review?.status || "pending");
	const metadata = $derived((annotation.metadata_details || {}) as Record<string, any>);
	const verification = $derived((annotation.verification_score || {}) as Record<string, any>);
	const firstQuestionStart = $derived(qSpans[0]?.start || annotation.question_time_span?.start || "");
	let suggestedChunksDraft = $state("");
	let suggestedChunksSource = $state("");

	$effect(() => {
		const nextSource = JSON.stringify(verification.suggested_chunks || [], null, 2);
		if (nextSource !== suggestedChunksSource) {
			suggestedChunksSource = nextSource;
			suggestedChunksDraft = nextSource;
		}
	});

	function choiceTone(type?: string): string {
		if (type === "correct") return "border-emerald-300 bg-emerald-50";
		if (type === "vague") return "border-amber-300 bg-amber-50";
		return "border-rose-300 bg-rose-50";
	}

	function choiceChipTone(active: boolean, type: string): string {
		if (!active) return "border-border bg-white text-muted-foreground hover:bg-secondary";
		if (type === "correct") return "border-emerald-500 bg-emerald-100 text-emerald-800";
		if (type === "vague") return "border-amber-500 bg-amber-100 text-amber-800";
		return "border-rose-500 bg-rose-100 text-rose-800";
	}

	function displayText(value: unknown): string {
		return unescapeHtml(typeof value === "string" ? value : "");
	}

	function emit(next: Annotation) {
		onChange(syncAnnotationForSave(next));
	}

	function updateField<K extends keyof Annotation>(field: K, value: Annotation[K]) {
		const next = deepClone(annotation);
		next[field] = value;
		if (field === "question" && next.question_details) next.question_details.text = value as string;
		if (field === "answer" && next.answer_details) next.answer_details.text = value as string;
		if (field === "room" && next.question_details) next.question_details.room = value as string;
		if (field === "modalities" && next.question_details) next.question_details.modalities = value as string[];
		if (field === "skill") {
			next.metadata_details = { ...(next.metadata_details || {}), skill: value };
		}
		if (field === "confidence" || field === "confidence_reasoning") {
			next.metadata_details = { ...(next.metadata_details || {}), [field]: value };
		}
		emit(next);
	}

	function updateQuestionDetail(field: string, value: unknown) {
		const next = deepClone(annotation);
		next.question_details = { ...(next.question_details || {}), [field]: value };
		if (field === "text") next.question = value as string;
		if (field === "room") next.room = value as string;
		emit(next);
	}

	function updateMetadata(field: string, value: unknown) {
		const next = deepClone(annotation);
		next.metadata_details = { ...(next.metadata_details || {}), [field]: value };
		if (field === "skill") next.skill = value as any;
		if (field === "confidence") next.confidence = value === "" ? undefined : Number(value);
		if (field === "confidence_reasoning") next.confidence_reasoning = value as string;
		emit(next);
	}

	function updateVerification(field: string, value: unknown) {
		const next = deepClone(annotation);
		next.verification_score = { ...(next.verification_score || {}), [field]: value } as any;
		next.metadata_details = {
			...(next.metadata_details || {}),
			verification_score: next.verification_score,
		};
		emit(next);
	}

	function updateHumanReview(patch: Partial<HumanReview>) {
		const next = deepClone(annotation);
		const status = patch.status || next.human_review?.status || "pending";
		next.human_review = {
			...(next.human_review || {}),
			...patch,
			status,
			reviewed: status !== "pending",
			timestamp: new Date().toISOString(),
		};
		emit(next);
	}

	function toggleModality(modality: string, target: "question" | "evidence", evidenceIndex = -1) {
		const next = deepClone(annotation);
		if (target === "question") {
			const current = next.modalities || [];
			next.modalities = current.includes(modality)
				? current.filter((item) => item !== modality)
				: [...current, modality];
			if (next.question_details) next.question_details.modalities = next.modalities;
		} else {
			const evidence = answerEvidence(next);
			const current = evidence[evidenceIndex]?.modalities || [];
			evidence[evidenceIndex].modalities = current.includes(modality)
				? current.filter((item) => item !== modality)
				: [...current, modality];
			next.answer_evidence = evidence;
		}
		emit(next);
	}

	function updateQuestionSpan(index: number, patch: Partial<TimeSpan>) {
		const next = deepClone(annotation);
		const spans = questionTimeSpans(next);
		spans[index] = { ...(spans[index] || {}), ...patch };
		next.question_time_spans = spans;
		next.question_time_span = spans[0];
		emit(next);
	}

	function addQuestionSpan() {
		const next = deepClone(annotation);
		next.question_time_spans = [...questionTimeSpans(next), { start: "", end: "", video_id: annotation.question_details?.video_id || "" }];
		next.question_time_span = next.question_time_spans[0];
		emit(next);
	}

	function removeQuestionSpan(index: number) {
		const next = deepClone(annotation);
		const spans = questionTimeSpans(next).filter((_, i) => i !== index);
		next.question_time_spans = spans;
		next.question_time_span = spans[0];
		emit(next);
	}

	function activeQuestionSpanIndex(): number {
		const match = activeClipKey.match(/^question-(\d+)$/);
		const index = match ? Number(match[1]) : 0;
		return Number.isFinite(index) && index >= 0 ? index : 0;
	}

	function updateEvidence(index: number, patch: Partial<Evidence>) {
		const next = deepClone(annotation);
		const evidence = answerEvidence(next);
		evidence[index] = { ...(evidence[index] || {}), ...patch };
		next.answer_evidence = evidence;
		emit(next);
	}

	function addEvidence() {
		const next = deepClone(annotation);
		next.answer_evidence = [...answerEvidence(next), { time_spans: [{ start: "", end: "" }], modalities: [] }];
		emit(next);
	}

	function removeEvidence(index: number) {
		const next = deepClone(annotation);
		next.answer_evidence = answerEvidence(next).filter((_, i) => i !== index);
		emit(next);
	}

	function updateEvidenceSpan(evidenceIndex: number, spanIndex: number, patch: Partial<TimeSpan>) {
		const evidence = answerEvidence(annotation);
		const ev = { ...(evidence[evidenceIndex] || {}) };
		const spans = [...(ev.time_spans || [])];
		spans[spanIndex] = { ...(spans[spanIndex] || {}), ...patch };
		updateEvidence(evidenceIndex, { ...ev, time_spans: spans });
	}

	function addEvidenceSpan(evidenceIndex: number) {
		const evidence = answerEvidence(annotation);
		const ev = { ...(evidence[evidenceIndex] || {}) };
		updateEvidence(evidenceIndex, { ...ev, time_spans: [...(ev.time_spans || []), { start: "", end: "", video_id: ev.video_path || "" }] });
	}

	function removeEvidenceSpan(evidenceIndex: number, spanIndex: number) {
		const evidence = answerEvidence(annotation);
		const ev = { ...(evidence[evidenceIndex] || {}) };
		updateEvidence(evidenceIndex, {
			...ev,
			time_spans: (ev.time_spans || []).filter((_, i) => i !== spanIndex),
		});
	}

	function evidenceSearchSpans(excludeEvidenceIndex: number): TimeSpan[] {
		return evidenceList.flatMap((evidence, evidenceIndex) =>
			evidenceIndex === excludeEvidenceIndex ? [] : evidence.time_spans || [],
		);
	}

	function applyCaptionToQuestion(selection: SearchSelection) {
		const next = deepClone(annotation);
		const spans = [...questionTimeSpans(next)];
		const targetIndex = spans.length > 0 ? Math.min(activeQuestionSpanIndex(), spans.length - 1) : 0;
		spans[targetIndex] = {
			...(spans[targetIndex] || {}),
			start: selection.start_time,
			end: selection.end_time,
			video_id: selection.video_id,
		};
		next.question_time_spans = spans;
		next.question_time_span = spans[0];
		next.question_details = {
			...(next.question_details || {}),
			video_id: selection.video_id,
		};
		emit(next);
		onClipSelect(`question-${targetIndex}`);
	}

	function applyCaptionToEvidence(evidenceIndex: number, selection: SearchSelection) {
		const evidence = answerEvidence(annotation);
		const ev = { ...(evidence[evidenceIndex] || {}) };
		const selectedVideoPath = selection.video_path || `${selection.video_id}.mp4`;
		const spans = [...(ev.time_spans || [])];
		spans[0] = {
			start: selection.start_time,
			end: selection.end_time,
			video_id: selection.video_id,
		};
		updateEvidence(evidenceIndex, {
			...ev,
			video_path: selectedVideoPath,
			time_spans: spans,
		});
		onClipSelect(`evidence-${evidenceIndex}-0`);
	}

	function updateAnswerable(isAnswerable: boolean) {
		const next = deepClone(annotation);
		next.is_answerable = isAnswerable;
		if (next.answer_details) next.answer_details.is_answerable = isAnswerable;
		if (next.question_details) next.question_details.is_answerable = isAnswerable;
		emit(next);
	}

	function updateChoice(index: number, patch: Partial<AnswerChoice>) {
		const next = deepClone(annotation);
		const choices = [...(next.answer_choices || [])];
		choices[index] = { ...(choices[index] || { text: "", choice_type: "incorrect", explanation: "" }), ...patch } as AnswerChoice;
		next.answer_choices = choices;
		if (next.answer_details) next.answer_details.answer_choices = choices;
		emit(next);
	}

	function addChoice() {
		const next = deepClone(annotation);
		const choices = [...(next.answer_choices || []), { text: "", choice_type: "incorrect", explanation: "" } as AnswerChoice];
		next.answer_choices = choices;
		if (next.answer_details) next.answer_details.answer_choices = choices;
		emit(next);
	}

	function removeChoice(index: number) {
		const next = deepClone(annotation);
		const choices = (next.answer_choices || []).filter((_, i) => i !== index);
		next.answer_choices = choices;
		if (next.answer_details) next.answer_details.answer_choices = choices;
		emit(next);
	}

	function updateBox(target: "question" | "evidence", boxIndex: number, patch: any, evidenceIndex = -1) {
		const next = deepClone(annotation);
		if (target === "question") {
			const boxes = [...(next.location?.boxes || [])];
			boxes[boxIndex] = { ...(boxes[boxIndex] || {}), ...patch };
			next.location = { ...(next.location || {}), boxes };
		} else {
			const evidence = answerEvidence(next);
			const boxes = [...(evidence[evidenceIndex]?.bounding_boxes || [])];
			boxes[boxIndex] = { ...(boxes[boxIndex] || {}), ...patch };
			evidence[evidenceIndex].bounding_boxes = boxes;
			next.answer_evidence = evidence;
		}
		emit(next);
	}

	function updateSuggestions(raw: string) {
		updateVerification("suggestions", raw.split("\n").map((line) => line.trim()).filter(Boolean));
	}

	function updateSuggestedChunks(raw: string) {
		suggestedChunksDraft = raw;
		try {
			updateVerification("suggested_chunks", raw.trim() ? JSON.parse(raw) : []);
		} catch {
			// Keep the typed value in place until the user finishes valid JSON.
		}
	}
</script>

<div class="space-y-3 text-sm">
	<div class="sticky top-0 z-10 -mx-2 flex items-center justify-between gap-2 border-b border-border bg-card/95 px-2 py-2 backdrop-blur">
		<div class="flex min-w-0 items-center gap-2">
			<Badge variant="secondary" class="shrink-0">{annotation.annotation_type || "qa"}</Badge>
			<Badge variant={reviewStatus === "accepted" ? "success" : reviewStatus === "rejected" ? "destructive" : "warning"} class="shrink-0">
				{reviewStatus}
			</Badge>
			{#if isDirty}
				<Badge variant="warning" class="shrink-0">Unsaved changes</Badge>
			{/if}
			<span class="truncate text-xs text-muted-foreground">{metadata.qa_id || annotation.skill || "unknown"}</span>
		</div>
		<Button size="sm" onclick={onSave} disabled={saving} class="h-8 gap-1.5">
			<Save class="h-3.5 w-3.5" />
			{saving ? "Saving" : "Save"}
		</Button>
	</div>

	{#if conflictMessage}
		<div class="flex flex-wrap items-center justify-between gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-2 text-xs text-destructive">
			<span>{conflictMessage}</span>
			{#if onReloadCurrent}
				<Button size="sm" variant="outline" class="h-7 bg-white text-xs" onclick={onReloadCurrent}>
					Reload current
				</Button>
			{/if}
		</div>
	{/if}

	{#if validationErrors.length > 0}
		<div class="rounded-md border border-destructive/30 bg-destructive/10 p-2 text-xs text-destructive">
			<div class="font-semibold">Fix before saving</div>
			<ul class="mt-1 list-disc pl-4">
				{#each validationErrors as validationError}
					<li>{validationError}</li>
				{/each}
			</ul>
		</div>
	{/if}

	<section class="rounded-md border border-sky-200 bg-sky-50/50 p-2">
		<div class="mb-1.5 flex items-center gap-2 text-xs font-semibold text-sky-800">
			<Film class="h-3.5 w-3.5" />
			<span>Clips</span>
		</div>
		<div class="flex flex-wrap gap-1.5">
			{#each clips as clip}
				<button
					type="button"
					class="rounded-md border px-2 py-1 font-mono text-[11px] transition-colors {clip.key === activeClipKey ? 'border-sky-500 bg-white text-sky-700 shadow-sm' : 'border-sky-200 bg-sky-100/60 text-sky-900 hover:bg-white'}"
					onclick={() => onClipSelect(clip.key)}
					title={`${clip.label} ${clip.videoFilename}`}
				>
					{clip.type === "question" ? "Q" : "E"} {clip.timeSpan.start || "?"}-{clip.timeSpan.end || "?"}
				</button>
			{/each}
		</div>
	</section>

	<section class="rounded-md border border-indigo-200 bg-indigo-50/40 p-2">
		<div class="mb-2 flex items-center gap-1.5 text-xs font-semibold text-indigo-800">
			<MessageSquare class="h-3.5 w-3.5" />
			Question
		</div>
		<textarea
			class="min-h-20 w-full resize-y rounded-md border border-indigo-200 bg-white px-2 py-1.5 text-sm leading-snug outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
			value={displayText(annotation.question)}
			oninput={(e) => updateField("question", e.currentTarget.value)}
		></textarea>
		<div class="mt-2 grid gap-1.5 lg:grid-cols-[1fr_1.4fr]">
			<label>
				<span class="mb-0.5 flex items-center gap-1 text-[11px] font-medium text-muted-foreground"><MapPin class="h-3 w-3" />Room</span>
				<Input class="h-8 bg-white text-xs" value={annotation.room || ""} oninput={(e) => updateField("room", e.currentTarget.value)} />
			</label>
			<label>
				<span class="mb-0.5 flex items-center gap-1 text-[11px] font-medium text-muted-foreground"><Film class="h-3 w-3" />Question video_id</span>
				<Input class="h-8 bg-white font-mono text-xs" value={annotation.question_details?.video_id || ""} oninput={(e) => updateQuestionDetail("video_id", e.currentTarget.value)} />
			</label>
		</div>
		<div class="mt-2 flex flex-wrap gap-1">
			{#each modalities as modality}
				<button
					type="button"
					class="rounded-full border px-2 py-0.5 text-[11px] {annotation.modalities?.includes(modality) ? 'border-violet-400 bg-violet-100 text-violet-800' : 'border-border bg-white text-muted-foreground'}"
					onclick={() => toggleModality(modality, "question")}
				>
					{modality}
				</button>
			{/each}
		</div>

		<div class="mt-2 rounded-md border border-blue-200 bg-blue-50/60 p-2">
			<div class="mb-1.5 flex items-center justify-between">
				<div class="flex items-center gap-1.5 text-xs font-semibold text-blue-800">
					<Clock class="h-3.5 w-3.5" />
					Time Spans
				</div>
				<button type="button" class="rounded p-1 text-blue-700 hover:bg-blue-100" onclick={addQuestionSpan} title="Add question span">
					<Plus class="h-4 w-4" />
				</button>
			</div>
			<div class="grid gap-1.5">
				{#each qSpans as span, index}
					<div
						class="grid cursor-pointer grid-cols-[1fr_1fr_minmax(120px,1.2fr)_28px] gap-1.5 rounded-md p-1 transition-colors {activeClipKey === `question-${index}` ? 'bg-blue-100 ring-1 ring-blue-300' : 'hover:bg-blue-100/60'}"
						onclick={() => onClipSelect(`question-${index}`)}
						onkeydown={(e) => {
							if (e.key === "Enter" || e.key === " ") onClipSelect(`question-${index}`);
						}}
						role="button"
						tabindex="0"
						title="Click to switch the video to this question span"
					>
						<Input class="h-8 bg-white font-mono text-xs" value={span.start || ""} placeholder="start" onfocus={() => onClipSelect(`question-${index}`)} oninput={(e) => updateQuestionSpan(index, { start: e.currentTarget.value })} />
						<Input class="h-8 bg-white font-mono text-xs" value={span.end || ""} placeholder="end" onfocus={() => onClipSelect(`question-${index}`)} oninput={(e) => updateQuestionSpan(index, { end: e.currentTarget.value })} />
						<Input class="h-8 bg-white font-mono text-xs" value={span.video_id || ""} placeholder="video_id" onfocus={() => onClipSelect(`question-${index}`)} oninput={(e) => updateQuestionSpan(index, { video_id: e.currentTarget.value })} />
						<button type="button" class="rounded text-muted-foreground hover:bg-blue-100 hover:text-destructive disabled:opacity-30" onclick={(e) => { e.stopPropagation(); removeQuestionSpan(index); }} disabled={qSpans.length <= 1} title="Remove span">
							<Trash2 class="mx-auto h-3.5 w-3.5" />
						</button>
					</div>
				{/each}
			</div>
		</div>

		<details
			class="mt-2 rounded-md border border-sky-200 bg-sky-50/70 p-2"
			open={activeClipKey.startsWith("question-")}
		>
			<summary class="flex cursor-pointer list-none items-center gap-1.5 text-xs font-semibold text-sky-800">
				<Search class="h-3.5 w-3.5" />
				Search Caption Database For Question Span
			</summary>
			<div class="mt-2">
				<CaptionSearchPanel
					mode="question"
					onSelect={applyCaptionToQuestion}
				/>
			</div>
		</details>

		{#if annotation.location?.boxes && annotation.location.boxes.length > 0}
			<details class="mt-2 rounded border border-violet-200 bg-violet-50/50 p-2">
				<summary class="flex cursor-pointer list-none items-center gap-1 text-[11px] font-semibold text-violet-800">
					<Box class="h-3 w-3" />
					Bounding Boxes ({annotation.location.boxes.length})
				</summary>
				<div class="mt-2 grid gap-1.5">
					{#each annotation.location.boxes as box, boxIndex}
						<div class="grid gap-1.5 lg:grid-cols-[90px_1fr_1fr]">
							<Input class="h-8 font-mono text-xs" value={box.timestamp || ""} placeholder="time" oninput={(e) => updateBox("question", boxIndex, { timestamp: e.currentTarget.value })} />
							<Input class="h-8 text-xs" value={box.description || ""} placeholder="label" oninput={(e) => updateBox("question", boxIndex, { description: e.currentTarget.value })} />
							<Input class="h-8 font-mono text-xs" value={(box.box_2d || []).join(",")} placeholder="y1,x1,y2,x2" oninput={(e) => updateBox("question", boxIndex, { box_2d: e.currentTarget.value.split(",").map((v) => Number(v.trim()) || 0) })} />
						</div>
					{/each}
				</div>
			</details>
		{/if}

		<label class="mt-2 block">
			<span class="mb-1 flex items-center gap-1.5 text-xs font-semibold text-indigo-800">Question Reasoning</span>
			<textarea
				class="min-h-16 w-full resize-y rounded-md border border-indigo-200 bg-white px-2 py-1.5 text-xs leading-snug outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
				value={displayText(annotation.question_details?.question_reasoning)}
				oninput={(e) => updateQuestionDetail("question_reasoning", e.currentTarget.value)}
			></textarea>
		</label>
	</section>

	<section class="rounded-md border border-emerald-200 bg-emerald-50/40 p-2">
		<div class="mb-2 flex items-center gap-1.5 text-xs font-semibold text-emerald-800">
			<Target class="h-3.5 w-3.5" />
			Answer
		</div>
		<textarea
			class="min-h-20 w-full resize-y rounded-md border border-emerald-200 bg-white px-2 py-1.5 text-sm leading-snug outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
			value={displayText(annotation.answer)}
			oninput={(e) => updateField("answer", e.currentTarget.value)}
		></textarea>
		<label class="mt-2 flex items-center gap-2 text-xs font-medium text-emerald-800">
			<input type="checkbox" checked={annotation.is_answerable !== false} onchange={(e) => updateAnswerable(e.currentTarget.checked)} />
			Answerable
		</label>

		<div class="mt-2 rounded-md border border-amber-200 bg-amber-50/60 p-2">
			<div class="mb-1.5 flex items-center justify-between">
				<div class="flex items-center gap-1.5 text-xs font-semibold text-amber-800">
					<ListChecks class="h-3.5 w-3.5" />
					Answer Choices
				</div>
				<button type="button" class="rounded p-1 text-amber-700 hover:bg-amber-100" onclick={addChoice} title="Add answer choice">
					<Plus class="h-4 w-4" />
				</button>
			</div>
			<div class="grid gap-1.5">
				{#each annotation.answer_choices || [] as choice, index}
					<div class="grid gap-1.5 rounded-md border-l-4 p-1.5 {choiceTone(choice.choice_type)} lg:grid-cols-[168px_1.2fr_1.2fr_28px]">
						<div class="flex rounded-md bg-white/70 p-0.5">
							{#each choiceTypes as type}
								<button
									type="button"
									class="h-7 flex-1 rounded border px-1 text-[10px] font-semibold uppercase tracking-normal {choiceChipTone(choice.choice_type === type, type)}"
									onclick={() => updateChoice(index, { choice_type: type as any })}
									title={`Mark choice as ${type}`}
								>
									{type === "correct" ? "OK" : type}
								</button>
							{/each}
						</div>
						<Input class="h-8 text-xs" value={displayText(choice.text)} placeholder="choice text" oninput={(e) => updateChoice(index, { text: e.currentTarget.value })} />
						<Input class="h-8 text-xs" value={displayText(choice.explanation)} placeholder="explanation" oninput={(e) => updateChoice(index, { explanation: e.currentTarget.value })} />
						<button type="button" class="rounded text-muted-foreground hover:bg-red-50 hover:text-destructive" onclick={() => removeChoice(index)} title="Remove choice">
							<Trash2 class="mx-auto h-3.5 w-3.5" />
						</button>
					</div>
				{/each}
			</div>
		</div>

		<div class="mt-2 rounded-md border border-emerald-200 bg-white/70 p-2">
			<div class="mb-2 flex items-center justify-between">
				<div class="flex items-center gap-1.5 text-xs font-semibold text-emerald-800">
					<Target class="h-3.5 w-3.5" />
					Evidence
				</div>
				<button type="button" class="rounded p-1 text-emerald-700 hover:bg-emerald-100" onclick={addEvidence} title="Add evidence">
					<Plus class="h-4 w-4" />
				</button>
			</div>
			<div class="space-y-2">
				{#each evidenceList as evidence, evidenceIndex}
					<div class="rounded-md border border-emerald-200 bg-white p-2">
						<div class="mb-2 flex items-center justify-between gap-2">
							<button type="button" class="rounded bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800" onclick={() => onClipSelect(`evidence-${evidenceIndex}-0`)}>
								E{evidenceIndex + 1}
							</button>
							<button type="button" class="rounded p-1 text-muted-foreground hover:bg-red-50 hover:text-destructive disabled:opacity-30" onclick={() => removeEvidence(evidenceIndex)} disabled={evidenceList.length <= 1} title="Remove evidence">
								<Trash2 class="h-3.5 w-3.5" />
							</button>
						</div>

						<div class="grid gap-1.5 lg:grid-cols-[1fr_1fr]">
							<label>
								<span class="mb-0.5 flex items-center gap-1 text-[11px] font-medium text-muted-foreground"><Film class="h-3 w-3" />Video</span>
								<Input class="h-8 font-mono text-xs" value={evidence.video_path || ""} placeholder="video_id" oninput={(e) => updateEvidence(evidenceIndex, { video_path: e.currentTarget.value })} />
							</label>
							<label>
								<span class="mb-0.5 flex items-center gap-1 text-[11px] font-medium text-muted-foreground"><MapPin class="h-3 w-3" />Room</span>
								<Input class="h-8 text-xs" value={evidence.room || ""} oninput={(e) => updateEvidence(evidenceIndex, { room: e.currentTarget.value })} />
							</label>
						</div>

						<div class="mt-1.5 flex flex-wrap gap-1">
							{#each modalities as modality}
								<button
									type="button"
									class="rounded-full border px-2 py-0.5 text-[11px] {evidence.modalities?.includes(modality) ? 'border-emerald-400 bg-emerald-100 text-emerald-800' : 'border-border bg-secondary/50 text-muted-foreground'}"
									onclick={() => toggleModality(modality, "evidence", evidenceIndex)}
								>
									{modality}
								</button>
							{/each}
						</div>

						<div class="mt-2 space-y-1.5">
							<div class="flex items-center justify-between text-[11px] font-semibold text-emerald-800">
								<span class="flex items-center gap-1"><Clock class="h-3 w-3" />Time</span>
								<button type="button" class="rounded p-0.5 hover:bg-emerald-100" onclick={() => addEvidenceSpan(evidenceIndex)} title="Add evidence span">
									<Plus class="h-3.5 w-3.5" />
								</button>
							</div>
							{#each evidence.time_spans || [] as span, spanIndex}
								<div
									class="grid cursor-pointer grid-cols-[1fr_1fr_minmax(120px,1.2fr)_28px] gap-1.5 rounded-md p-1 transition-colors {activeClipKey === `evidence-${evidenceIndex}-${spanIndex}` ? 'bg-emerald-100 ring-1 ring-emerald-300' : 'hover:bg-emerald-100/60'}"
									onclick={() => onClipSelect(`evidence-${evidenceIndex}-${spanIndex}`)}
									onkeydown={(e) => {
										if (e.key === "Enter" || e.key === " ") onClipSelect(`evidence-${evidenceIndex}-${spanIndex}`);
									}}
									role="button"
									tabindex="0"
									title="Click to switch the video to this evidence span"
								>
									<Input class="h-8 bg-white font-mono text-xs" value={span.start || ""} placeholder="start" onfocus={() => onClipSelect(`evidence-${evidenceIndex}-${spanIndex}`)} oninput={(e) => updateEvidenceSpan(evidenceIndex, spanIndex, { start: e.currentTarget.value })} />
									<Input class="h-8 bg-white font-mono text-xs" value={span.end || ""} placeholder="end" onfocus={() => onClipSelect(`evidence-${evidenceIndex}-${spanIndex}`)} oninput={(e) => updateEvidenceSpan(evidenceIndex, spanIndex, { end: e.currentTarget.value })} />
									<Input class="h-8 bg-white font-mono text-xs" value={span.video_id || ""} placeholder="video_id" onfocus={() => onClipSelect(`evidence-${evidenceIndex}-${spanIndex}`)} oninput={(e) => updateEvidenceSpan(evidenceIndex, spanIndex, { video_id: e.currentTarget.value })} />
									<button type="button" class="rounded text-muted-foreground hover:bg-red-50 hover:text-destructive disabled:opacity-30" onclick={(e) => { e.stopPropagation(); removeEvidenceSpan(evidenceIndex, spanIndex); }} disabled={(evidence.time_spans?.length || 0) <= 1} title="Remove span">
										<Trash2 class="mx-auto h-3.5 w-3.5" />
									</button>
								</div>
							{/each}
						</div>

						<details
							class="mt-2 rounded-md border border-cyan-200 bg-cyan-50/60 p-2"
							open={evidenceIndex === 0 || activeClipKey.startsWith(`evidence-${evidenceIndex}`)}
						>
							<summary class="flex cursor-pointer list-none items-center gap-1.5 text-xs font-semibold text-cyan-800">
								<Search class="h-3.5 w-3.5" />
								Search Caption Database For Evidence Span
							</summary>
							<div class="mt-2">
								<CaptionSearchPanel
									mode="evidence"
									questionStartTime={firstQuestionStart}
									existingEvidenceSpans={evidenceSearchSpans(evidenceIndex)}
									onSelect={(selection) => applyCaptionToEvidence(evidenceIndex, selection)}
								/>
							</div>
						</details>

						{#if evidence.bounding_boxes && evidence.bounding_boxes.length > 0}
							<details class="mt-2 rounded border border-border bg-secondary/30 p-2">
								<summary class="flex cursor-pointer list-none items-center gap-1 text-[11px] font-semibold text-muted-foreground">
									<Box class="h-3 w-3" />
									Boxes ({evidence.bounding_boxes.length})
								</summary>
								<div class="mt-2 grid gap-1.5">
									{#each evidence.bounding_boxes as box, boxIndex}
										<div class="grid gap-1.5 lg:grid-cols-[90px_1fr_1fr]">
											<Input class="h-8 font-mono text-xs" value={box.timestamp || ""} placeholder="time" oninput={(e) => updateBox("evidence", boxIndex, { timestamp: e.currentTarget.value }, evidenceIndex)} />
											<Input class="h-8 text-xs" value={box.description || ""} placeholder="label" oninput={(e) => updateBox("evidence", boxIndex, { description: e.currentTarget.value }, evidenceIndex)} />
											<Input class="h-8 font-mono text-xs" value={(box.box_2d || []).join(",")} placeholder="y1,x1,y2,x2" oninput={(e) => updateBox("evidence", boxIndex, { box_2d: e.currentTarget.value.split(",").map((v) => Number(v.trim()) || 0) }, evidenceIndex)} />
										</div>
									{/each}
								</div>
							</details>
						{/if}

						<label class="mt-2 block">
							<span class="mb-0.5 flex items-center gap-1 text-[11px] font-medium text-muted-foreground"><MessageSquare class="h-3 w-3" />Reason</span>
							<textarea
								class="min-h-14 w-full resize-y rounded-md border border-input bg-white px-2 py-1 text-xs leading-snug outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
								value={displayText(evidence.reason)}
								oninput={(e) => updateEvidence(evidenceIndex, { reason: e.currentTarget.value })}
							></textarea>
						</label>
					</div>
				{/each}
			</div>
		</div>

		<label class="mt-2 block">
			<span class="mb-1 flex items-center gap-1.5 text-xs font-semibold text-amber-800">Balance Reasoning</span>
			<textarea
				class="min-h-16 w-full resize-y rounded-md border border-amber-200 bg-white px-2 py-1.5 text-xs leading-snug outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500"
				value={displayText(annotation.balance_reasoning)}
				oninput={(e) => updateField("balance_reasoning", e.currentTarget.value)}
			></textarea>
		</label>
	</section>

	<section class="rounded-md border border-zinc-200 bg-zinc-50/70 p-2">
		<div class="mb-2 flex items-center gap-1.5 text-xs font-semibold text-zinc-700">
			<Tags class="h-3.5 w-3.5" />
			Metadata
		</div>
		<div class="grid gap-1.5 lg:grid-cols-[1fr_1fr_1fr_90px]">
			<label>
				<span class="mb-0.5 block text-[11px] font-medium text-muted-foreground">Skill</span>
				<select class="h-8 w-full rounded-md border border-input bg-white px-2 text-xs" value={annotation.skill || metadata.skill || "unknown"} onchange={(e) => updateMetadata("skill", e.currentTarget.value)}>
					{#each skills as skill}
						<option value={skill}>{skill}</option>
					{/each}
				</select>
			</label>
			<label>
				<span class="mb-0.5 block text-[11px] font-medium text-muted-foreground">QA ID</span>
				<Input class="h-8 bg-white font-mono text-xs" value={metadata.qa_id || ""} oninput={(e) => updateMetadata("qa_id", e.currentTarget.value)} />
			</label>
			<label>
				<span class="mb-0.5 block text-[11px] font-medium text-muted-foreground">Primary Video</span>
				<Input class="h-8 bg-white font-mono text-xs" value={metadata.primary_video_id || ""} oninput={(e) => updateMetadata("primary_video_id", e.currentTarget.value)} />
			</label>
			<label>
				<span class="mb-0.5 block text-[11px] font-medium text-muted-foreground">Orig</span>
				<Input class="h-8 bg-white font-mono text-xs" value={metadata.original_idx ?? ""} oninput={(e) => updateMetadata("original_idx", e.currentTarget.value === "" ? undefined : Number(e.currentTarget.value))} />
			</label>
		</div>
		<div class="mt-2 grid gap-1.5 lg:grid-cols-[120px_1fr]">
			<label>
				<span class="mb-0.5 block text-[11px] font-medium text-muted-foreground">Confidence</span>
				<Input class="h-8 bg-white text-xs" value={String(annotation.confidence ?? metadata.confidence ?? "")} oninput={(e) => updateMetadata("confidence", e.currentTarget.value)} />
			</label>
			<label>
				<span class="mb-0.5 block text-[11px] font-medium text-muted-foreground">Confidence Reasoning</span>
				<Input class="h-8 bg-white text-xs" value={displayText(annotation.confidence_reasoning || metadata.confidence_reasoning)} oninput={(e) => updateMetadata("confidence_reasoning", e.currentTarget.value)} />
			</label>
		</div>
		<label class="mt-2 block">
			<span class="mb-1 block text-xs font-semibold text-zinc-700">Skill Reasoning</span>
			<textarea class="min-h-16 w-full resize-y rounded-md border border-input bg-white px-2 py-1 text-xs leading-snug" value={displayText(metadata.skill_reasoning)} oninput={(e) => updateMetadata("skill_reasoning", e.currentTarget.value)}></textarea>
		</label>
	</section>

	<section class="rounded-md border border-fuchsia-200 bg-fuchsia-50/40 p-2">
		<div class="mb-2 flex items-center gap-1.5 text-xs font-semibold text-fuchsia-800">
			<ShieldCheck class="h-3.5 w-3.5" />
			Verification
		</div>
		<div class="grid gap-1.5 lg:grid-cols-4">
			{#each [
				["factual_correctness_score", "Factual"],
				["objective_correctness_score", "Objective"],
				["causal_answerability_score", "Causal"],
				["naturalness_score", "Natural"],
			] as score}
				<label>
					<span class="mb-0.5 block text-[11px] font-medium text-muted-foreground">{score[1]}</span>
					<Input class="h-8 bg-white text-xs" value={verification[score[0]] ?? ""} oninput={(e) => updateVerification(score[0], e.currentTarget.value === "" ? undefined : Number(e.currentTarget.value))} />
				</label>
			{/each}
		</div>
		<div class="mt-2 flex flex-wrap gap-1.5">
			{#each [
				["is_correct", "Correct"],
				["is_guessable", "Guessable"],
				["contains_pii", "PII"],
				["is_salvageable", "Salvageable"],
			] as flag}
				<label class="flex items-center gap-1 rounded-full border bg-white px-2 py-1 text-[11px] text-muted-foreground">
					<input type="checkbox" checked={Boolean(verification[flag[0]])} onchange={(e) => updateVerification(flag[0], e.currentTarget.checked)} />
					{flag[1]}
				</label>
			{/each}
		</div>
		<div class="mt-2 grid gap-2 lg:grid-cols-2">
			<label>
				<span class="mb-1 block text-[11px] font-semibold text-muted-foreground">Suggestions</span>
				<textarea class="min-h-16 w-full resize-y rounded-md border border-input bg-white px-2 py-1 text-xs leading-snug" value={(verification.suggestions || []).map(displayText).join('\n')} oninput={(e) => updateSuggestions(e.currentTarget.value)}></textarea>
			</label>
			<label>
				<span class="mb-1 block text-[11px] font-semibold text-muted-foreground">Suggested Chunks</span>
				<textarea class="min-h-16 w-full resize-y rounded-md border border-input bg-white px-2 py-1 font-mono text-[11px] leading-snug" value={suggestedChunksDraft} oninput={(e) => updateSuggestedChunks(e.currentTarget.value)}></textarea>
			</label>
		</div>
		<div class="mt-2 grid gap-2 lg:grid-cols-2">
			{#each [
				["factual_correctness_reasoning", "Factual Reasoning"],
				["objective_correctness_reasoning", "Objective Reasoning"],
				["causal_answerability_reasoning", "Causal Reasoning"],
				["naturalness_reasoning", "Naturalness Reasoning"],
				["guessability_justification", "Guessability Justification"],
				["privacy_audit_reasoning", "Privacy Audit Reasoning"],
			] as field}
				<label>
					<span class="mb-1 block text-[11px] font-semibold text-fuchsia-800">{field[1]}</span>
					<textarea class="min-h-16 w-full resize-y rounded-md border border-fuchsia-200 bg-white px-2 py-1 text-xs leading-snug outline-none focus:border-fuchsia-500 focus:ring-1 focus:ring-fuchsia-500" value={displayText(verification[field[0]])} oninput={(e) => updateVerification(field[0], e.currentTarget.value)}></textarea>
				</label>
			{/each}
		</div>
	</section>

	<section class="rounded-md border border-slate-200 bg-slate-50/70 p-2">
		<div class="mb-2 flex items-center gap-1.5 text-xs font-semibold text-slate-700">
			<ShieldCheck class="h-3.5 w-3.5" />
			Review
		</div>
		<div class="grid gap-2 lg:grid-cols-[auto_1fr]">
			<div class="flex gap-1">
				<button type="button" class="rounded-md border px-2 py-1 text-xs {reviewStatus === 'accepted' ? 'border-emerald-400 bg-emerald-100 text-emerald-800' : 'border-border bg-white text-muted-foreground'}" onclick={() => updateHumanReview({ status: "accepted" })} title="Accept">
					<Check class="h-3.5 w-3.5" />
				</button>
				<button type="button" class="rounded-md border px-2 py-1 text-xs {reviewStatus === 'rejected' ? 'border-red-400 bg-red-100 text-red-800' : 'border-border bg-white text-muted-foreground'}" onclick={() => updateHumanReview({ status: "rejected" })} title="Reject">
					<X class="h-3.5 w-3.5" />
				</button>
				<button type="button" class="rounded-md border px-2 py-1 text-xs {reviewStatus === 'pending' ? 'border-amber-400 bg-amber-100 text-amber-800' : 'border-border bg-white text-muted-foreground'}" onclick={() => updateHumanReview({ status: "pending" })} title="Pending">
					<Clock class="h-3.5 w-3.5" />
				</button>
			</div>
			<Input class="h-8 bg-white text-xs" value={annotation.human_review?.comment || ""} placeholder="Review comment" oninput={(e) => updateHumanReview({ comment: e.currentTarget.value })} />
		</div>
		<label class="mt-2 block">
			<span class="mb-1 block text-xs font-semibold text-slate-700">Rejection Reason</span>
			<textarea class="min-h-14 w-full resize-y rounded-md border border-input bg-white px-2 py-1 text-xs leading-snug" value={displayText(annotation.rejection_reason)} oninput={(e) => updateField("rejection_reason", e.currentTarget.value)}></textarea>
		</label>
	</section>
</div>
