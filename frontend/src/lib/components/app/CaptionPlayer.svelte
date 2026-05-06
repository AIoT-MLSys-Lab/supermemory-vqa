<script lang="ts">
	import {
		Card,
		CardHeader,
		CardTitle,
		CardContent,
	} from "$lib/components/ui/card";
	import Button from "$lib/components/ui/button/Button.svelte";
	import Badge from "$lib/components/ui/badge/Badge.svelte";
	import Input from "$lib/components/ui/input/Input.svelte";
	import VideoControls from "./VideoControls.svelte";
	import VideoProgressBar from "./VideoProgressBar.svelte";
	import CaptionTimeline from "./CaptionTimeline.svelte";
	import CaptionEditModal from "./CaptionEditModal.svelte";
	import { parseTimestamp, formatTimestamp } from "$lib/utils";
	import { resolveVideoSource } from "$lib/utils/video-source";
	import type { Caption, CaptionFile, HumanReview } from "$lib/types";
	import { apiClient } from "$lib/api";
	import {
		currentVideo,
		playerSectionActive,
		captionFiles,
		captionFilesLoading,
		setCaptionFiles,
		showAlert,
	} from "$lib/stores";
	import { getReviewStatus } from "$lib/stores";
	import { REVIEW_BADGE_VARIANT, REVIEW_LABEL, type ReviewStatus, IMPORTANCE_COLOR, IMPORTANCE_COLOR_DEFAULT, type ImportanceLevel, CONFIDENCE_COLOR, CONFIDENCE_COLOR_DEFAULT, type ConfidenceLevel } from "$lib/theme";
	import { onMount, onDestroy } from "svelte";

	/** Return value only if it is a string; otherwise return empty string. */
	function str(v: unknown): string {
		return typeof v === 'string' ? v : '';
	}

	let videoPlayer: HTMLVideoElement | undefined = $state();

	// Audio amplification
	let audioContext: AudioContext | undefined = $state();
	let gainNode: GainNode | undefined = $state();
	let mediaSource: MediaElementAudioSourceNode | undefined = $state();
	let volumeAmplification = $state(100);
	const SEEK_STEP = 5;

	// Video time tracking
	let videoDuration = $state(0);
	let videoCurrentTime = $state(0);
	let isPlaying = $state(false);
	let isVideoSeeking = $state(false);

	// Caption state
	let localCaptionFiles = $state<CaptionFile[]>([]);
	let selectedFileIndex = $state(0);
	let selectedCaptionIndex = $state(-1);
	let captionsLoading = $state(false);
	let editingCaptionIndex = $state(-1);
	let editingText = $state("");
	let editingStart = $state("");
	let editingEnd = $state("");
	let editingSummaryIndex = $state(-1);
	let editingSummaryText = $state("");
	// Individual description field editing
	let editingActivities = $state("");
	let editingObjects = $state("");
	let editingEnvironment = $state("");
	let editingVisibleText = $state("");
	// (audio_transcript and people editing moved to CaptionEditModal's structured list editors)
	let editingImportance = $state("medium");
	let editingConfidence = $state("medium");

	// Modal state
	let editModalOpen = $state(false);
	let editModalType = $state<'caption' | 'summary'>('caption');
	let editModalCaption = $state<Caption | undefined>(undefined);
	let editModalCaptionIndex = $state(0);
	let editModalSummaryText = $state('');
	let editModalSummaryIndex = $state(0);
	let editModalClipStart = $state(0);
	let editModalClipEnd = $state(0);

	// Context menu state
	let contextMenuOpen = $state(false);
	let contextMenuX = $state(0);
	let contextMenuY = $state(0);
	let contextMenuTime = $state(0);

	// New caption file form
	let showNewFileForm = $state(false);
	let newFileType = $state("narration");

	// New caption form
	let showNewCaptionForm = $state(false);
	let newCaptionText = $state("");
	let newCaptionStart = $state("");
	let newCaptionEnd = $state("");

	// Derived
	const activeVideoSource = $derived(
		$currentVideo?.path
			? resolveVideoSource($currentVideo.path)
			: $currentVideo
				? `/uploads/${$currentVideo.filename}`
				: ""
	);

	const currentFile = $derived(
		localCaptionFiles.length > 0 && selectedFileIndex >= 0 && selectedFileIndex < localCaptionFiles.length
			? localCaptionFiles[selectedFileIndex]
			: null
	);

	const currentCaptions = $derived(currentFile?.captions ?? []);
	const currentReviewStatus = $derived<ReviewStatus>(getReviewStatus(currentFile?.human_review));

	function handleKeydown(e: KeyboardEvent) {
		const activeElement = document.activeElement;
		const isInputFocused =
			activeElement instanceof HTMLInputElement ||
			activeElement instanceof HTMLTextAreaElement ||
			activeElement instanceof HTMLSelectElement;

		if (isInputFocused || !videoPlayer) return;

		if (e.key === " ") {
			e.preventDefault();
			if (videoPlayer.paused) videoPlayer.play();
			else videoPlayer.pause();
		} else if (e.key === "ArrowLeft") {
			e.preventDefault();
			const t = Math.max(0, videoPlayer.currentTime - SEEK_STEP);
			videoPlayer.currentTime = t;
			videoCurrentTime = t;
		} else if (e.key === "ArrowRight") {
			e.preventDefault();
			const t = Math.min(videoPlayer.duration || 0, videoPlayer.currentTime + SEEK_STEP);
			videoPlayer.currentTime = t;
			videoCurrentTime = t;
		} else if (e.key === "[" && e.ctrlKey) {
			e.preventDefault();
			navigatePrevCaption();
		} else if (e.key === "]" && e.ctrlKey) {
			e.preventDefault();
			navigateNextCaption();
		}
	}

	function initAudioAmplification() {
		if (!videoPlayer || audioContext) return;
		try {
			audioContext = new AudioContext();
			gainNode = audioContext.createGain();
			mediaSource = audioContext.createMediaElementSource(videoPlayer);
			mediaSource.connect(gainNode);
			gainNode.connect(audioContext.destination);
			gainNode.gain.value = volumeAmplification / 100;
		} catch (error) {
			console.error("Failed to initialize audio amplification:", error);
			audioContext = undefined;
			gainNode = undefined;
			mediaSource = undefined;
		}
	}

	function setVolumeAmplification(value: number) {
		volumeAmplification = Math.max(0, Math.min(200, value));
		if (gainNode) gainNode.gain.value = volumeAmplification / 100;
	}

	onMount(async () => {
		document.addEventListener("keydown", handleKeydown);
		document.addEventListener("click", closeContextMenu);
		await apiClient.fetchCsrfToken();
	});

	onDestroy(() => {
		document.removeEventListener("keydown", handleKeydown);
		document.removeEventListener("click", closeContextMenu);
		if (audioContext) audioContext.close();
	});

	// Load caption files when video changes
	$effect(() => {
		if ($currentVideo) {
			loadCaptionFiles($currentVideo.filename);
		}
	});

	async function loadCaptionFiles(filename: string) {
		captionsLoading = true;
		try {
			const files = await apiClient.listCaptionFiles(filename);
			// Load full details for each
			const detailed: CaptionFile[] = [];
			for (const f of files) {
				try {
					const full = await apiClient.getCaptionFile(filename, f.filename);
					detailed.push(full);
				} catch {
					detailed.push(f);
				}
			}
			localCaptionFiles = detailed;
			setCaptionFiles(detailed);
			selectedFileIndex = 0;
			selectedCaptionIndex = -1;
		} catch (error) {
			console.error("Failed to load caption files:", error);
			localCaptionFiles = [];
			setCaptionFiles([]);
		} finally {
			captionsLoading = false;
		}
	}

	function seekTo(timeStr: string) {
		if (!videoPlayer) return;
		const t = parseTimestamp(timeStr);
		videoPlayer.currentTime = t;
		videoCurrentTime = t;
	}

	function goBack() {
		playerSectionActive.set(false);
		currentVideo.set(null);
	}

	function navigateNextCaption() {
		if (currentCaptions.length === 0) return;
		const next = selectedCaptionIndex < currentCaptions.length - 1 ? selectedCaptionIndex + 1 : 0;
		selectCaption(next);
	}

	function navigatePrevCaption() {
		if (currentCaptions.length === 0) return;
		const prev = selectedCaptionIndex > 0 ? selectedCaptionIndex - 1 : currentCaptions.length - 1;
		selectCaption(prev);
	}

	function selectCaption(index: number) {
		selectedCaptionIndex = index;
		const cap = currentCaptions[index];
		if (cap) seekTo(cap.start);
		// Scroll the caption list to show the selected caption
		requestAnimationFrame(() => {
			const el = document.querySelector(`[data-caption-index="${index}"]`);
			if (el) el.scrollIntoView({ behavior: "smooth", block: "nearest" });
		});
	}

	// Edit caption – opens modal
	function startEdit(index: number) {
		const cap = currentCaptions[index];
		editModalType = 'caption';
		editModalCaption = cap;
		editModalCaptionIndex = index;
		editModalClipStart = parseTimestamp(cap.start);
		editModalClipEnd = parseTimestamp(cap.end);
		editModalOpen = true;
		editingCaptionIndex = index;
	}

	function cancelEdit() {
		editingCaptionIndex = -1;
		editModalOpen = false;
	}

	function startSummaryEdit(index: number, text: string) {
		editModalType = 'summary';
		editModalSummaryIndex = index;
		editModalSummaryText = text;
		// Estimate clip time from chunk data
		const chunks = currentFile?.chunks || [];
		if (chunks[index]) {
			editModalClipStart = chunks[index].start_time ?? 0;
			editModalClipEnd = chunks[index].end_time ?? (editModalClipStart + 60);
		} else {
			const summaries = currentFile?.chunk_summaries || [];
			const segDur = videoDuration / Math.max(1, summaries.length);
			editModalClipStart = index * segDur;
			editModalClipEnd = (index + 1) * segDur;
		}
		editModalOpen = true;
		editingSummaryIndex = index;
	}

	function cancelSummaryEdit() {
		editingSummaryIndex = -1;
		editModalOpen = false;
	}

	async function saveSummaryEdit() {
		if (!currentFile || !$currentVideo || editingSummaryIndex < 0) return;
		const summaries = [...(currentFile.chunk_summaries || [])];
		summaries[editingSummaryIndex] = editingSummaryText;
		
		try {
			const res = await apiClient.updateCaptionFile(
				$currentVideo.filename,
				currentFile.filename,
				{ chunk_summaries: summaries, caption_type: currentFile.caption_type || "narration" }
			);
			if (res.success && res.data) {
				localCaptionFiles[selectedFileIndex] = res.data;
				showAlert("success", "Chunk summary updated");
			} else {
				showAlert("error", "Failed to update chunk summary");
			}
		} catch (error) {
			showAlert("error", `Error: ${error}`);
		}
		editingSummaryIndex = -1;
	}

	// Delete chunk summary
	async function deleteChunkSummary(index: number) {
		if (!currentFile || !$currentVideo) return;
		const summaries = [...(currentFile.chunk_summaries || [])];
		if (index < 0 || index >= summaries.length) return;
		summaries.splice(index, 1);
		try {
			const res = await apiClient.updateCaptionFile(
				$currentVideo.filename,
				currentFile.filename,
				{ chunk_summaries: summaries, caption_type: currentFile.caption_type || "narration" }
			);
			if (res.success && res.data) {
				localCaptionFiles[selectedFileIndex] = res.data;
				showAlert("success", "Chunk summary deleted");
			} else {
				showAlert("error", "Failed to delete chunk summary");
			}
		} catch (error) {
			showAlert("error", `Error: ${error}`);
		}
	}

	/** Save caption from modal data */
	async function saveCaptionFromModal(data: any) {
		if (!currentFile || !$currentVideo) return;
		const index = data.index;
		const updatedCaptions = [...currentCaptions];
		updatedCaptions[index] = {
			...currentCaptions[index],  // preserve ALL existing fields
			text: data.text,
			start: data.start,
			end: data.end,
			importance: data.importance,
			importance_reasoning: data.importance_reasoning,
			confidence: data.confidence,
			confidence_reasoning: data.confidence_reasoning,
			optimal_sampling_rate: data.optimal_sampling_rate,
			optimal_sampling_rate_reasoning: data.optimal_sampling_rate_reasoning,
			optimal_resolution: data.optimal_resolution,
			optimal_resolution_reasoning: data.optimal_resolution_reasoning,
			...(data.description ? { description: data.description } : {}),
		};
		try {
			const res = await apiClient.updateCaptionFile(
				$currentVideo.filename,
				currentFile.filename,
				{ captions: updatedCaptions }
			);
			if (res.success && res.data) {
				localCaptionFiles[selectedFileIndex] = res.data;
				showAlert("success", "Caption updated");
			} else {
				showAlert("error", "Failed to update caption");
			}
		} catch (error) {
			showAlert("error", `Error: ${error}`);
		}
	}

	/** Save summary from modal data */
	async function saveSummaryFromModal(data: any) {
		if (!currentFile || !$currentVideo) return;
		const summaries = [...(currentFile.chunk_summaries || [])];
		summaries[data.index] = data.text;
		try {
			const res = await apiClient.updateCaptionFile(
				$currentVideo.filename,
				currentFile.filename,
				{ chunk_summaries: summaries, caption_type: currentFile.caption_type || "narration" }
			);
			if (res.success && res.data) {
				localCaptionFiles[selectedFileIndex] = res.data;
				showAlert("success", "Chunk summary updated");
			} else {
				showAlert("error", "Failed to update chunk summary");
			}
		} catch (error) {
			showAlert("error", `Error: ${error}`);
		}
	}

	/** Modal callbacks */
	async function handleModalSave(data: any) {
		if (data.type === 'caption') {
			await saveCaptionFromModal(data);
		} else {
			await saveSummaryFromModal(data);
		}
		editModalOpen = false;
		editingCaptionIndex = -1;
		editingSummaryIndex = -1;
	}

	function handleModalCancel() {
		editModalOpen = false;
		editingCaptionIndex = -1;
		editingSummaryIndex = -1;
	}

	async function handleModalSaveAndNext(data: any) {
		if (data.type === 'caption') {
			await saveCaptionFromModal(data);
			const nextIdx = data.index + 1;
			if (nextIdx < currentCaptions.length) {
				// Navigate to next and open editor
				// Need to re-read from latest data (just saved)
				const nextCap = localCaptionFiles[selectedFileIndex]?.captions?.[nextIdx];
				if (nextCap) {
					selectCaption(nextIdx);
					startEdit(nextIdx);
					return;
				}
			}
		} else {
			await saveSummaryFromModal(data);
			const summaries = localCaptionFiles[selectedFileIndex]?.chunk_summaries || [];
			const nextIdx = data.index + 1;
			if (nextIdx < summaries.length) {
				startSummaryEdit(nextIdx, summaries[nextIdx]);
				return;
			}
		}
		// If no next, just close
		editModalOpen = false;
		editingCaptionIndex = -1;
		editingSummaryIndex = -1;
	}

	async function handleModalSaveAndPrev(data: any) {
		if (data.type === 'caption') {
			await saveCaptionFromModal(data);
			const prevIdx = data.index - 1;
			if (prevIdx >= 0) {
				const prevCap = localCaptionFiles[selectedFileIndex]?.captions?.[prevIdx];
				if (prevCap) {
					selectCaption(prevIdx);
					startEdit(prevIdx);
					return;
				}
			}
		} else {
			await saveSummaryFromModal(data);
			const prevIdx = data.index - 1;
			if (prevIdx >= 0) {
				const summaries = localCaptionFiles[selectedFileIndex]?.chunk_summaries || [];
				startSummaryEdit(prevIdx, summaries[prevIdx]);
				return;
			}
		}
		// If no prev, just close
		editModalOpen = false;
		editingCaptionIndex = -1;
		editingSummaryIndex = -1;
	}

	// Keep legacy saveEdit for any remaining references
	async function saveEdit() {
		// Not used anymore – modal handles saving
		editingCaptionIndex = -1;
	}

	// Review actions
	async function setReviewStatus(status: ReviewStatus) {
		if (!currentFile || !$currentVideo) return;
		const review: HumanReview = {
			reviewed: status !== "pending",
			status,
			timestamp: new Date().toISOString(),
		};
		try {
			const res = await apiClient.updateCaptionFile(
				$currentVideo.filename,
				currentFile.filename,
				{ human_review: review }
			);
			if (res.success && res.data) {
				localCaptionFiles[selectedFileIndex] = res.data;
				showAlert("success", `Marked as ${status}`);
			} else {
				showAlert("error", "Failed to update review status");
			}
		} catch (error) {
			showAlert("error", `Error: ${error}`);
		}
	}

	// Split caption at a given time
	async function splitCaptionAtTime(time: number) {
		if (!currentFile || !$currentVideo) return;
		const captions = [...currentCaptions];
		// Find caption containing this time
		const idx = captions.findIndex(c => {
			const s = parseTimestamp(c.start);
			const e = parseTimestamp(c.end);
			return time > s && time < e;
		});
		if (idx < 0) {
			showAlert("info", "No caption at this time to split");
			return;
		}
		const cap = captions[idx];
		const splitTimeStr = formatTimestamp(time);
		const first: Caption = {
			text: cap.text, start: cap.start, end: splitTimeStr,
			importance: cap.importance, confidence: cap.confidence,
			...(cap.description ? { description: {
				...cap.description,
				// Deep-copy arrays so the two halves don't share references
				audio_transcript: Array.isArray(cap.description.audio_transcript)
					? [...cap.description.audio_transcript]
					: cap.description.audio_transcript,
				people: Array.isArray(cap.description.people)
					? [...cap.description.people]
					: cap.description.people,
			}} : {}),
		};
		const second: Caption = {
			text: "", start: splitTimeStr, end: cap.end,
			importance: cap.importance, confidence: cap.confidence,
			...(cap.description ? { description: {
				activities: "", objects: "", environment: "", visible_text: "",
				audio_transcript: [], people: [],
			}} : {}),
		};
		captions.splice(idx, 1, first, second);
		try {
			const res = await apiClient.updateCaptionFile(
				$currentVideo.filename,
				currentFile.filename,
				{ captions }
			);
			if (res.success && res.data) {
				localCaptionFiles[selectedFileIndex] = res.data;
				selectedCaptionIndex = idx + 1; // Select the new second part
				showAlert("success", "Caption split");
			} else {
				showAlert("error", "Failed to split caption");
			}
		} catch (error) {
			showAlert("error", `Error: ${error}`);
		}
	}

	// Merge caption with the next one
	async function mergeWithNext(index: number) {
		if (!currentFile || !$currentVideo) return;
		const captions = [...currentCaptions];
		if (index < 0 || index >= captions.length - 1) return;
		const current = captions[index];
		const next = captions[index + 1];
		/** Merge two string-typed description fields */
		const mergeStr = (a: string | undefined, b: string | undefined): string =>
			[a, b].filter(x => x !== undefined && x !== null).join(" ").trim();

		/** Merge two array-typed description fields, handling legacy string fallback */
		function mergeArr<T>(a: T[] | string | undefined, b: T[] | string | undefined): T[] {
			const toArr = (v: T[] | string | undefined): T[] => {
				if (Array.isArray(v)) return v;
				return [];
			};
			return [...toArr(a), ...toArr(b)];
		}

		const hasDesc = current.description || next.description;
		const importanceRank: Record<string, number> = { high: 3, medium: 2, low: 1 };
		const mergedImportance = (importanceRank[current.importance ?? 'medium'] ?? 2) >= (importanceRank[next.importance ?? 'medium'] ?? 2) ? current.importance : next.importance;
		const confidenceRank: Record<string, number> = { 'very high': 5, 'high': 4, 'medium': 3, 'low': 2, 'very low': 1 };
		const mergedConfidence = (confidenceRank[current.confidence ?? 'medium'] ?? 3) <= (confidenceRank[next.confidence ?? 'medium'] ?? 3) ? current.confidence : next.confidence;
		const merged: Caption = {
			text: `${current.text} ${next.text}`.trim(),
			start: current.start,
			end: next.end,
			importance: mergedImportance,
			confidence: mergedConfidence,
			...(hasDesc ? {
				description: {
					activities: mergeStr(current.description?.activities, next.description?.activities),
					objects: mergeStr(current.description?.objects, next.description?.objects),
					environment: mergeStr(current.description?.environment, next.description?.environment),
					visible_text: mergeStr(current.description?.visible_text, next.description?.visible_text),
					audio_transcript: mergeArr(current.description?.audio_transcript, next.description?.audio_transcript),
					people: mergeArr(current.description?.people, next.description?.people),
				}
			} : {}),
		};
		captions.splice(index, 2, merged);
		try {
			const res = await apiClient.updateCaptionFile(
				$currentVideo.filename,
				currentFile.filename,
				{ captions }
			);
			if (res.success && res.data) {
				localCaptionFiles[selectedFileIndex] = res.data;
				selectedCaptionIndex = index;
				showAlert("success", "Captions merged");
			} else {
				showAlert("error", "Failed to merge captions");
			}
		} catch (error) {
			showAlert("error", `Error: ${error}`);
		}
	}

	// Delete caption
	async function deleteCaption(index: number) {
		if (!currentFile || !$currentVideo) return;
		const captions = [...currentCaptions];
		captions.splice(index, 1);
		try {
			const res = await apiClient.updateCaptionFile(
				$currentVideo.filename,
				currentFile.filename,
				{ captions }
			);
			if (res.success && res.data) {
				localCaptionFiles[selectedFileIndex] = res.data;
				if (selectedCaptionIndex >= captions.length) {
					selectedCaptionIndex = captions.length - 1;
				}
				showAlert("success", "Caption deleted");
			}
		} catch (error) {
			showAlert("error", `Error: ${error}`);
		}
	}

	// Add new caption
	async function addCaption() {
		if (!currentFile || !$currentVideo || !newCaptionStart || !newCaptionEnd) return;
		const captions = [...currentCaptions];
		const newCap: Caption = {
			text: newCaptionText,
			start: newCaptionStart,
			end: newCaptionEnd,
		};
		// Insert in sorted order by start time
		const insertTime = parseTimestamp(newCaptionStart);
		let insertIdx = captions.findIndex(c => parseTimestamp(c.start) > insertTime);
		if (insertIdx < 0) insertIdx = captions.length;
		captions.splice(insertIdx, 0, newCap);
		try {
			const res = await apiClient.updateCaptionFile(
				$currentVideo.filename,
				currentFile.filename,
				{ captions }
			);
			if (res.success && res.data) {
				localCaptionFiles[selectedFileIndex] = res.data;
				selectedCaptionIndex = insertIdx;
				showNewCaptionForm = false;
				newCaptionText = "";
				newCaptionStart = "";
				newCaptionEnd = "";
				showAlert("success", "Caption added");
			}
		} catch (error) {
			showAlert("error", `Error: ${error}`);
		}
	}

	// Create new caption file
	async function createNewFile() {
		if (!$currentVideo || !newFileType.trim()) return;
		try {
			const res = await apiClient.createCaptionFile($currentVideo.filename, newFileType.trim(), []);
			if (res.success && res.data) {
				localCaptionFiles = [...localCaptionFiles, res.data];
				selectedFileIndex = localCaptionFiles.length - 1;
				showNewFileForm = false;
				newFileType = "narration";
				showAlert("success", "Caption file created");
			}
		} catch (error) {
			showAlert("error", `Error: ${error}`);
		}
	}

	// Delete caption file
	async function deleteCaptionFile(index: number) {
		if (!$currentVideo) return;
		const file = localCaptionFiles[index];
		if (!file) return;
		try {
			const res = await apiClient.deleteCaptionFile($currentVideo.filename, file.filename);
			if (res.success) {
				localCaptionFiles = localCaptionFiles.filter((_, i) => i !== index);
				if (selectedFileIndex >= localCaptionFiles.length) {
					selectedFileIndex = Math.max(0, localCaptionFiles.length - 1);
				}
				showAlert("success", "Caption file deleted");
			}
		} catch (error) {
			showAlert("error", `Error: ${error}`);
		}
	}

	// Context menu handlers
	function handleContextMenu(e: MouseEvent, time: number) {
		contextMenuOpen = true;
		contextMenuX = e.clientX;
		contextMenuY = e.clientY;
		contextMenuTime = time;
	}

	function closeContextMenu() {
		contextMenuOpen = false;
	}

	function contextSplit() {
		splitCaptionAtTime(contextMenuTime);
		contextMenuOpen = false;
	}

	// Get current caption at playback time
	const activeCaptionIndex = $derived.by(() => {
		return currentCaptions.findIndex(c => {
			const s = parseTimestamp(c.start);
			const e = parseTimestamp(c.end);
			return videoCurrentTime >= s && videoCurrentTime < e;
		});
	});

	const renderItems = $derived.by(() => {
		if (!currentFile) return [];
		let items: any[] = [];
		let summaries = currentFile.chunk_summaries || [];
		let chunks = currentFile.chunks || [];
		
		for (let i = 0; i < summaries.length; i++) {
			items.push({
				type: 'summary',
				index: i,
				text: summaries[i],
				start: chunks[i]?.start_time ?? (i * videoDuration / Math.max(1, summaries.length))
			});
		}

		for (let i = 0; i < currentCaptions.length; i++) {
			items.push({
				type: 'caption',
				index: i,
				caption: currentCaptions[i],
				start: parseTimestamp(currentCaptions[i].start)
			});
		}

		items.sort((a, b) => {
			if (Math.abs(a.start - b.start) < 0.1) {
				if (a.type === 'summary' && b.type === 'caption') return -1;
				if (a.type === 'caption' && b.type === 'summary') return 1;
			}
			return a.start - b.start;
		});

		return items;
	});

	// Update timespan on caption
	async function updateCaptionTimespan(index: number, field: 'start' | 'end', value: string) {
		if (!currentFile || !$currentVideo) return;
		const captions = [...currentCaptions];
		captions[index] = { ...captions[index], [field]: value };
		try {
			const res = await apiClient.updateCaptionFile(
				$currentVideo.filename,
				currentFile.filename,
				{ captions }
			);
			if (res.success && res.data) {
				localCaptionFiles[selectedFileIndex] = res.data;
			}
		} catch (error) {
			showAlert("error", `Error: ${error}`);
		}
	}
</script>

{#if $playerSectionActive && $currentVideo}
	<Card>
		<CardHeader class="flex-row items-center justify-between">
			<div>
				<CardTitle class="text-lg font-semibold">Caption Review</CardTitle>
				<p class="text-sm text-muted-foreground mt-1">
					{$currentVideo.filename} • {localCaptionFiles.length} caption file{localCaptionFiles.length !== 1 ? "s" : ""}
				</p>
			</div>
			<Button variant="outline" onclick={goBack}>← Back to Videos</Button>
		</CardHeader>
		<CardContent>
			<!-- Caption Files Panel -->
			<div class="mb-4 border border-border rounded-lg p-3 bg-card">
				<div class="flex items-center justify-between mb-2">
					<h3 class="text-sm font-semibold text-foreground">Caption Files ({localCaptionFiles.length})</h3>
					<Button variant="outline" size="sm" onclick={() => showNewFileForm = !showNewFileForm}>
						{showNewFileForm ? "Cancel" : "+ New File"}
					</Button>
				</div>
				{#if showNewFileForm}
					<div class="flex items-center gap-2 mb-2 p-2 bg-secondary rounded">
						<Input
							bind:value={newFileType}
							placeholder="Caption type (e.g. narration)"
							class="text-sm h-8"
						/>
						<Button size="sm" onclick={createNewFile}>Create</Button>
					</div>
				{/if}
				{#if captionsLoading}
					<div class="text-sm text-muted-foreground py-2">Loading caption files...</div>
				{:else if localCaptionFiles.length === 0}
					<div class="text-sm text-muted-foreground py-2">No caption files found. Create one to get started.</div>
				{:else}
					<div class="flex flex-wrap gap-2">
						{#each localCaptionFiles as file, i}
							{@const status = getReviewStatus(file.human_review)}
							<button
								class="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md border transition-colors {i === selectedFileIndex ? 'border-primary bg-primary/10 text-primary font-medium' : 'border-border bg-card text-foreground hover:bg-secondary'}"
								onclick={() => { selectedFileIndex = i; selectedCaptionIndex = -1; editingCaptionIndex = -1; }}
							>
								<span>{file.caption_type || file.filename}</span>
								<span class="text-xs text-muted-foreground">({file.captions?.length ?? 0})</span>
								<Badge variant={REVIEW_BADGE_VARIANT[status] as "success" | "destructive" | "warning"} class="text-[10px] px-1 py-0">{status}</Badge>
							</button>
						{/each}
					</div>
				{/if}
			</div>

			<!-- Video Player Section -->
			<div class="space-y-4">
				<div class="relative flex flex-col overflow-hidden">
					<div class="relative video-player-wrapper flex-shrink-1 min-h-0 overflow-hidden">
						{#if isVideoSeeking}
							<div class="absolute inset-0 flex items-center justify-center bg-black/30 z-20 rounded-lg">
								<div class="spinner"></div>
							</div>
						{/if}
						<div class="relative aspect-video mx-auto" style="max-height: 500px; width: 100%;">
							<video
								bind:this={videoPlayer}
								src={activeVideoSource}
								preload="metadata"
								class="w-full h-full object-contain rounded-t-lg bg-black cursor-pointer"
								onplay={() => { isPlaying = true; }}
								onpause={() => { isPlaying = false; }}
								onloadedmetadata={() => { if (videoPlayer) videoDuration = videoPlayer.duration || 0; }}
								onloadeddata={() => {
									if (videoPlayer) videoDuration = videoPlayer.duration || 0;
									if (!audioContext) initAudioAmplification();
								}}
								ontimeupdate={() => { if (videoPlayer && !isVideoSeeking) videoCurrentTime = videoPlayer.currentTime; }}
								onseeking={() => { isVideoSeeking = true; }}
								onseeked={() => { isVideoSeeking = false; }}
								onclick={() => { if (videoPlayer) { if (videoPlayer.paused) videoPlayer.play(); else videoPlayer.pause(); } }}
							>
								<track kind="captions" />
							</video>
							<!-- Active caption overlay -->
							{#if activeCaptionIndex >= 0}
								<div class="absolute bottom-12 left-0 right-0 flex justify-center pointer-events-none z-10">
									<div class="bg-black/75 text-white text-sm px-4 py-2 rounded max-w-[80%] text-center">
										{currentCaptions[activeCaptionIndex].text}
									</div>
								</div>
							{/if}
						</div>
						<div class="video-controls bg-secondary border-t border-border px-3 py-2 rounded-b-lg">
							<VideoProgressBar
								videoElement={videoPlayer}
								videoFilename={$currentVideo?.filename || ""}
								duration={videoDuration}
								currentTime={videoCurrentTime}
								annotations={[]}
								onSeek={(time) => {
									if (videoPlayer) {
										videoCurrentTime = time;
										videoPlayer.currentTime = time;
									}
								}}
							/>
							<VideoControls
								{isPlaying}
								{volumeAmplification}
								onTogglePlay={() => { if (videoPlayer) { if (videoPlayer.paused) videoPlayer.play(); else videoPlayer.pause(); } }}
								onToggleMute={() => { if (videoPlayer) videoPlayer.muted = !videoPlayer.muted; }}
								onVolumeChange={setVolumeAmplification}
								onFullscreen={() => { if (videoPlayer) { if (document.fullscreenElement) document.exitFullscreen(); else videoPlayer.requestFullscreen(); } }}
							/>
						</div>
					</div>
				</div>

				<!-- Secondary Timeline (±3 min) -->
				{#if currentFile}
					<div class="border border-border rounded-lg p-2 bg-card">
						<CaptionTimeline
							duration={videoDuration}
							currentTime={videoCurrentTime}
							captions={currentCaptions}
							{selectedCaptionIndex}
							windowSeconds={180}
							onSeek={(time) => {
								if (videoPlayer) {
									videoCurrentTime = time;
									videoPlayer.currentTime = time;
								}
							}}
							onCaptionSelect={(idx) => { selectCaption(idx); }}
							onContextMenu={handleContextMenu}
						/>
					</div>
				{/if}

				<!-- Review Actions for current file -->
				{#if currentFile}
					<div class="flex items-center gap-2 flex-wrap">
						<span class="text-sm font-medium text-muted-foreground">File Review:</span>
						<Badge variant={REVIEW_BADGE_VARIANT[currentReviewStatus] as "success" | "destructive" | "warning"}>
							{REVIEW_LABEL[currentReviewStatus]}
						</Badge>
						<div class="flex gap-1 ml-2">
							<Button
								size="sm"
								variant={currentReviewStatus === 'accepted' ? 'default' : 'outline'}
								onclick={() => setReviewStatus('accepted')}
							>✓ Accept</Button>
							<Button
								size="sm"
								variant={currentReviewStatus === 'rejected' ? 'destructive' : 'outline'}
								onclick={() => setReviewStatus('rejected')}
							>✗ Reject</Button>
							<Button
								size="sm"
								variant={currentReviewStatus === 'pending' ? 'secondary' : 'outline'}
								onclick={() => setReviewStatus('pending')}
							>⏳ Pending</Button>
						</div>
						<div class="ml-auto flex gap-1">
							<Button
								size="sm"
								variant="outline"
								onclick={() => { showNewCaptionForm = !showNewCaptionForm; }}
							>
								{showNewCaptionForm ? "Cancel" : "+ Add Caption"}
							</Button>
							<Button
								size="sm"
								variant="outline"
								class="text-destructive"
								onclick={() => deleteCaptionFile(selectedFileIndex)}
							>Delete File</Button>
						</div>
					</div>
				{/if}

				<!-- Add New Caption Form -->
				{#if showNewCaptionForm && currentFile}
					<div class="border border-border rounded-lg p-3 bg-secondary/50">
						<h4 class="text-sm font-semibold mb-2">Add New Caption</h4>
						<div class="grid grid-cols-[1fr_auto_auto] gap-2 items-end">
							<label>
								<span class="text-xs text-muted-foreground">Text</span>
								<Input bind:value={newCaptionText} placeholder="Caption text" class="text-sm h-8" />
							</label>
							<label>
								<span class="text-xs text-muted-foreground">Start</span>
								<Input bind:value={newCaptionStart} placeholder="0:00" class="text-sm h-8 w-20" />
							</label>
							<label>
								<span class="text-xs text-muted-foreground">End</span>
								<Input bind:value={newCaptionEnd} placeholder="0:30" class="text-sm h-8 w-20" />
							</label>
						</div>
						<div class="flex justify-end mt-2">
							<Button size="sm" onclick={addCaption}>Add</Button>
						</div>
					</div>
				{/if}

				<!-- Captions List -->
				{#if currentFile}
					<div class="border border-border rounded-lg bg-card">
						<div class="flex items-center justify-between p-3 border-b border-border">
							<h3 class="text-sm font-semibold text-foreground">
								Captions — {currentFile.caption_type || "unknown type"} ({currentCaptions.length})
							</h3>
							<div class="flex items-center gap-2">
								<Button size="sm" variant="outline" onclick={navigatePrevCaption} disabled={currentCaptions.length === 0}>← Prev</Button>
								<span class="text-xs text-muted-foreground">
									{selectedCaptionIndex >= 0 ? selectedCaptionIndex + 1 : 0} / {currentCaptions.length}
								</span>
								<Button size="sm" variant="outline" onclick={navigateNextCaption} disabled={currentCaptions.length === 0}>Next →</Button>
							</div>
						</div>
						<div class="max-h-[400px] overflow-y-auto divide-y divide-border">
							{#each renderItems as item}
								{#if item.type === 'summary'}
									<div class="p-3 bg-secondary/20 border-l-4 border-l-primary/50 transition-colors">
										<div class="flex items-start gap-3">
											<div class="flex-shrink-0 text-xs font-mono text-muted-foreground pt-0.5 w-24">
												<button class="hover:text-primary transition-colors text-left" onclick={() => seekTo(formatTimestamp(item.start))}>
													Chunk #{item.index + 1}
												</button>
											</div>
											<div class="flex-1 text-sm text-foreground leading-relaxed italic opacity-90">
												<span class="font-semibold mr-1">Summary:</span> {item.text}
											</div>
											<div class="flex-shrink-0 flex items-center gap-1">
												<button
													class="p-1 rounded hover:bg-secondary text-muted-foreground hover:text-foreground transition-colors"
													title="Edit Summary"
													onclick={() => startSummaryEdit(item.index, item.text)}
												>
													✏️
												</button>
												<button
													class="p-1 rounded hover:bg-secondary text-muted-foreground hover:text-destructive transition-colors"
													title="Delete Summary"
													onclick={() => deleteChunkSummary(item.index)}
												>
													🗑️
												</button>
											</div>
										</div>
									</div>
								{:else if item.type === 'caption'}
								{@const i = item.index}
								{@const cap = item.caption}
								{@const isActive = i === activeCaptionIndex}
								{@const isSelected = i === selectedCaptionIndex}
								<div
									class="p-3 transition-colors cursor-pointer {isActive ? 'bg-primary/5' : ''} {isSelected ? 'bg-primary/10 border-l-2 border-l-primary' : 'border-l-2 border-l-transparent'}"
									data-caption-index={i}
									onclick={() => selectCaption(i)}
									role="button"
									tabindex="0"
									onkeydown={(e) => { if (e.key === 'Enter') selectCaption(i); }}
								>
										<div class="flex items-start gap-3">
											<div class="flex-shrink-0 text-xs font-mono text-muted-foreground pt-0.5 w-24">
												<button
													class="hover:text-primary transition-colors"
													onclick={(e) => { e.stopPropagation(); seekTo(cap.start); }}
												>
													{cap.start}
												</button>
												<span class="mx-0.5">→</span>
												<button
													class="hover:text-primary transition-colors"
													onclick={(e) => { e.stopPropagation(); seekTo(cap.end); }}
												>
													{cap.end}
												</button>
											</div>
											<div class="flex-1 text-sm text-foreground leading-relaxed">
												{#if cap.importance}
													<span class="inline-block text-[10px] font-semibold px-1.5 py-0.5 rounded mr-1 mb-1" style="background-color: {IMPORTANCE_COLOR[(cap.importance) as ImportanceLevel] ?? IMPORTANCE_COLOR_DEFAULT}20; color: {IMPORTANCE_COLOR[(cap.importance) as ImportanceLevel] ?? IMPORTANCE_COLOR_DEFAULT}; border: 1px solid {IMPORTANCE_COLOR[(cap.importance) as ImportanceLevel] ?? IMPORTANCE_COLOR_DEFAULT}40;">
														{cap.importance}
													</span>
												{/if}
												{#if cap.confidence}
													<span class="inline-block text-[10px] font-semibold px-1.5 py-0.5 rounded mr-1 mb-1" style="background-color: {CONFIDENCE_COLOR[(cap.confidence) as ConfidenceLevel] ?? CONFIDENCE_COLOR_DEFAULT}20; color: {CONFIDENCE_COLOR[(cap.confidence) as ConfidenceLevel] ?? CONFIDENCE_COLOR_DEFAULT}; border: 1px solid {CONFIDENCE_COLOR[(cap.confidence) as ConfidenceLevel] ?? CONFIDENCE_COLOR_DEFAULT}40;">
														conf: {cap.confidence}
													</span>
												{/if}
												{#if cap.optimal_sampling_rate}
													<span class="inline-block text-[10px] font-medium px-1.5 py-0.5 rounded mr-1 mb-1 bg-blue-50 text-blue-700 border border-blue-200">
														⚡ {cap.optimal_sampling_rate}
													</span>
												{/if}
												{#if cap.optimal_resolution}
													<span class="inline-block text-[10px] font-medium px-1.5 py-0.5 rounded mr-1 mb-1 bg-purple-50 text-purple-700 border border-purple-200">
														🔍 {cap.optimal_resolution}
													</span>
												{/if}
												{#if cap.description}
													{#if str(cap.description.activities)}
														<div><span class="font-medium text-muted-foreground text-xs">Activities:</span> {str(cap.description.activities)}</div>
													{/if}
													{#if str(cap.description.objects)}
														<div><span class="font-medium text-muted-foreground text-xs">Objects:</span> {str(cap.description.objects)}</div>
													{/if}
													{#if str(cap.description.environment)}
														<div><span class="font-medium text-muted-foreground text-xs">Environment:</span> {str(cap.description.environment)}</div>
													{/if}
													{#if Array.isArray(cap.description.people) && cap.description.people.length > 0}
														<div>
															<span class="font-medium text-muted-foreground text-xs">People:</span>
															{#each cap.description.people as person}
																<div class="ml-3 text-xs">
																	{#if person.person}
																		<span class="inline-block font-semibold px-1 py-0 rounded text-[10px] mr-1" style="background-color: hsl(217 91% 60% / 0.15); color: hsl(217 91% 60%); border: 1px solid hsl(217 91% 60% / 0.3);">{person.person}</span>
																	{/if}
																	{person.description}
																</div>
															{/each}
														</div>
													{:else if typeof cap.description.people === 'string' && cap.description.people}
														<div><span class="font-medium text-muted-foreground text-xs">People:</span> {cap.description.people}</div>
													{/if}
													{#if Array.isArray(cap.description.audio_transcript) && cap.description.audio_transcript.length > 0}
														<div>
															<span class="font-medium text-muted-foreground text-xs">Audio:</span>
															{#each cap.description.audio_transcript as line}
																<div class="ml-3 text-xs">
																	{#if line.speaker}
																		<span class="inline-block font-semibold px-1 py-0 rounded text-[10px] mr-1" style="background-color: hsl(142 71% 45% / 0.15); color: hsl(142 71% 45%); border: 1px solid hsl(142 71% 45% / 0.3);">{line.speaker}</span>
																	{:else}
																		<span class="inline-block font-semibold px-1 py-0 rounded text-[10px] mr-1" style="background-color: hsl(38 92% 50% / 0.15); color: hsl(38 92% 50%); border: 1px solid hsl(38 92% 50% / 0.3);">🔊</span>
																	{/if}
																	{line.transcript}
																</div>
															{/each}
														</div>
													{:else if typeof cap.description.audio_transcript === 'string' && cap.description.audio_transcript}
														<div><span class="font-medium text-muted-foreground text-xs">Audio:</span> {cap.description.audio_transcript}</div>
													{/if}
													{#if str(cap.description.visible_text)}
														<div><span class="font-medium text-muted-foreground text-xs">Text:</span> {str(cap.description.visible_text)}</div>
													{/if}
												{:else}
													{cap.text || "(empty)"}
												{/if}
											</div>
											<div class="flex-shrink-0 flex items-center gap-1">
												<button
													class="p-1 rounded hover:bg-secondary text-muted-foreground hover:text-foreground transition-colors"
													title="Edit"
													onclick={(e) => { e.stopPropagation(); startEdit(i); }}
												>
													✏️
												</button>
												<button
													class="p-1 rounded hover:bg-secondary text-muted-foreground hover:text-foreground transition-colors"
													title="Split at midpoint"
													onclick={(e) => {
														e.stopPropagation();
														const mid = (parseTimestamp(cap.start) + parseTimestamp(cap.end)) / 2;
														splitCaptionAtTime(mid);
													}}
												>
													✂️
												</button>
												{#if i < currentCaptions.length - 1}
													<button
														class="p-1 rounded hover:bg-secondary text-muted-foreground hover:text-foreground transition-colors"
														title="Merge with next"
														onclick={(e) => { e.stopPropagation(); mergeWithNext(i); }}
													>
														🔗
													</button>
												{/if}
												<button
													class="p-1 rounded hover:bg-secondary text-muted-foreground hover:text-destructive transition-colors"
													title="Delete"
													onclick={(e) => { e.stopPropagation(); deleteCaption(i); }}
												>
													🗑️
												</button>
											</div>
										</div>
								</div>
								{/if}
							{/each}
							{#if currentCaptions.length === 0}
								<div class="p-4 text-sm text-muted-foreground text-center">
									No captions in this file. Add one to get started.
								</div>
							{/if}
						</div>
					</div>
				{:else if !captionsLoading}
					<div class="border border-border rounded-lg p-8 bg-card text-center">
						<p class="text-muted-foreground">No caption files available. Create a new caption file to start reviewing.</p>
					</div>
				{/if}
			</div>
		</CardContent>
	</Card>

	<!-- All Caption Types Overview -->
	{#if localCaptionFiles.length > 1}
		<Card class="mt-4">
			<CardHeader>
				<CardTitle class="text-base font-semibold">All Caption Types Overview</CardTitle>
			</CardHeader>
			<CardContent>
				<div class="space-y-3">
					{#each localCaptionFiles as file, fileIdx}
						{@const status = getReviewStatus(file.human_review)}
						<div class="border border-border rounded-lg p-3 {fileIdx === selectedFileIndex ? 'border-primary bg-primary/5' : ''}">
							<div class="flex items-center justify-between mb-2">
								<div class="flex items-center gap-2">
									<button
										class="font-medium text-sm hover:text-primary transition-colors"
										onclick={() => { selectedFileIndex = fileIdx; selectedCaptionIndex = -1; }}
									>
										{file.caption_type || file.filename}
									</button>
									<Badge variant={REVIEW_BADGE_VARIANT[status] as "success" | "destructive" | "warning"} class="text-xs">{status}</Badge>
									<span class="text-xs text-muted-foreground">{file.captions?.length ?? 0} captions</span>
								</div>
							</div>
							<!-- Show first 3 captions as preview -->
							{#if file.captions && file.captions.length > 0}
								<div class="space-y-1">
									{#each file.captions.slice(0, 3) as cap}
										<div class="text-xs text-muted-foreground truncate">
											<span class="font-mono">{cap.start}→{cap.end}</span>: {cap.text}
										</div>
									{/each}
									{#if file.captions.length > 3}
										<div class="text-xs text-muted-foreground italic">...and {file.captions.length - 3} more</div>
									{/if}
								</div>
							{/if}
						</div>
					{/each}
				</div>
			</CardContent>
		</Card>
	{/if}

	<!-- Context Menu -->
	{#if contextMenuOpen}
		<div
			class="fixed z-50 bg-card border border-border rounded-lg shadow-lg py-1 min-w-[160px]"
			style="left: {contextMenuX}px; top: {contextMenuY}px;"
			role="menu"
		>
			<button
				class="w-full text-left px-3 py-1.5 text-sm hover:bg-secondary transition-colors"
				onclick={contextSplit}
				role="menuitem"
			>
				✂️ Split caption here ({formatTimestamp(contextMenuTime)})
			</button>
			<button
				class="w-full text-left px-3 py-1.5 text-sm hover:bg-secondary transition-colors"
				onclick={() => {
					if (videoPlayer) {
						videoPlayer.currentTime = contextMenuTime;
						videoCurrentTime = contextMenuTime;
					}
					contextMenuOpen = false;
				}}
				role="menuitem"
			>
				⏱️ Seek to {formatTimestamp(contextMenuTime)}
			</button>
			<button
				class="w-full text-left px-3 py-1.5 text-sm hover:bg-secondary transition-colors"
				onclick={() => {
					newCaptionStart = formatTimestamp(contextMenuTime);
					newCaptionEnd = formatTimestamp(Math.min(contextMenuTime + 30, videoDuration));
					showNewCaptionForm = true;
					contextMenuOpen = false;
				}}
				role="menuitem"
			>
				➕ Add caption at {formatTimestamp(contextMenuTime)}
			</button>
		</div>
	{/if}

	<!-- Caption Edit Modal -->
	<CaptionEditModal
		open={editModalOpen}
		editType={editModalType}
		videoSource={activeVideoSource}
		clipStart={editModalClipStart}
		clipEnd={editModalClipEnd}
		videoDuration={videoDuration}
		caption={editModalCaption}
		captionIndex={editModalCaptionIndex}
		totalCaptions={currentCaptions.length}
		summaryText={editModalSummaryText}
		summaryIndex={editModalSummaryIndex}
		totalSummaries={(currentFile?.chunk_summaries || []).length}
		onSave={handleModalSave}
		onCancel={handleModalCancel}
		onSaveAndNext={handleModalSaveAndNext}
		onSaveAndPrev={handleModalSaveAndPrev}
	/>
{/if}
