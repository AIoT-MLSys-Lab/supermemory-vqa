<script lang="ts">
	import Button from "$lib/components/ui/button/Button.svelte";
	import Input from "$lib/components/ui/input/Input.svelte";
	import { parseTimestamp, formatTimestamp } from "$lib/utils";
	import { resolveVideoSource } from "$lib/utils/video-source";
	import type { Caption, CaptionFile, TranscriptLine, PersonDetail } from "$lib/types";
	import { onMount, onDestroy } from "svelte";

	/** Return value only if it is a string; otherwise return empty string. */
	function str(v: unknown): string {
		return typeof v === 'string' ? v : '';
	}

	// -------- Props --------
	type EditType = 'caption' | 'summary';

	interface Props {
		/** Whether the modal is open */
		open: boolean;
		/** Type of item being edited */
		editType: EditType;
		/** Video source URL */
		videoSource: string;
		/** Start time for the video clip (for seeking) */
		clipStart: number;
		/** End time for the video clip */
		clipEnd: number;
		/** Video duration */
		videoDuration: number;

		// ---- Caption-specific props ----
		/** The caption data being edited (for caption type) */
		caption?: Caption;
		captionIndex?: number;
		totalCaptions?: number;

		// ---- Summary-specific props ----
		/** The chunk summary text (for summary type) */
		summaryText?: string;
		summaryIndex?: number;
		totalSummaries?: number;

		// ---- Callbacks ----
		onSave: (data: any) => void;
		onCancel: () => void;
		onSaveAndNext: (data: any) => void;
		onSaveAndPrev: (data: any) => void;
	}

	let {
		open,
		editType,
		videoSource,
		clipStart,
		clipEnd,
		videoDuration,
		caption,
		captionIndex = 0,
		totalCaptions = 0,
		summaryText = '',
		summaryIndex = 0,
		totalSummaries = 0,
		onSave,
		onCancel,
		onSaveAndNext,
		onSaveAndPrev,
	}: Props = $props();

	// ---- Local video player ----
	let modalVideoPlayer: HTMLVideoElement | undefined = $state();
	let isModalPlaying = $state(false);
	let modalCurrentTime = $state(0);
	let modalDuration = $state(0);
	let reachedEnd = $state(false);

	// ---- Editing state for captions ----
	let editingText = $state("");
	let editingStart = $state("");
	let editingEnd = $state("");
	let editingActivities = $state("");
	let editingObjects = $state("");
	let editingEnvironment = $state("");
	let editingVisibleText = $state("");
	let editingImportance = $state("medium");
	let editingImportanceReasoning = $state("");
	let editingConfidence = $state("medium");
	let editingConfidenceReasoning = $state("");
	let editingOptimalSamplingRate = $state("medium");
	let editingOptimalSamplingRateReasoning = $state("");
	let editingOptimalResolution = $state("medium");
	let editingOptimalResolutionReasoning = $state("");

	// ---- Structured editing state for transcript and people ----
	let editingTranscriptLines = $state<TranscriptLine[]>([]);
	let editingPeopleList = $state<PersonDetail[]>([]);

	// ---- Editing state for summaries ----
	let editingSummaryText = $state("");

	// Whether the caption has description fields
	let hasDescription = $derived(editType === 'caption' && caption?.description !== undefined);

	// Current index and total for display
	let currentIndex = $derived(editType === 'caption' ? (captionIndex ?? 0) : (summaryIndex ?? 0));
	let totalItems = $derived(editType === 'caption' ? (totalCaptions ?? 0) : (totalSummaries ?? 0));
	let hasPrev = $derived(currentIndex > 0);
	let hasNext = $derived(currentIndex < totalItems - 1);

	// Speaker label options
	const speakerLabels = ['User', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z'];
	const personLabels = ['User', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z'];

	/** Parse audio_transcript field (could be string or list) */
	function parseTranscriptLines(v: unknown): TranscriptLine[] {
		if (Array.isArray(v)) {
			return v.map(item => ({
				speaker: item?.speaker ?? null,
				transcript: item?.transcript ?? (typeof item === 'string' ? item : ''),
			}));
		}
		if (typeof v === 'string' && v.trim()) {
			// Legacy string format: try to split by semicolons or newlines
			return v.split(/[;\n]/).filter(s => s.trim()).map(s => {
				const trimmed = s.trim();
				// Try to parse "Speaker: text" format
				const match = trimmed.match(/^([A-Z][a-z]*|User)\s*:\s*(.+)$/);
				if (match) {
					return { speaker: match[1], transcript: match[2] };
				}
				return { speaker: null, transcript: trimmed };
			});
		}
		return [];
	}

	/** Parse people field (could be string or list) */
	function parsePeopleList(v: unknown): PersonDetail[] {
		if (Array.isArray(v)) {
			return v.map(item => ({
				person: item?.person ?? '',
				description: item?.description ?? (typeof item === 'string' ? item : ''),
			}));
		}
		if (typeof v === 'string' && v.trim()) {
			// Legacy string format: try to split by semicolons
			return v.split(';').filter(s => s.trim()).map(s => ({
				person: '',
				description: s.trim(),
			}));
		}
		return [];
	}

	// Populate editing state from props
	$effect(() => {
		if (open && editType === 'caption' && caption) {
			editingText = caption.text;
			editingStart = caption.start;
			editingEnd = caption.end;
			const desc = caption.description;
			editingActivities = str(desc?.activities);
			editingObjects = str(desc?.objects);
			editingEnvironment = str(desc?.environment);
			editingVisibleText = str(desc?.visible_text);
			editingTranscriptLines = parseTranscriptLines(desc?.audio_transcript);
			editingPeopleList = parsePeopleList(desc?.people);
			editingImportance = caption.importance ?? "medium";
			editingImportanceReasoning = caption.importance_reasoning ?? "";
			editingConfidence = caption.confidence ?? "medium";
			editingConfidenceReasoning = caption.confidence_reasoning ?? "";
			editingOptimalSamplingRate = caption.optimal_sampling_rate ?? "medium";
			editingOptimalSamplingRateReasoning = caption.optimal_sampling_rate_reasoning ?? "";
			editingOptimalResolution = caption.optimal_resolution ?? "medium";
			editingOptimalResolutionReasoning = caption.optimal_resolution_reasoning ?? "";
			reachedEnd = false;
		}
	});

	$effect(() => {
		if (open && editType === 'summary') {
			editingSummaryText = summaryText ?? '';
		}
	});

	// Seek video to clip start when modal opens
	$effect(() => {
		if (open && modalVideoPlayer && clipStart >= 0) {
			modalVideoPlayer.currentTime = clipStart;
			modalCurrentTime = clipStart;
			reachedEnd = false;
		}
	});

	/** Handle replay: restart from clip start */
	function handleReplay() {
		if (!modalVideoPlayer) return;
		reachedEnd = false;
		modalVideoPlayer.currentTime = clipStart;
		modalCurrentTime = clipStart;
		modalVideoPlayer.play();
	}

	/** Handle range slider scrub */
	function handleRangeSliderInput(e: Event) {
		if (!modalVideoPlayer) return;
		const value = parseFloat((e.target as HTMLInputElement).value);
		modalVideoPlayer.currentTime = value;
		modalCurrentTime = value;
		if (value < clipEnd - 0.1) {
			reachedEnd = false;
		}
	}

	// ---- Transcript list editing ----
	function insertTranscriptLine(position: number) {
		const copy = [...editingTranscriptLines];
		copy.splice(position, 0, { speaker: null, transcript: '' });
		editingTranscriptLines = copy;
	}

	function addTranscriptLine() {
		insertTranscriptLine(editingTranscriptLines.length);
	}

	function removeTranscriptLine(index: number) {
		editingTranscriptLines = editingTranscriptLines.filter((_, i) => i !== index);
	}

	function moveTranscriptLine(index: number, direction: -1 | 1) {
		const target = index + direction;
		if (target < 0 || target >= editingTranscriptLines.length) return;
		const copy = [...editingTranscriptLines];
		[copy[index], copy[target]] = [copy[target], copy[index]];
		editingTranscriptLines = copy;
	}

	function updateTranscriptSpeaker(index: number, speaker: string | null) {
		editingTranscriptLines = editingTranscriptLines.map((item, i) =>
			i === index ? { ...item, speaker: speaker === '' ? null : speaker } : item
		);
	}

	function updateTranscriptText(index: number, transcript: string) {
		editingTranscriptLines = editingTranscriptLines.map((item, i) =>
			i === index ? { ...item, transcript } : item
		);
	}

	// ---- People list editing ----
	function insertPerson(position: number) {
		const copy = [...editingPeopleList];
		copy.splice(position, 0, { person: '', description: '' });
		editingPeopleList = copy;
	}

	function addPerson() {
		insertPerson(editingPeopleList.length);
	}

	function removePerson(index: number) {
		editingPeopleList = editingPeopleList.filter((_, i) => i !== index);
	}

	function movePerson(index: number, direction: -1 | 1) {
		const target = index + direction;
		if (target < 0 || target >= editingPeopleList.length) return;
		const copy = [...editingPeopleList];
		[copy[index], copy[target]] = [copy[target], copy[index]];
		editingPeopleList = copy;
	}

	function updatePersonLabel(index: number, person: string) {
		editingPeopleList = editingPeopleList.map((item, i) =>
			i === index ? { ...item, person } : item
		);
	}

	function updatePersonDescription(index: number, description: string) {
		editingPeopleList = editingPeopleList.map((item, i) =>
			i === index ? { ...item, description } : item
		);
	}

	/** Build data object to pass back */
	function buildCaptionData() {
		const hadDescription = !!caption?.description;
		const description = hadDescription ? {
			activities: editingActivities,
			objects: editingObjects,
			environment: editingEnvironment,
			visible_text: editingVisibleText,
			audio_transcript: editingTranscriptLines,
			people: editingPeopleList,
		} : undefined;

		/** Rebuild the flat `text` field from individual description fields. */
		function buildTextFromDescription(): string {
			const parts: string[] = [];
			if (editingActivities.trim()) parts.push(editingActivities.trim());
			if (editingObjects.trim()) parts.push(`Objects: ${editingObjects.trim()}`);
			if (editingEnvironment.trim()) parts.push(`Environment: ${editingEnvironment.trim()}`);
			const peopleStr = editingPeopleList
				.filter(p => p.description.trim())
				.map(p => p.person ? `${p.person}: ${p.description}` : p.description)
				.join('; ');
			if (peopleStr) parts.push(`People: ${peopleStr}`);
			const audioStr = editingTranscriptLines
				.filter(t => t.transcript.trim())
				.map(t => t.speaker ? `${t.speaker}: ${t.transcript}` : t.transcript)
				.join('; ');
			if (audioStr) parts.push(`Audio: ${audioStr}`);
			if (editingVisibleText.trim()) parts.push(`Text: ${editingVisibleText.trim()}`);
			return parts.join(". ");
		}

		return {
			type: 'caption' as const,
			index: captionIndex,
			text: hadDescription ? buildTextFromDescription() : editingText,
			start: editingStart,
			end: editingEnd,
			importance: editingImportance,
			importance_reasoning: editingImportanceReasoning,
			confidence: editingConfidence,
			confidence_reasoning: editingConfidenceReasoning,
			optimal_sampling_rate: editingOptimalSamplingRate,
			optimal_sampling_rate_reasoning: editingOptimalSamplingRateReasoning,
			optimal_resolution: editingOptimalResolution,
			optimal_resolution_reasoning: editingOptimalResolutionReasoning,
			...(description ? { description } : {}),
		};
	}

	function buildSummaryData() {
		return {
			type: 'summary' as const,
			index: summaryIndex,
			text: editingSummaryText,
		};
	}

	function buildData() {
		return editType === 'caption' ? buildCaptionData() : buildSummaryData();
	}

	function handleSave() {
		onSave(buildData());
	}

	function handleSaveAndNext() {
		onSaveAndNext(buildData());
	}

	function handleSaveAndPrev() {
		onSaveAndPrev(buildData());
	}

	function handleCancel() {
		onCancel();
	}

	// Handle ESC key
	function handleKeydown(e: KeyboardEvent) {
		if (!open) return;
		if (e.key === 'Escape') {
			e.preventDefault();
			handleCancel();
		}
	}

	onMount(() => {
		document.addEventListener('keydown', handleKeydown);
	});

	onDestroy(() => {
		document.removeEventListener('keydown', handleKeydown);
	});
</script>

{#if open}
	<!-- Backdrop -->
	<div class="caption-edit-modal-backdrop" onclick={handleCancel} role="presentation"></div>

	<!-- Modal -->
	<div class="caption-edit-modal" role="dialog" aria-modal="true" aria-label="Edit {editType === 'caption' ? 'Caption' : 'Chunk Summary'}">
		<!-- Top Action Bar -->
		<div class="modal-action-bar">
			<div class="modal-action-bar-left">
				<span class="modal-title">
					{#if editType === 'caption'}
						Editing Caption {(captionIndex ?? 0) + 1} of {totalCaptions}
					{:else}
						Editing Chunk Summary {(summaryIndex ?? 0) + 1} of {totalSummaries}
					{/if}
				</span>
			</div>
			<div class="modal-action-bar-right">
				<!-- Previous + Save -->
				<button
					class="modal-icon-btn"
					title="Save & Previous"
					onclick={handleSaveAndPrev}
					disabled={!hasPrev}
				>
					<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
						<path d="M19 12H5M12 19l-7-7 7-7"/>
					</svg>
				</button>
				<!-- Save -->
				<button
					class="modal-icon-btn modal-icon-btn-primary"
					title="Save"
					onclick={handleSave}
				>
					<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
						<path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/>
						<polyline points="17 21 17 13 7 13 7 21"/>
						<polyline points="7 3 7 8 15 8"/>
					</svg>
				</button>
				<!-- Next + Save -->
				<button
					class="modal-icon-btn"
					title="Save & Next"
					onclick={handleSaveAndNext}
					disabled={!hasNext}
				>
					<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
						<path d="M5 12h14M12 5l7 7-7 7"/>
					</svg>
				</button>
				<!-- Divider -->
				<div class="modal-action-divider"></div>
				<!-- Cancel -->
				<button
					class="modal-icon-btn modal-icon-btn-cancel"
					title="Cancel (Esc)"
					onclick={handleCancel}
				>
					<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
						<line x1="18" y1="6" x2="6" y2="18"/>
						<line x1="6" y1="6" x2="18" y2="18"/>
					</svg>
				</button>
			</div>
		</div>

		<!-- Main Content: Video Left, Editor Right -->
		<div class="modal-content">
			<!-- Left: Video Player -->
			<div class="modal-video-panel">
				<div class="modal-video-wrapper">
					<video
						bind:this={modalVideoPlayer}
						src={videoSource}
						preload="metadata"
						class="modal-video"
						onplay={() => { isModalPlaying = true; }}
						onpause={() => { isModalPlaying = false; }}
						onloadedmetadata={() => { if (modalVideoPlayer) modalDuration = modalVideoPlayer.duration || 0; }}
						onloadeddata={() => {
							if (modalVideoPlayer) {
								modalDuration = modalVideoPlayer.duration || 0;
								modalVideoPlayer.currentTime = clipStart;
							}
						}}
						ontimeupdate={() => {
							if (!modalVideoPlayer) return;
							modalCurrentTime = modalVideoPlayer.currentTime;
							if (modalVideoPlayer.currentTime >= clipEnd && !modalVideoPlayer.paused) {
								modalVideoPlayer.pause();
								modalVideoPlayer.currentTime = clipEnd;
								modalCurrentTime = clipEnd;
								reachedEnd = true;
							}
						}}
						onclick={() => {
							if (!modalVideoPlayer) return;
							if (reachedEnd) {
								handleReplay();
							} else if (modalVideoPlayer.paused) {
								modalVideoPlayer.play();
							} else {
								modalVideoPlayer.pause();
							}
						}}
					>
						<track kind="captions" />
					</video>
				</div>
				<!-- Video controls -->
				<div class="modal-video-controls">
					<button
						class="modal-video-ctrl-btn {reachedEnd ? 'modal-video-ctrl-btn-replay' : ''}"
						onclick={() => {
							if (reachedEnd) {
								handleReplay();
							} else if (modalVideoPlayer) {
								if (modalVideoPlayer.paused) modalVideoPlayer.play(); else modalVideoPlayer.pause();
							}
						}}
						title={reachedEnd ? "Replay from start" : isModalPlaying ? "Pause" : "Play"}
					>
						{#if reachedEnd}
							<!-- Replay icon -->
							<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
								<polyline points="1 4 1 10 7 10"/>
								<path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>
							</svg>
						{:else if isModalPlaying}
							<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
						{:else}
							<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><polygon points="5,3 19,12 5,21"/></svg>
						{/if}
					</button>
					<div class="modal-video-time">
						{formatTimestamp(modalCurrentTime)} / {formatTimestamp(modalDuration)}
					</div>
					<!-- Seek to clip start -->
					<button
						class="modal-video-ctrl-btn"
						onclick={() => { if (modalVideoPlayer) { modalVideoPlayer.currentTime = clipStart; modalCurrentTime = clipStart; reachedEnd = false; } }}
						title="Seek to clip start"
					>
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="11 17 6 12 11 7"/><line x1="6" y1="12" x2="20" y2="12"/></svg>
					</button>
					<!-- Seek to clip end -->
					<button
						class="modal-video-ctrl-btn"
						onclick={() => { if (modalVideoPlayer) { modalVideoPlayer.currentTime = clipEnd; modalCurrentTime = clipEnd; } }}
						title="Seek to clip end"
					>
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="13 7 18 12 13 17"/><line x1="4" y1="12" x2="18" y2="12"/></svg>
					</button>
				</div>
				<!-- Range slider constrained to caption timespan -->
				<div class="modal-range-slider">
					<span class="modal-range-label">{formatTimestamp(clipStart)}</span>
					<input
						type="range"
						class="modal-range-input"
						min={clipStart}
						max={clipEnd}
						step={0.1}
						value={modalCurrentTime < clipStart ? clipStart : modalCurrentTime > clipEnd ? clipEnd : modalCurrentTime}
						oninput={handleRangeSliderInput}
					/>
					<span class="modal-range-label">{formatTimestamp(clipEnd)}</span>
				</div>
				<!-- Clip time info -->
				<div class="modal-clip-info">
					<span class="modal-clip-label">Clip:</span>
					<span class="modal-clip-time">{formatTimestamp(clipStart)} → {formatTimestamp(clipEnd)}</span>
					{#if reachedEnd}
						<span class="modal-clip-ended-badge">Ended</span>
					{/if}
				</div>
			</div>

			<!-- Right: Edit Panel -->
			<div class="modal-edit-panel">
				{#if editType === 'summary'}
					<!-- Summary Edit Form -->
					<div class="edit-section">
						<label class="edit-label">Chunk Summary #{(summaryIndex ?? 0) + 1}</label>
						<textarea
							class="edit-textarea edit-textarea-large"
							bind:value={editingSummaryText}
							placeholder="Enter chunk summary..."
						></textarea>
					</div>
				{:else if editType === 'caption'}
					<!-- Caption Edit Form -->
					{#if hasDescription}
						<!-- Individual description fields -->
						<div class="edit-section">
							<label class="edit-label">Activities</label>
							<textarea class="edit-textarea" bind:value={editingActivities} placeholder="What activities are happening..."></textarea>
						</div>
						<div class="edit-section">
							<label class="edit-label">Objects</label>
							<textarea class="edit-textarea" bind:value={editingObjects} placeholder="Objects visible in the scene..."></textarea>
						</div>
						<div class="edit-section">
							<label class="edit-label">Environment</label>
							<textarea class="edit-textarea" bind:value={editingEnvironment} placeholder="Environment description..."></textarea>
						</div>

						<!-- People: structured list editor -->
						<div class="edit-section">
							<div class="edit-label-row">
								<label class="edit-label">People</label>
								<button class="list-add-btn" onclick={addPerson} title="Add person at end">
									<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
									Add
								</button>
							</div>
							{#if editingPeopleList.length === 0}
								<div class="list-empty">No people listed. Click "Add" to add a person.</div>
							{:else}
								<div class="structured-list">
									<!-- Insert-at-top button -->
									<button class="list-insert-btn" onclick={() => insertPerson(0)} title="Insert person at top">
										<span class="list-insert-line"></span>
										<span class="list-insert-icon">
											<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
										</span>
										<span class="list-insert-line"></span>
									</button>
									{#each editingPeopleList as person, i}
										<div class="list-item">
											<div class="list-item-order-controls">
												<button class="list-move-btn" onclick={() => movePerson(i, -1)} disabled={i === 0} title="Move up">
													<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="18 15 12 9 6 15"/></svg>
												</button>
												<span class="list-item-index">{i + 1}</span>
												<button class="list-move-btn" onclick={() => movePerson(i, 1)} disabled={i === editingPeopleList.length - 1} title="Move down">
													<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
												</button>
											</div>
											<div class="list-item-fields">
												<div class="list-item-label-field">
													<select
														class="edit-select-compact"
														value={person.person}
														onchange={(e) => updatePersonLabel(i, (e.target as HTMLSelectElement).value)}
													>
														<option value="">—</option>
														{#each personLabels as lbl}
															<option value={lbl}>{lbl}</option>
														{/each}
													</select>
												</div>
												<div class="list-item-text-field">
													<input
														type="text"
														class="edit-input-compact"
														value={person.description}
														oninput={(e) => updatePersonDescription(i, (e.target as HTMLInputElement).value)}
														placeholder="Physical description, role, actions..."
													/>
												</div>
											</div>
											<button class="list-remove-btn" onclick={() => removePerson(i)} title="Remove person">
												<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
											</button>
										</div>
										<!-- Insert-after button -->
										<button class="list-insert-btn" onclick={() => insertPerson(i + 1)} title="Insert person after this">
											<span class="list-insert-line"></span>
											<span class="list-insert-icon">
												<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
											</span>
											<span class="list-insert-line"></span>
										</button>
									{/each}
								</div>
							{/if}
						</div>

						<!-- Audio Transcript: structured list editor -->
						<div class="edit-section">
							<div class="edit-label-row">
								<label class="edit-label">Audio Transcript</label>
								<button class="list-add-btn" onclick={addTranscriptLine} title="Add transcript line at end">
									<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
									Add
								</button>
							</div>
							{#if editingTranscriptLines.length === 0}
								<div class="list-empty">No transcript lines. Click "Add" to add a line.</div>
							{:else}
								<div class="structured-list">
									<!-- Insert-at-top button -->
									<button class="list-insert-btn" onclick={() => insertTranscriptLine(0)} title="Insert line at top">
										<span class="list-insert-line"></span>
										<span class="list-insert-icon">
											<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
										</span>
										<span class="list-insert-line"></span>
									</button>
									{#each editingTranscriptLines as line, i}
										<div class="list-item">
											<div class="list-item-order-controls">
												<button class="list-move-btn" onclick={() => moveTranscriptLine(i, -1)} disabled={i === 0} title="Move up">
													<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="18 15 12 9 6 15"/></svg>
												</button>
												<span class="list-item-index">{i + 1}</span>
												<button class="list-move-btn" onclick={() => moveTranscriptLine(i, 1)} disabled={i === editingTranscriptLines.length - 1} title="Move down">
													<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
												</button>
											</div>
											<div class="list-item-fields">
												<div class="list-item-label-field">
													<select
														class="edit-select-compact"
														value={line.speaker ?? ''}
														onchange={(e) => updateTranscriptSpeaker(i, (e.target as HTMLSelectElement).value || null)}
													>
														<option value="">🔊</option>
														{#each speakerLabels as lbl}
															<option value={lbl}>{lbl}</option>
														{/each}
													</select>
												</div>
												<div class="list-item-text-field">
													<input
														type="text"
														class="edit-input-compact"
														value={line.transcript}
														oninput={(e) => updateTranscriptText(i, (e.target as HTMLInputElement).value)}
														placeholder="Spoken text or [Sound description]..."
													/>
												</div>
											</div>
											<button class="list-remove-btn" onclick={() => removeTranscriptLine(i)} title="Remove line">
												<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
											</button>
										</div>
										<!-- Insert-after button -->
										<button class="list-insert-btn" onclick={() => insertTranscriptLine(i + 1)} title="Insert line after this">
											<span class="list-insert-line"></span>
											<span class="list-insert-icon">
												<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
											</span>
											<span class="list-insert-line"></span>
										</button>
									{/each}
								</div>
							{/if}
						</div>

						<div class="edit-section">
							<label class="edit-label">Visible Text</label>
							<textarea class="edit-textarea" bind:value={editingVisibleText} placeholder="Text visible on screen..."></textarea>
						</div>
					{:else}
						<!-- Fallback: single text field -->
						<div class="edit-section">
							<label class="edit-label">Caption Text</label>
							<textarea class="edit-textarea edit-textarea-large" bind:value={editingText} placeholder="Caption text..."></textarea>
						</div>
					{/if}

					<!-- Time span and metadata -->
					<div class="edit-row">
						<div class="edit-field">
							<label class="edit-label">Start</label>
							<input type="text" class="edit-input" bind:value={editingStart} placeholder="0:00" />
						</div>
						<div class="edit-field">
							<label class="edit-label">End</label>
							<input type="text" class="edit-input" bind:value={editingEnd} placeholder="0:00" />
						</div>
						<div class="edit-field">
							<label class="edit-label">Importance</label>
							<select class="edit-select" bind:value={editingImportance}>
								<option value="high">High</option>
								<option value="medium">Medium</option>
								<option value="low">Low</option>
							</select>
						</div>
						<div class="edit-field">
							<label class="edit-label">Confidence</label>
							<select class="edit-select" bind:value={editingConfidence}>
								<option value="very high">Very High</option>
								<option value="high">High</option>
								<option value="medium">Medium</option>
								<option value="low">Low</option>
								<option value="very low">Very Low</option>
							</select>
						</div>
						<div class="edit-field">
							<label class="edit-label">Sampling Rate</label>
							<select class="edit-select" bind:value={editingOptimalSamplingRate}>
								<option value="high">High</option>
								<option value="medium">Medium</option>
								<option value="low">Low</option>
							</select>
						</div>
						<div class="edit-field">
							<label class="edit-label">Resolution</label>
							<select class="edit-select" bind:value={editingOptimalResolution}>
								<option value="high">High</option>
								<option value="medium">Medium</option>
								<option value="low">Low</option>
							</select>
						</div>
					</div>

					<!-- Reasoning fields -->
					<div class="edit-section">
						<label class="edit-label">Importance Reasoning</label>
						<textarea class="edit-textarea" bind:value={editingImportanceReasoning} placeholder="Reasoning for the importance level..."></textarea>
					</div>
					<div class="edit-section">
						<label class="edit-label">Confidence Reasoning</label>
						<textarea class="edit-textarea" bind:value={editingConfidenceReasoning} placeholder="Reasoning for the confidence level..."></textarea>
					</div>
					<div class="edit-section">
						<label class="edit-label">Sampling Rate Reasoning</label>
						<textarea class="edit-textarea" bind:value={editingOptimalSamplingRateReasoning} placeholder="Reasoning for the optimal sampling rate..."></textarea>
					</div>
					<div class="edit-section">
						<label class="edit-label">Resolution Reasoning</label>
						<textarea class="edit-textarea" bind:value={editingOptimalResolutionReasoning} placeholder="Reasoning for the optimal resolution..."></textarea>
					</div>
				{/if}
			</div>
		</div>
	</div>
{/if}

<style>
	.caption-edit-modal-backdrop {
		position: fixed;
		inset: 0;
		z-index: 90;
		background: rgba(0, 0, 0, 0.6);
		backdrop-filter: blur(4px);
		animation: fadeIn 0.15s ease-out;
	}

	.caption-edit-modal {
		position: fixed;
		inset: 32px;
		z-index: 100;
		display: flex;
		flex-direction: column;
		background: var(--color-card);
		border: 1px solid var(--color-border);
		border-radius: 12px;
		box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25), 0 0 0 1px rgba(0, 0, 0, 0.05);
		overflow: hidden;
		animation: modalSlideIn 0.2s ease-out;
	}

	/* Top action bar */
	.modal-action-bar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 10px 16px;
		background: var(--color-secondary);
		border-bottom: 1px solid var(--color-border);
		flex-shrink: 0;
	}

	.modal-action-bar-left {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.modal-title {
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--color-foreground);
	}

	.modal-action-bar-right {
		display: flex;
		align-items: center;
		gap: 4px;
	}

	.modal-icon-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 36px;
		height: 36px;
		border-radius: 8px;
		border: 1px solid var(--color-border);
		background: var(--color-card);
		color: var(--color-muted-foreground);
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.modal-icon-btn:hover:not(:disabled) {
		background: var(--color-secondary);
		color: var(--color-foreground);
		border-color: var(--color-foreground);
	}

	.modal-icon-btn:disabled {
		opacity: 0.35;
		cursor: not-allowed;
	}

	.modal-icon-btn-primary {
		background: var(--color-primary);
		color: var(--color-primary-foreground);
		border-color: var(--color-primary);
	}

	.modal-icon-btn-primary:hover:not(:disabled) {
		background: hsl(0 72% 44%);
		color: var(--color-primary-foreground);
		border-color: hsl(0 72% 44%);
	}

	.modal-icon-btn-cancel {
		color: var(--color-destructive);
		border-color: hsl(0 72% 51% / 0.3);
	}

	.modal-icon-btn-cancel:hover:not(:disabled) {
		background: hsl(0 72% 51% / 0.1);
		border-color: var(--color-destructive);
		color: var(--color-destructive);
	}

	.modal-action-divider {
		width: 1px;
		height: 24px;
		background: var(--color-border);
		margin: 0 6px;
	}

	/* Main content split */
	.modal-content {
		display: flex;
		flex: 1;
		min-height: 0;
		overflow: hidden;
	}

	/* Video panel (left side) */
	.modal-video-panel {
		flex: 0 0 50%;
		display: flex;
		flex-direction: column;
		background: hsl(0 0% 4%);
		border-right: 1px solid var(--color-border);
	}

	.modal-video-wrapper {
		flex: 1;
		display: flex;
		align-items: center;
		justify-content: center;
		min-height: 0;
		overflow: hidden;
	}

	.modal-video {
		width: 100%;
		height: 100%;
		object-fit: contain;
		cursor: pointer;
	}

	.modal-video-controls {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 8px 12px;
		background: hsl(0 0% 8%);
		border-top: 1px solid hsl(0 0% 15%);
	}

	.modal-video-ctrl-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 32px;
		height: 32px;
		border-radius: 6px;
		border: none;
		background: transparent;
		color: hsl(0 0% 70%);
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.modal-video-ctrl-btn:hover {
		background: hsl(0 0% 18%);
		color: hsl(0 0% 95%);
	}

	.modal-video-time {
		font-size: 0.75rem;
		font-family: ui-monospace, SFMono-Regular, monospace;
		color: hsl(0 0% 55%);
		margin-left: auto;
	}

	.modal-clip-info {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 6px 12px;
		background: hsl(0 0% 6%);
		border-top: 1px solid hsl(0 0% 12%);
	}

	.modal-clip-label {
		font-size: 0.6875rem;
		font-weight: 600;
		color: hsl(0 0% 45%);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.modal-clip-time {
		font-size: 0.75rem;
		font-family: ui-monospace, SFMono-Regular, monospace;
		color: hsl(0 72% 60%);
	}

	/* Edit panel (right side) */
	.modal-edit-panel {
		flex: 0 0 50%;
		display: flex;
		flex-direction: column;
		gap: 12px;
		padding: 16px;
		overflow-y: auto;
		background: var(--color-card);
	}

	.edit-section {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.edit-label {
		font-size: 0.6875rem;
		font-weight: 600;
		color: var(--color-muted-foreground);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.edit-label-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
	}

	.edit-textarea {
		width: 100%;
		font-size: 0.8125rem;
		line-height: 1.5;
		padding: 8px 10px;
		border: 1px solid var(--color-border);
		border-radius: 8px;
		resize: vertical;
		min-height: 48px;
		background: var(--color-background);
		color: var(--color-foreground);
		font-family: inherit;
		transition: border-color 0.15s ease;
	}

	.edit-textarea:focus {
		outline: none;
		border-color: var(--color-primary);
		box-shadow: 0 0 0 2px hsl(0 72% 51% / 0.15);
	}

	.edit-textarea-large {
		min-height: 120px;
		flex: 1;
	}

	.edit-row {
		display: flex;
		gap: 10px;
		flex-wrap: wrap;
	}

	.edit-field {
		display: flex;
		flex-direction: column;
		gap: 4px;
		flex: 1;
		min-width: 100px;
	}

	.edit-input {
		font-size: 0.8125rem;
		padding: 6px 8px;
		border: 1px solid var(--color-border);
		border-radius: 6px;
		background: var(--color-background);
		color: var(--color-foreground);
		font-family: ui-monospace, SFMono-Regular, monospace;
		transition: border-color 0.15s ease;
	}

	.edit-input:focus {
		outline: none;
		border-color: var(--color-primary);
		box-shadow: 0 0 0 2px hsl(0 72% 51% / 0.15);
	}

	.edit-select {
		font-size: 0.8125rem;
		padding: 6px 8px;
		border: 1px solid var(--color-border);
		border-radius: 6px;
		background: var(--color-background);
		color: var(--color-foreground);
		transition: border-color 0.15s ease;
		cursor: pointer;
	}

	.edit-select:focus {
		outline: none;
		border-color: var(--color-primary);
		box-shadow: 0 0 0 2px hsl(0 72% 51% / 0.15);
	}

	/* Structured list styles */
	.structured-list {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.list-item {
		display: flex;
		align-items: center;
		gap: 4px;
		padding: 4px 0;
	}

	.list-item-fields {
		display: flex;
		flex: 1;
		gap: 6px;
		align-items: center;
		min-width: 0;
	}

	.list-item-label-field {
		flex: 0 0 auto;
	}

	.list-item-text-field {
		flex: 1;
		min-width: 0;
	}

	.edit-select-compact {
		font-size: 0.75rem;
		padding: 4px 6px;
		border: 1px solid var(--color-border);
		border-radius: 5px;
		background: var(--color-background);
		color: var(--color-foreground);
		cursor: pointer;
		min-width: 52px;
		transition: border-color 0.15s ease;
	}

	.edit-select-compact:focus {
		outline: none;
		border-color: var(--color-primary);
		box-shadow: 0 0 0 2px hsl(0 72% 51% / 0.1);
	}

	.edit-input-compact {
		width: 100%;
		font-size: 0.8125rem;
		padding: 4px 8px;
		border: 1px solid var(--color-border);
		border-radius: 5px;
		background: var(--color-background);
		color: var(--color-foreground);
		font-family: inherit;
		transition: border-color 0.15s ease;
	}

	.edit-input-compact:focus {
		outline: none;
		border-color: var(--color-primary);
		box-shadow: 0 0 0 2px hsl(0 72% 51% / 0.1);
	}

	.list-add-btn {
		display: inline-flex;
		align-items: center;
		gap: 3px;
		font-size: 0.6875rem;
		font-weight: 600;
		padding: 3px 8px;
		border: 1px solid var(--color-border);
		border-radius: 5px;
		background: var(--color-card);
		color: var(--color-muted-foreground);
		cursor: pointer;
		transition: all 0.15s ease;
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}

	.list-add-btn:hover {
		background: var(--color-secondary);
		color: var(--color-foreground);
		border-color: var(--color-primary);
	}

	.list-remove-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 26px;
		height: 26px;
		border-radius: 5px;
		border: 1px solid transparent;
		background: transparent;
		color: var(--color-muted-foreground);
		cursor: pointer;
		flex-shrink: 0;
		transition: all 0.15s ease;
	}

	.list-remove-btn:hover {
		background: hsl(0 72% 51% / 0.1);
		color: var(--color-destructive);
		border-color: hsl(0 72% 51% / 0.3);
	}

	.list-empty {
		font-size: 0.75rem;
		color: var(--color-muted-foreground);
		padding: 8px 0;
		font-style: italic;
	}

	/* Order controls column */
	.list-item-order-controls {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0px;
		flex-shrink: 0;
		width: 24px;
	}

	.list-item-index {
		font-size: 0.625rem;
		color: var(--color-muted-foreground);
		font-weight: 600;
		line-height: 1;
		user-select: none;
		font-variant-numeric: tabular-nums;
	}

	.list-move-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 20px;
		height: 16px;
		border: none;
		background: transparent;
		color: var(--color-muted-foreground);
		cursor: pointer;
		border-radius: 3px;
		padding: 0;
		transition: all 0.12s ease;
	}

	.list-move-btn:hover:not(:disabled) {
		background: var(--color-secondary);
		color: var(--color-foreground);
	}

	.list-move-btn:disabled {
		opacity: 0.2;
		cursor: default;
	}

	/* Insert-between button */
	.list-insert-btn {
		display: flex;
		align-items: center;
		gap: 0;
		width: 100%;
		height: 16px;
		border: none;
		background: transparent;
		cursor: pointer;
		padding: 0 4px;
		opacity: 0;
		transition: opacity 0.15s ease;
	}

	.structured-list:hover .list-insert-btn {
		opacity: 0.45;
	}

	.list-insert-btn:hover {
		opacity: 1 !important;
	}

	.list-insert-line {
		flex: 1;
		height: 1px;
		background: var(--color-primary);
		opacity: 0.4;
		transition: opacity 0.12s ease;
	}

	.list-insert-btn:hover .list-insert-line {
		opacity: 0.8;
	}

	.list-insert-icon {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 18px;
		height: 18px;
		border-radius: 50%;
		background: var(--color-card);
		border: 1px solid var(--color-primary);
		color: var(--color-primary);
		flex-shrink: 0;
		transition: all 0.12s ease;
	}

	.list-insert-btn:hover .list-insert-icon {
		background: var(--color-primary);
		color: var(--color-primary-foreground);
		box-shadow: 0 0 6px hsl(0 72% 51% / 0.3);
	}

	/* Range slider */
	.modal-range-slider {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 6px 12px;
		background: hsl(0 0% 6%);
		border-top: 1px solid hsl(0 0% 12%);
	}

	.modal-range-label {
		font-size: 0.6875rem;
		font-family: ui-monospace, SFMono-Regular, monospace;
		color: hsl(0 0% 45%);
		white-space: nowrap;
		min-width: 36px;
		text-align: center;
	}

	.modal-range-input {
		flex: 1;
		height: 4px;
		-webkit-appearance: none;
		appearance: none;
		background: hsl(0 0% 20%);
		border-radius: 2px;
		outline: none;
		cursor: pointer;
		transition: background 0.15s ease;
	}

	.modal-range-input::-webkit-slider-thumb {
		-webkit-appearance: none;
		appearance: none;
		width: 14px;
		height: 14px;
		border-radius: 50%;
		background: hsl(0 72% 55%);
		border: 2px solid hsl(0 0% 95%);
		cursor: pointer;
		box-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
		transition: transform 0.1s ease, box-shadow 0.1s ease;
	}

	.modal-range-input::-webkit-slider-thumb:hover {
		transform: scale(1.2);
		box-shadow: 0 2px 6px rgba(0, 0, 0, 0.5);
	}

	.modal-range-input::-moz-range-thumb {
		width: 14px;
		height: 14px;
		border-radius: 50%;
		background: hsl(0 72% 55%);
		border: 2px solid hsl(0 0% 95%);
		cursor: pointer;
		box-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
	}

	/* Replay button styling */
	.modal-video-ctrl-btn-replay {
		color: hsl(0 72% 60%) !important;
		background: hsl(0 72% 51% / 0.15) !important;
		border-radius: 6px;
	}

	.modal-video-ctrl-btn-replay:hover {
		background: hsl(0 72% 51% / 0.25) !important;
		color: hsl(0 72% 70%) !important;
	}

	/* Ended badge */
	.modal-clip-ended-badge {
		font-size: 0.625rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		padding: 2px 6px;
		border-radius: 4px;
		background: hsl(0 72% 51% / 0.15);
		color: hsl(0 72% 60%);
		border: 1px solid hsl(0 72% 51% / 0.3);
		margin-left: auto;
	}

	/* Animations */
	@keyframes fadeIn {
		from { opacity: 0; }
		to { opacity: 1; }
	}

	@keyframes modalSlideIn {
		from {
			opacity: 0;
			transform: scale(0.96) translateY(8px);
		}
		to {
			opacity: 1;
			transform: scale(1) translateY(0);
		}
	}
</style>
