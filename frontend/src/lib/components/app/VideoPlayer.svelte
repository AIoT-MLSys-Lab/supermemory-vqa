<script lang="ts">
	import {
		Card,
		CardHeader,
		CardTitle,
		CardContent,
	} from "$lib/components/ui/card";
	import Button from "$lib/components/ui/button/Button.svelte";
	import Select from "$lib/components/ui/select/Select.svelte";
	import Label from "$lib/components/ui/label/Label.svelte";
	import Input from "$lib/components/ui/input/Input.svelte";
	import Badge from "$lib/components/ui/badge/Badge.svelte";
	import AnnotationItem from "./AnnotationItem.svelte";
	import AnnotationFilePanel from "./AnnotationFilePanel.svelte";
	import VideoControls from "./VideoControls.svelte";
	import BoundingBoxControls from "./BoundingBoxControls.svelte";
	import ActionBar from "./ActionBar.svelte";
	import AnnotationsPanel from "./AnnotationsPanel.svelte";
	import SummaryModal from "./SummaryModal.svelte";
	import PromptPreviewModal from "./PromptPreviewModal.svelte";
	import { StatusBadge, Chip } from "./ui";
	import AnnotationFileSelector from "./AnnotationFileSelector.svelte";
	import EditAnnotationModal from "./EditAnnotationModal.svelte";
	import AddAnnotationModal from "./AddAnnotationModal.svelte";
	import DebugModal from "./DebugModal.svelte";
	import BoundingBoxCanvas from "./BoundingBoxCanvas.svelte";
	import VideoProgressBar from "./VideoProgressBar.svelte";
	import AnnotationTimeline from "./AnnotationTimeline.svelte";
	import { parseTimestamp, formatTimestamp } from "$lib/utils";
	import {
		resolveVideoSource,
		collectVideoSourcesFromAnnotations,
	} from "$lib/utils/video-source";
	import type {
		Annotation,
		AnnotationFile,
		LocationBox,
		Prompt,
		PromptInputParameter,
	} from "$lib/types";
	import { apiClient } from "$lib/api";
	import {
		currentVideo,
		playerSectionActive,
		annotations,
		models,
		prompts,
		selectedModel,
		selectedPrompt,
		promptParameters,
		generateStatus,
		setAnnotations,
		updateAnnotation as updateAnnotationInStore,
		deleteAnnotation as deleteAnnotationFromStore,
		addAnnotation as addAnnotationToStore,
		showAlert,
	} from "$lib/stores";
	import { onMount, onDestroy } from "svelte";

	let videoPlayer: HTMLVideoElement | undefined = $state();

	// Audio amplification state (Web Audio API)
	let audioContext: AudioContext | undefined = $state();
	let gainNode: GainNode | undefined = $state();
	let mediaSource: MediaElementAudioSourceNode | undefined = $state();
	let volumeAmplification = $state(100); // 0-200%
	const SEEK_STEP = 5; // seconds to seek with arrow keys
	let boundingBoxCanvas: BoundingBoxCanvas | undefined = $state();
	let annotationsLoading = $state(false);

	// Video time tracking for custom progress bar
	let videoDuration = $state(0);
	let videoCurrentTime = $state(0);
	let isPlaying = $state(false);
	let isVideoSeeking = $state(false);

	// Annotation file management
	let annotationFiles = $state<AnnotationFile[]>([]);
	let selectedAnnotationFiles = $state<string[]>([]);
	// Track which file each annotation came from (for editing/deleting)
	let annotationSourceFiles = $state<string[]>([]);

	// Modals
	let editModalOpen = $state(false);
	let addModalOpen = $state(false);
	let summaryModalOpen = $state(false);
	let promptPreviewModalOpen = $state(false);
	let editingAnnotation = $state<Annotation | null>(null);
	let editingIndex = $state(-1);

	// Debug Modal
	let debugModalOpen = $state(false);
	let debugModalTitle = $state("");
	let debugModalContent = $state("");
	let debugModalType = $state<"markdown" | "json" | "text">("text");

	// Summary data
	let summaryData = $state<Record<string, unknown> | null>(null);

	// Prompt preview
	let promptPreviewContent = $state("");
	let currentPromptDetails = $state<Prompt | null>(null);
	let promptParamValues = $state<Record<string, unknown>>({});

	// Bounding box display - using stable state that persists across re-renders
	// The key issue is that $state variables can be re-initialized during Svelte's reactive cycles
	// So we track the box display separately with explicit flags
	let activeBox = $state<LocationBox | null>(null);
	let activeBoxIndex = $state(-1);
	let activeAnnotationIndex = $state(-1);
	let activeBoxEvidenceIndex = $state(-1);
	let boxEditMode = $state(false);
	let boxDrawMode = $state(false);
	let annotationsPanelCollapsed = $state(false);
	let annotationFilesPanelCollapsed = $state(false);
	let originalBoxCoords = $state<number[] | null>(null); // For cancel functionality
	let editingBoxTimestamp = $state("");
	let editingBoxDescription = $state("");

	// This flag explicitly controls whether box controls are shown
	// It's set true when a box is clicked and false only on explicit clear
	let showBoxControls = $state(false);

	// Active time marker for progress bar dragging
	interface ActiveTimeMarker {
		type: "timespan" | "timestamp";
		startTime: number;
		endTime?: number;
		// Context for updating the annotation
		annotationIndex: number;
		field:
			| "question_time_span"
			| "evidence_time_span"
			| "time_span"
			| "box_timestamp";
		evidenceIndex?: number;
		spanIndex?: number;
		boxIndex?: number;
	}
	let activeTimeMarker = $state<ActiveTimeMarker | null>(null);

	// Context menu state
	interface ContextMenuState {
		show: boolean;
		x: number;
		y: number;
		time: number;
		annotation?: Annotation;
		annotationIndex?: number;
		evidenceIndex?: number;
	}
	let contextMenu = $state<ContextMenuState>({
		show: false,
		x: 0,
		y: 0,
		time: 0,
	});

	// Timeline drag state for editing timespans
	let timelineDragState = $state<{
		type: "question" | "evidence";
		annotationIndex: number;
		evidenceIndex?: number;
		spanIndex?: number;
		edge: "start" | "end";
		originalTime: number;
	} | null>(null);

	// Handle time marker updates from progress bar dragging
	function handleTimeMarkerUpdate(marker: {
		type: "timespan" | "timestamp";
		startTime: number;
		endTime?: number;
	}) {
		if (!activeTimeMarker) return;
		activeTimeMarker = {
			...activeTimeMarker,
			startTime: marker.startTime,
			endTime: marker.endTime,
		};
	}

	// Save time marker changes when drag ends (called from progress bar)
	async function saveTimeMarkerChanges() {
		if (!activeTimeMarker || !$currentVideo) return;
		const annIdx = activeTimeMarker.annotationIndex;
		if (annIdx < 0 || annIdx >= $annotations.length) return;

		const sourceFile = getSourceFileForIndex(annIdx);
		if (!sourceFile) return;

		const annotation = { ...$annotations[annIdx] };
		const startStr = formatTimestamp(activeTimeMarker.startTime);
		const endStr =
			activeTimeMarker.endTime != null
				? formatTimestamp(activeTimeMarker.endTime)
				: undefined;

		if (activeTimeMarker.field === "question_time_span") {
			annotation.question_time_span = {
				start: startStr,
				...(endStr ? { end: endStr } : {}),
			};
		} else if (activeTimeMarker.field === "evidence_time_span") {
			const evIdx = activeTimeMarker.evidenceIndex ?? 0;
			const spIdx = activeTimeMarker.spanIndex ?? 0;
			if (annotation.answer_evidence?.[evIdx]?.time_spans?.[spIdx]) {
				const updatedEvidence = [...(annotation.answer_evidence || [])];
				const updatedSpans = [
					...(updatedEvidence[evIdx].time_spans || []),
				];
				updatedSpans[spIdx] = {
					start: startStr,
					...(endStr ? { end: endStr } : {}),
				};
				updatedEvidence[evIdx] = {
					...updatedEvidence[evIdx],
					time_spans: updatedSpans,
				};
				annotation.answer_evidence = updatedEvidence;
			}
		} else if (activeTimeMarker.field === "time_span") {
			annotation.time_span = {
				start: startStr,
				...(endStr ? { end: endStr } : {}),
			};
		} else if (activeTimeMarker.field === "box_timestamp") {
			const bIdx = activeTimeMarker.boxIndex ?? 0;
			if (annotation.location?.boxes?.[bIdx]) {
				const updatedBoxes = [...(annotation.location.boxes || [])];
				updatedBoxes[bIdx] = {
					...updatedBoxes[bIdx],
					timestamp: startStr,
				};
				annotation.location = {
					...annotation.location,
					boxes: updatedBoxes,
				};
			}
		}

		const localIndex = getLocalIndexInFile(annIdx);
		try {
			const result = await apiClient.updateAnnotation(
				$currentVideo.filename,
				sourceFile,
				localIndex,
				annotation,
			);
			if (result.success) {
				updateAnnotationInStore(annIdx, annotation);
				showAlert("success", "Time updated");
			} else {
				showAlert("error", result.error || "Failed to update time");
			}
		} catch (error) {
			showAlert("error", `Error: ${error}`);
		}
	}

	// Video source management
	// Instead of abstract streams, we track the currently playing video path
	let activeVideoSource = $state<string>("");

	// Derived list of unique sources from ALL annotations
	const availableVideoSources = $derived.by(() => {
		if (!$currentVideo) return [];

		// Use main video path
		const mainVideoPath = $currentVideo.path
			? resolveVideoSource($currentVideo.path)
			: `/uploads/${$currentVideo.filename}`;

		return collectVideoSourcesFromAnnotations(
			mainVideoPath,
			activeVideoSource,
			$annotations,
		);
	});

	// Initialize active video source
	$effect(() => {
		if ($currentVideo && !activeVideoSource) {
			// Use actual path if available
			activeVideoSource = $currentVideo.path
				? resolveVideoSource($currentVideo.path)
				: `/uploads/${$currentVideo.filename}`;
		}
	});

	function setActiveVideoSource(source: string, shouldSeek: boolean = true) {
		// Ensure source is resolved
		const resolvedSource = resolveVideoSource(source);

		if (resolvedSource === activeVideoSource) return;
		activeVideoSource = resolvedSource;

		// When switching sources, if we have an active annotation, seek to relevant time?
		// User request: "It will only show question stream if ... timestamp falls within question timespan"
		// Logic: If switching to Main Video, maybe seek to question start?
		// If switching to Evidence Video, seek to evidence start?
		// The previous logic was complex. For now, let's just switch. The Dropdown/Click usually implies a specific target context.

		// If triggered from Dropdown, we might want to find the first time span associated with this video.
		if (
			shouldSeek &&
			activeAnnotationIndex >= 0 &&
			$annotations[activeAnnotationIndex]
		) {
			const ann = $annotations[activeAnnotationIndex];
			const mainVideoPath = `/uploads/${$currentVideo!.filename}`; // Safe because check in effect

			let targetTime = "";

			if (resolvedSource === mainVideoPath) {
				// Question time
				targetTime = ann.question_time_span?.start || "";
			} else {
				// Find evidence with this path - check both raw and resolved
				// Note: ev.video_path logic in availableVideoSources resolved it, but here we might be comparing against raw in data

				// Helper to check if evidence matches current source
				const matchesSource = (path: string) => {
					return resolveVideoSource(path) === resolvedSource;
				};

				const ev = ann.answer_evidence?.find(
					(e) => e.video_path && matchesSource(e.video_path),
				);
				if (ev?.time_spans?.[0]?.start) {
					targetTime = ev.time_spans[0].start;
				} else if (
					ann.answer_video_path &&
					matchesSource(ann.answer_video_path) &&
					ann.time_span?.start
				) {
					// Legacy
					targetTime = ann.time_span.start;
				}
			}

			if (targetTime) seekTo(targetTime, true);
		}
	}

	// Keyboard navigation handler for video seeking
	function handleKeydown(e: KeyboardEvent) {
		// Only handle keys when video player exists and no input is focused
		const activeElement = document.activeElement;
		const isInputFocused =
			activeElement instanceof HTMLInputElement ||
			activeElement instanceof HTMLTextAreaElement ||
			activeElement instanceof HTMLSelectElement;

		if (isInputFocused || !videoPlayer) return;

		// Don't intercept arrow keys when bounding box edit mode is active
		// (arrow keys move the box in that case)
		const isBboxEditActive = boxEditMode && activeBox;

		if (e.key === " ") {
			e.preventDefault();
			if (videoPlayer.paused) {
				videoPlayer.play();
			} else {
				videoPlayer.pause();
			}
		} else if (e.key === "ArrowLeft" && !isBboxEditActive) {
			e.preventDefault();
			const newTime = Math.max(0, videoPlayer.currentTime - SEEK_STEP);
			videoPlayer.currentTime = newTime;
			videoCurrentTime = newTime; // Explicitly update state
		} else if (e.key === "ArrowRight" && !isBboxEditActive) {
			e.preventDefault();
			const newTime = Math.min(
				videoPlayer.duration || 0,
				videoPlayer.currentTime + SEEK_STEP,
			);
			videoPlayer.currentTime = newTime;
			videoCurrentTime = newTime; // Explicitly update state
		} else if (e.key === "[" && e.ctrlKey) {
			// Ctrl+[ - Navigate to previous annotation
			e.preventDefault();
			navigateToPreviousAnnotation();
		} else if (e.key === "]" && e.ctrlKey) {
			// Ctrl+] - Navigate to next annotation
			e.preventDefault();
			navigateToNextAnnotation();
		}
	}

	// Initialize audio amplification with Web Audio API
	function initAudioAmplification() {
		if (!videoPlayer || audioContext) return;

		try {
			audioContext = new AudioContext();
			gainNode = audioContext.createGain();
			mediaSource = audioContext.createMediaElementSource(videoPlayer);

			// Connect: video -> gain -> output
			mediaSource.connect(gainNode);
			gainNode.connect(audioContext.destination);

			// Set initial volume
			gainNode.gain.value = volumeAmplification / 100;
		} catch (error) {
			console.error("Failed to initialize audio amplification:", error);
			// Reset state to prevent inconsistent state
			audioContext = undefined;
			gainNode = undefined;
			mediaSource = undefined;
		}
	}

	// Update volume amplification
	function setVolumeAmplification(value: number) {
		volumeAmplification = Math.max(0, Math.min(200, value));
		if (gainNode) {
			gainNode.gain.value = volumeAmplification / 100;
		}
	}

	onMount(async () => {
		// Add keyboard listener for arrow key navigation
		document.addEventListener("keydown", handleKeydown);

		// Fetch CSRF token on mount
		await apiClient.fetchCsrfToken();

		// Load models and prompts
		try {
			const [modelData, promptData] = await Promise.all([
				apiClient.loadModels(),
				apiClient.loadPrompts(),
			]);
			models.set(modelData.models);
			prompts.set(promptData);

			if (modelData.models.length > 0) {
				selectedModel.set(modelData.models[0].id);
			}
			if (promptData.length > 0) {
				selectedPrompt.set(promptData[0].id);
			}
		} catch (error) {
			console.error("Failed to load models/prompts:", error);
		}
	});

	// Cleanup on destroy
	onDestroy(() => {
		document.removeEventListener("keydown", handleKeydown);
		if (audioContext) {
			audioContext.close();
		}
	});

	// Load annotation files when video changes
	$effect(() => {
		if ($currentVideo) {
			loadAnnotationFiles($currentVideo.filename);
		}
	});

	async function loadAnnotationFiles(filename: string) {
		annotationsLoading = true;
		try {
			const files = await apiClient.getAnnotations(filename);
			annotationFiles = files;

			if (files.length > 0) {
				// Select all files by default
				selectedAnnotationFiles = files.map((f) => f.filename);
				await loadAnnotationsFromSelectedFiles(
					filename,
					selectedAnnotationFiles,
				);
			} else {
				selectedAnnotationFiles = [];
				setAnnotations([]);
				annotationSourceFiles = [];
			}
		} catch (error) {
			console.error("Failed to load annotation files:", error);
			annotationFiles = [];
			setAnnotations([]);
			annotationSourceFiles = [];
		} finally {
			annotationsLoading = false;
		}
	}

	async function loadAnnotationsFromSelectedFiles(
		videoFilename: string,
		selectedFilenames: string[],
	) {
		try {
			const allAnnotations: Annotation[] = [];
			const sourceFiles: string[] = [];

			for (const annotationFilename of selectedFilenames) {
				const file = await apiClient.getAnnotationFile(
					videoFilename,
					annotationFilename,
				);

				// Store the full file object in annotationFiles list
				const fileIndex = annotationFiles.findIndex(
					(f) => f.filename === annotationFilename,
				);
				if (fileIndex !== -1) {
					annotationFiles[fileIndex] = {
						...annotationFiles[fileIndex],
						...file,
					};
				}

				// Add annotations with source tracking
				const fileAnnotations = file.annotations || [];
				allAnnotations.push(...fileAnnotations);
				sourceFiles.push(
					...fileAnnotations.map(() => annotationFilename),
				);
			}

			setAnnotations(allAnnotations);
			annotationSourceFiles = sourceFiles;

			// Reset active markers/boxes when loading new files to prevent rendering issues
			clearBoundingBox(true);

			// Auto-select first annotation if none selected or if previous selection is now invalid
			if (allAnnotations.length > 0) {
				if (
					activeAnnotationIndex === -1 ||
					activeAnnotationIndex >= allAnnotations.length
				) {
					activeAnnotationIndex = 0;
				}
			} else {
				activeAnnotationIndex = -1;
			}
		} catch (error) {
			console.error("Failed to load annotations from files:", error);
			setAnnotations([]);
			annotationSourceFiles = [];
		}
	}

	async function handleFileSelectionChange(filenames: string[]) {
		if (!$currentVideo) return;
		selectedAnnotationFiles = filenames;
		annotationsLoading = true;
		await loadAnnotationsFromSelectedFiles(
			$currentVideo.filename,
			filenames,
		);
		annotationsLoading = false;
	}

	async function refreshAnnotationFiles() {
		if (!$currentVideo) return;
		await loadAnnotationFiles($currentVideo.filename);
	}

	// Helper function to get the source file for a given annotation index
	function getSourceFileForIndex(index: number): string | null {
		if (index >= 0 && index < annotationSourceFiles.length) {
			return annotationSourceFiles[index];
		}
		return null;
	}

	// Get local index within a specific annotation file
	function getLocalIndexInFile(globalIndex: number): number {
		const sourceFile = annotationSourceFiles[globalIndex];
		if (!sourceFile) return -1;

		let localIndex = 0;
		for (let i = 0; i < globalIndex; i++) {
			if (annotationSourceFiles[i] === sourceFile) {
				localIndex++;
			}
		}
		return localIndex;
	}

	function goBack() {
		playerSectionActive.set(false);
		currentVideo.set(null);
		setAnnotations([]);
		annotationFiles = [];
		selectedAnnotationFiles = [];
		annotationSourceFiles = [];
		clearBoundingBox();
	}

	function seekTo(timestamp: string, autoPlay: boolean = true) {
		if (videoPlayer) {
			const time = parseTimestamp(timestamp);
			videoPlayer.currentTime = time;
			videoCurrentTime = time; // Explicitly update state for immediate UI feedback

			// Do NOT reset the annotation selection when seeking,
			// otherwise the active annotation card disappears
			clearBoundingBox(false);
			if (autoPlay) {
				videoPlayer.play();
			}
		}
	}

	import { tick } from "svelte";

	// Show bounding box on video
	// State to track pending seeks across video source changes
	// Format: { timestamp: number, autoPlay: boolean }
	let pendingSeek = $state<{ timestamp: number; autoPlay: boolean } | null>(
		null,
	);

	// Handle canplay/loadeddata event to consume pending seek
	function handleVideoReady() {
		// console.log("[VideoPlayer] Video ready event fired", { pendingSeek, readyState: videoPlayer?.readyState });
		if (pendingSeek && videoPlayer) {
			try {
				// Check if we are ready enough
				if (videoPlayer.readyState >= 1) {
					// HAVE_METADATA or higher
					console.log(
						`[VideoPlayer] Executing pending seek to ${pendingSeek.timestamp}`,
					);
					videoPlayer.currentTime = pendingSeek.timestamp;
					videoCurrentTime = pendingSeek.timestamp; // Explicitly update state for immediate UI feedback

					if (!pendingSeek.autoPlay) {
						videoPlayer.pause();
					} else {
						videoPlayer.play();
					}
					// Clear pending seek
					pendingSeek = null;
					// Do not clear the annotation selection when the video is ready
					clearBoundingBox(false);
				}
			} catch (e) {
				console.warn("[VideoPlayer] Pending seek failed", e);
			}
		}
	}

	// Show bounding box on video
	async function handleShowBox(
		box: LocationBox,
		boxIndex: number,
		annotationIndex?: number,
		evidenceIndex?: number,
	) {
		const targetTime = parseTimestamp(box.timestamp || "00:00");

		console.log("[VideoPlayer] handleShowBox called", {
			boxIndex,
			annotationIndex,
			timestamp: box.timestamp,
			targetTime,
		});

		// Set the active box
		activeBox = box;
		activeBoxIndex = boxIndex;

		// Update active annotation to ensure context (and video sources) are correct
		if (typeof annotationIndex === "number" && annotationIndex >= 0) {
			activeAnnotationIndex = annotationIndex;
		}

		// Switch context if the box belongs to a specific video
		const resolvedBoxPath = resolveVideoSource(box.video_path || "");
		if (resolvedBoxPath && resolvedBoxPath !== activeVideoSource) {
			console.log(
				`[VideoPlayer] Switching video source to ${resolvedBoxPath} for box click`,
			);

			// Set pending seek matching the target time
			pendingSeek = { timestamp: targetTime, autoPlay: false };

			setActiveVideoSource(resolvedBoxPath, false); // Don't auto-seek to span start activeVideoSource update will trigger re-render

			// We rely on the markup binding to update src, then 'canplay'/'loadeddata' to trigger handleVideoReady which is bound in the markup
			await tick();
			// Force load to ensure event fires if browser lazy loads or if same src
			videoPlayer?.load();
		} else {
			// No stream switch, normal seek
			// This prevents race conditions where seeking while playing might trigger 'play' events
			if (videoPlayer) {
				console.log(
					"[VideoPlayer] Pausing video and seeking to",
					box.timestamp,
				);
				videoPlayer.pause(); // Pause to show the box
				const time = parseTimestamp(box.timestamp || "00:00");
				videoPlayer.currentTime = time;
				videoCurrentTime = time; // Explicitly update state for immediate UI feedback
			}
		}

		// Set active box to display on canvas
		activeBox = box;
		activeBoxIndex = boxIndex;
		activeAnnotationIndex = annotationIndex ?? -1;
		activeBoxEvidenceIndex = evidenceIndex ?? -1;

		// Save original coordinates for cancel functionality
		originalBoxCoords = box.box_2d ? [...box.box_2d] : null;
		editingBoxTimestamp = box.timestamp || "";
		editingBoxDescription = box.description || "";

		// Show box controls
		showBoxControls = true;
		console.log("[VideoPlayer] Box controls enabled, activeBox set");

		// Set active time marker for the box timestamp on progress bar
		if (typeof annotationIndex === "number" && annotationIndex >= 0) {
			activeTimeMarker = {
				type: "timestamp",
				startTime: targetTime,
				annotationIndex: annotationIndex,
				field: "box_timestamp",
				boxIndex: boxIndex,
			};
		}

		// Auto-enable edit mode so user can immediately drag/resize the box
		boxEditMode = true;
		boxDrawMode = false;
		// Give the canvas time to render, then enable edit mode
		setTimeout(() => {
			if (boundingBoxCanvas) {
				console.log("[VideoPlayer] Enabling edit mode on canvas");
				boundingBoxCanvas.enableEditMode();
				// Ensure the box is drawn
				boundingBoxCanvas.redraw();
			}
		}, 50);
	}

	function clearBoundingBox(resetAnnotation: boolean = true) {
		console.log("[VideoPlayer] clearBoundingBox called");
		activeBox = null;
		activeBoxIndex = -1;
		if (resetAnnotation) {
			activeAnnotationIndex = -1;
		}
		originalBoxCoords = null;
		editingBoxTimestamp = "";
		editingBoxDescription = "";
		boxEditMode = false;
		boxDrawMode = false;
		showBoxControls = false; // Hide controls
		activeTimeMarker = null; // Clear time marker

		if (boundingBoxCanvas) {
			boundingBoxCanvas.clear();
			boundingBoxCanvas.disableEditMode();
			boundingBoxCanvas.disableDrawMode();
		}
	}

	// Cancel box editing and restore original coordinates
	function cancelBoxEditing() {
		console.log("[VideoPlayer] cancelBoxEditing called");
		if (activeBox && originalBoxCoords) {
			activeBox.box_2d = [...originalBoxCoords];
			boundingBoxCanvas?.redraw();
		}
		clearBoundingBox(false);
		showAlert("info", "Changes cancelled");
	}

	// Delete bounding box
	async function deleteBox() {
		const sourceFile = getSourceFileForIndex(activeAnnotationIndex);
		if (
			!$currentVideo ||
			!sourceFile ||
			activeAnnotationIndex < 0 ||
			activeBoxIndex < 0
		)
			return;

		if (!confirm("Delete this bounding box?")) return;

		const annotation = $annotations[activeAnnotationIndex];
		if (!annotation.location?.boxes) return;

		// Remove the box from the array
		const updatedBoxes = annotation.location.boxes.filter(
			(_: LocationBox, i: number) => i !== activeBoxIndex,
		);

		const updatedAnnotation = {
			...annotation,
			location: {
				...annotation.location,
				boxes: updatedBoxes,
			},
		};

		const localIndex = getLocalIndexInFile(activeAnnotationIndex);
		try {
			const result = await apiClient.updateAnnotation(
				$currentVideo.filename,
				sourceFile,
				localIndex,
				updatedAnnotation,
			);

			if (result.success) {
				updateAnnotationInStore(
					activeAnnotationIndex,
					updatedAnnotation,
				);
				clearBoundingBox(false);
				showAlert("success", "Bounding box deleted");
			} else {
				showAlert("error", result.error || "Failed to delete box");
			}
		} catch (error) {
			showAlert("error", `Error: ${error}`);
		}
	}

	// Save box with timestamp and description
	async function saveBoxWithDetails() {
		const sourceFile = getSourceFileForIndex(activeAnnotationIndex);
		if (
			!$currentVideo ||
			!sourceFile ||
			activeAnnotationIndex < 0 ||
			!activeBox
		)
			return;

		const annotation = $annotations[activeAnnotationIndex];

		// Update the box with new timestamp and description
		const updatedBox = {
			...activeBox,
			timestamp: editingBoxTimestamp || activeBox.timestamp,
			description: editingBoxDescription || activeBox.description,
			video_path: activeBox.video_path || activeVideoSource,
		};

		let updatedAnnotation = { ...annotation };

		if (activeBoxEvidenceIndex >= 0) {
			// It's an evidence box
			if (annotation.answer_evidence?.[activeBoxEvidenceIndex]) {
				// Legacy evidence
				const updatedBoxes = (
					annotation.answer_evidence[activeBoxEvidenceIndex]
						.bounding_boxes || []
				).map((b, i) => (i === activeBoxIndex ? updatedBox : b));
				updatedAnnotation.answer_evidence =
					annotation.answer_evidence.map((e, i) =>
						i === activeBoxEvidenceIndex
							? { ...e, bounding_boxes: updatedBoxes }
							: e,
					);
			} else if (
				(annotation.answer as any)?.evidence_list?.[
					activeBoxEvidenceIndex
				]
			) {
				// pipeline_v2 evidence
				const evidenceList = (annotation.answer as any).evidence_list;
				const ev = evidenceList[activeBoxEvidenceIndex];
				const updatedBoxes = (ev.bounding_boxes || []).map(
					(b: any, i: number) => {
						if (i === activeBoxIndex) {
							return {
								...b,
								ymin: updatedBox.box_2d[0],
								xmin: updatedBox.box_2d[1],
								ymax: updatedBox.box_2d[2],
								xmax: updatedBox.box_2d[3],
								label:
									(updatedBox as any).label ||
									updatedBox.description,
								time_offset: updatedBox.timestamp,
							};
						}
						return b;
					},
				);
				updatedAnnotation.answer = {
					...(annotation.answer as any),
					evidence_list: evidenceList.map((e: any, i: number) =>
						i === activeBoxEvidenceIndex
							? { ...e, bounding_boxes: updatedBoxes }
							: e,
					),
				};
			}
		} else {
			// It's a question box
			if (annotation.location?.boxes) {
				// Legacy question boxes
				updatedAnnotation.location = {
					...annotation.location,
					boxes: annotation.location.boxes.map((b, i) =>
						i === activeBoxIndex ? updatedBox : b,
					),
				};
			} else if ((annotation.question as any)?.bounding_boxes) {
				// pipeline_v2 question boxes
				const updatedBoxes = (
					annotation.question as any
				).bounding_boxes.map((b: any, i: number) => {
					if (i === activeBoxIndex) {
						return {
							...b,
							ymin: updatedBox.box_2d[0],
							xmin: updatedBox.box_2d[1],
							ymax: updatedBox.box_2d[2],
							xmax: updatedBox.box_2d[3],
							label:
								(updatedBox as any).label ||
								updatedBox.description,
							time_offset: updatedBox.timestamp,
						};
					}
					return b;
				});
				updatedAnnotation.question = {
					...(annotation.question as any),
					bounding_boxes: updatedBoxes,
				};
			}
		}

		const localIndex = getLocalIndexInFile(activeAnnotationIndex);
		try {
			const result = await apiClient.updateAnnotation(
				$currentVideo.filename,
				sourceFile,
				localIndex,
				updatedAnnotation,
			);

			if (result.success) {
				updateAnnotationInStore(
					activeAnnotationIndex,
					updatedAnnotation,
				);
				clearBoundingBox(false);
				showAlert("success", "Bounding box saved");
			} else {
				showAlert("error", result.error || "Failed to save box");
			}
		} catch (error) {
			showAlert("error", `Error: ${error}`);
		}
	}

	// Handle video play event - clear bounding box when video starts playing
	function handleVideoPlay() {
		console.log(
			"[VideoPlayer] handleVideoPlay triggered - clearing bounding box",
		);
		clearBoundingBox();
	}

	// Handle box update from canvas drag/resize
	async function handleBoxUpdate(box: LocationBox, boxIndex: number) {
		const sourceFile = getSourceFileForIndex(activeAnnotationIndex);
		if (!$currentVideo || !sourceFile || activeAnnotationIndex < 0) return;

		const annotation = $annotations[activeAnnotationIndex];
		let updatedAnnotation = { ...annotation };

		if (activeBoxEvidenceIndex >= 0) {
			// It's an evidence box
			if (annotation.answer_evidence?.[activeBoxEvidenceIndex]) {
				// Legacy evidence
				const updatedBoxes = (
					annotation.answer_evidence[activeBoxEvidenceIndex]
						.bounding_boxes || []
				).map((b, i) => (i === boxIndex ? box : b));
				updatedAnnotation.answer_evidence =
					annotation.answer_evidence.map((e, i) =>
						i === activeBoxEvidenceIndex
							? { ...e, bounding_boxes: updatedBoxes }
							: e,
					);
			} else if (
				(annotation.answer as any)?.evidence_list?.[
					activeBoxEvidenceIndex
				]
			) {
				// pipeline_v2 evidence
				const evidenceList = (annotation.answer as any).evidence_list;
				const ev = evidenceList[activeBoxEvidenceIndex];
				const updatedBoxes = (ev.bounding_boxes || []).map(
					(b: any, i: number) => {
						if (i === boxIndex) {
							return {
								...b,
								ymin: box.box_2d[0],
								xmin: box.box_2d[1],
								ymax: box.box_2d[2],
								xmax: box.box_2d[3],
							};
						}
						return b;
					},
				);
				updatedAnnotation.answer = {
					...(annotation.answer as any),
					evidence_list: evidenceList.map((e: any, i: number) =>
						i === activeBoxEvidenceIndex
							? { ...e, bounding_boxes: updatedBoxes }
							: e,
					),
				};
			}
		} else {
			// It's a question box
			if (annotation.location?.boxes) {
				// Legacy question boxes
				updatedAnnotation.location = {
					...annotation.location,
					boxes: annotation.location.boxes.map((b, i) =>
						i === boxIndex ? box : b,
					),
				};
			} else if ((annotation.question as any)?.bounding_boxes) {
				// pipeline_v2 question boxes
				const updatedBoxes = (
					annotation.question as any
				).bounding_boxes.map((b: any, i: number) => {
					if (i === boxIndex) {
						return {
							...b,
							ymin: box.box_2d[0],
							xmin: box.box_2d[1],
							ymax: box.box_2d[2],
							xmax: box.box_2d[3],
						};
					}
					return b;
				});
				updatedAnnotation.question = {
					...(annotation.question as any),
					bounding_boxes: updatedBoxes,
				};
			}
		}

		const localIndex = getLocalIndexInFile(activeAnnotationIndex);
		try {
			const result = await apiClient.updateAnnotation(
				$currentVideo.filename,
				sourceFile,
				localIndex,
				updatedAnnotation,
			);

			if (result.success) {
				updateAnnotationInStore(
					activeAnnotationIndex,
					updatedAnnotation,
				);
				showAlert("success", `Bounding box updated`);
			} else {
				showAlert(
					"error",
					result.error || "Failed to update bounding box",
				);
			}
		} catch (error) {
			showAlert("error", `Error: ${error}`);
		}
	}

	async function generateAnnotations() {
		if (!$currentVideo) return;
		if (!$selectedModel || !$selectedPrompt) {
			showAlert("error", "Please select a model and prompt");
			return;
		}

		generateStatus.set({
			loading: true,
			message: "Generating annotations...",
		});
		try {
			const result = await apiClient.generateAnnotations({
				video_filename: $currentVideo.filename,
				model_id: $selectedModel,
				prompt_id: $selectedPrompt,
				prompt_params: $promptParameters,
			});

			if (result.success && result.data) {
				setAnnotations(result.data.annotations);
				// Refresh file list to show new file
				await refreshAnnotationFiles();
				showAlert("success", "Annotations generated successfully");
			} else {
				showAlert(
					"error",
					result.error || "Failed to generate annotations",
				);
			}
		} catch (error) {
			showAlert("error", `Error generating annotations: ${error}`);
		} finally {
			generateStatus.set({ loading: false, message: "" });
		}
	}

	// Edit annotation
	function handleEdit(index: number) {
		if (index >= 0 && index < $annotations.length) {
			editingAnnotation = $annotations[index];
			editingIndex = index;
			editModalOpen = true;
		}
	}

	async function handleSaveEdit(annotation: Annotation) {
		const sourceFile = getSourceFileForIndex(editingIndex);
		if (!$currentVideo || !sourceFile || editingIndex < 0) return;

		const localIndex = getLocalIndexInFile(editingIndex);
		try {
			const result = await apiClient.updateAnnotation(
				$currentVideo.filename,
				sourceFile,
				localIndex,
				annotation,
			);

			if (result.success) {
				updateAnnotationInStore(editingIndex, annotation);
				showAlert("success", `Annotation #${editingIndex + 1} updated`);
			} else {
				showAlert(
					"error",
					result.error || "Failed to update annotation",
				);
			}
		} catch (error) {
			showAlert("error", `Error: ${error}`);
		}

		editModalOpen = false;
		editingAnnotation = null;
		editingIndex = -1;
	}

	function handleCancelEdit() {
		editModalOpen = false;
		editingAnnotation = null;
		editingIndex = -1;
	}

	// Add annotation
	function openAddModal() {
		if (selectedAnnotationFiles.length === 0) {
			showAlert(
				"error",
				"Please select or create an annotation file first",
			);
			return;
		}
		addModalOpen = true;
	}

	async function handleAddAnnotation(annotation: Annotation) {
		// Add to the first selected file
		const targetFile = selectedAnnotationFiles[0];
		if (!$currentVideo || !targetFile) return;

		try {
			const result = await apiClient.addAnnotation(
				$currentVideo.filename,
				targetFile,
				annotation,
			);

			if (result.success) {
				// Refresh to get updated annotations including the new one
				await loadAnnotationsFromSelectedFiles(
					$currentVideo.filename,
					selectedAnnotationFiles,
				);
				showAlert("success", `Annotation added to ${targetFile}`);
			} else {
				showAlert("error", result.error || "Failed to add annotation");
			}
		} catch (error) {
			showAlert("error", `Error: ${error}`);
		}

		addModalOpen = false;
	}

	function handleCancelAdd() {
		addModalOpen = false;
	}

	// Review annotation (quick status update)
	async function handleReview(index: number) {
		const sourceFile = getSourceFileForIndex(index);
		if (!$currentVideo || !sourceFile) return;

		const annotation = $annotations[index];
		const currentStatus = annotation.human_review?.status || "pending";

		// Cycle through statuses: pending -> accepted -> rejected -> pending
		let newStatus: "accepted" | "rejected" | "pending";
		if (currentStatus === "pending") newStatus = "accepted";
		else if (currentStatus === "accepted") newStatus = "rejected";
		else newStatus = "pending";

		const updatedAnnotation = {
			...annotation,
			human_review: {
				...annotation.human_review,
				status: newStatus,
				reviewed: newStatus !== "pending",
			},
		};

		const localIndex = getLocalIndexInFile(index);
		try {
			const result = await apiClient.updateAnnotation(
				$currentVideo.filename,
				sourceFile,
				localIndex,
				updatedAnnotation,
			);

			if (result.success) {
				updateAnnotationInStore(index, updatedAnnotation);
				showAlert(
					"success",
					`Annotation #${index + 1} marked as ${newStatus}`,
				);
			} else {
				showAlert(
					"error",
					result.error || "Failed to update review status",
				);
			}
		} catch (error) {
			showAlert("error", `Error: ${error}`);
		}
	}

	// Delete annotation
	async function handleDelete(index: number) {
		if (!confirm("Are you sure you want to delete this annotation?"))
			return;
		const sourceFile = getSourceFileForIndex(index);
		if (!$currentVideo || !sourceFile) return;

		const localIndex = getLocalIndexInFile(index);
		try {
			const result = await apiClient.deleteAnnotation(
				$currentVideo.filename,
				sourceFile,
				localIndex,
			);

			if (result.success) {
				// Refresh annotations from all selected files
				await loadAnnotationsFromSelectedFiles(
					$currentVideo.filename,
					selectedAnnotationFiles,
				);
				showAlert("success", "Annotation deleted");
			} else {
				showAlert(
					"error",
					result.error || "Failed to delete annotation",
				);
			}
		} catch (error) {
			showAlert("error", `Error: ${error}`);
		}
	}

	// Summary functionality
	async function showSummary() {
		if (!$currentVideo) return;
		try {
			const data = await apiClient.getSummary($currentVideo.filename);
			summaryData = data;
			summaryModalOpen = true;
		} catch (error) {
			showAlert("error", `Failed to load summary: ${error}`);
		}
	}

	// Prompt parameter handling
	async function loadPromptParameters() {
		const promptId = $selectedPrompt;
		if (!promptId) return;

		try {
			const details = await apiClient.getPromptDetails(promptId);
			currentPromptDetails = details;

			// Initialize parameter values with defaults
			const newParams: Record<string, unknown> = {};
			for (const [name, param] of Object.entries(
				details.input_parameters || {},
			)) {
				const typedParam = param as PromptInputParameter;
				newParams[name] = typedParam.default;
			}
			promptParamValues = newParams;
		} catch (error) {
			console.error("Failed to load prompt parameters:", error);
		}
	}

	// Watch for prompt changes to load parameters
	$effect(() => {
		if ($selectedPrompt) {
			loadPromptParameters();
		}
	});

	function updatePromptParam(name: string, value: unknown) {
		promptParamValues = { ...promptParamValues, [name]: value };
	}

	async function buildAndPreviewPrompt() {
		const promptId = $selectedPrompt;
		if (!promptId) {
			showAlert("error", "Please select a prompt first");
			return;
		}

		try {
			const result = await apiClient.buildPrompt(
				promptId,
				promptParamValues,
			);
			if (result.success && result.rendered_prompt) {
				promptPreviewContent = result.rendered_prompt;
				promptPreviewModalOpen = true;
			} else {
				showAlert("error", result.error || "Failed to build prompt");
			}
		} catch (error) {
			showAlert("error", `Error building prompt: ${error}`);
		}
	}

	// Bounding box edit mode
	function toggleBoxEditMode() {
		boxEditMode = !boxEditMode;
		boxDrawMode = false;
		if (boxEditMode) {
			boundingBoxCanvas?.enableEditMode();
		} else {
			boundingBoxCanvas?.disableEditMode();
		}
	}

	function toggleBoxDrawMode() {
		boxDrawMode = !boxDrawMode;
		boxEditMode = false;
		if (boxDrawMode) {
			boundingBoxCanvas?.enableDrawMode();
		} else {
			boundingBoxCanvas?.disableDrawMode();
		}
	}

	// Select annotation for adding bounding boxes
	function handleSelectAnnotation(index: number) {
		if (activeAnnotationIndex === index && boxDrawMode) {
			// Deselect
			activeAnnotationIndex = -1;
			boxDrawMode = false;
			boundingBoxCanvas?.disableDrawMode();
		} else {
			// Select this annotation and enable draw mode
			activeAnnotationIndex = index;
			boxDrawMode = true;
			boxEditMode = false;
			boundingBoxCanvas?.enableDrawMode();
			showAlert(
				"info",
				`Select annotation #${index + 1}. Draw on the video to add a bounding box.`,
			);
		}
	}

	// Quick add bounding box at current time
	async function handleQuickAddBox(index: number) {
		const sourceFile = getSourceFileForIndex(index);
		if (!$currentVideo || !sourceFile || index < 0) return;

		const annotation = $annotations[index];
		const timestamp = formatTimestamp(videoCurrentTime);
		const defaultCoords = [10, 10, 90, 90]; // [y1, x1, y2, x2]

		let updatedAnnotation = { ...annotation };

		const mainVideoPath = $currentVideo.path
			? resolveVideoSource($currentVideo.path)
			: `/uploads/${$currentVideo.filename}`;

		// Detect schema
		if (annotation.location) {
			// Legacy
			const newBox: LocationBox = {
				timestamp,
				video_path: activeVideoSource || mainVideoPath,
				box_2d: [...defaultCoords],
				stream: "question",
			};
			updatedAnnotation.location = {
				...annotation.location,
				boxes: [...(annotation.location.boxes || []), newBox],
			};
		} else if ((annotation.question as any)?.bounding_boxes) {
			// pipeline_v2
			const q = annotation.question as any;
			const newBox = {
				ymin: defaultCoords[0],
				xmin: defaultCoords[1],
				ymax: defaultCoords[2],
				xmax: defaultCoords[3],
				label: "",
				time_offset: timestamp,
			};
			updatedAnnotation.question = {
				...q,
				bounding_boxes: [...(q.bounding_boxes || []), newBox],
			};
		} else {
			// Fallback: create legacy location if none exists
			updatedAnnotation.location = {
				boxes: [
					{
						timestamp,
						video_path: activeVideoSource || mainVideoPath,
						box_2d: [...defaultCoords],
						stream: "question",
					},
				],
			};
		}

		const localIndex = getLocalIndexInFile(index);
		try {
			const result = await apiClient.updateAnnotation(
				$currentVideo.filename,
				sourceFile,
				localIndex,
				updatedAnnotation,
			);

			if (result.success) {
				updateAnnotationInStore(index, updatedAnnotation);
				// Automatically select the new box and show it
				activeAnnotationIndex = index;
				if (updatedAnnotation.location?.boxes) {
					const newBoxIndex =
						updatedAnnotation.location.boxes.length - 1;
					handleShowBox(
						updatedAnnotation.location.boxes[newBoxIndex],
						newBoxIndex,
					);
				} else if (
					(updatedAnnotation.question as any)?.bounding_boxes
				) {
					const q = updatedAnnotation.question as any;
					const newBoxIndex = q.bounding_boxes.length - 1;
					// Map pipeline_v2 box to LocationBox for display
					const v2Box = q.bounding_boxes[newBoxIndex];
					const displayBox: LocationBox = {
						timestamp: v2Box.time_offset,
						box_2d: [
							v2Box.ymin,
							v2Box.xmin,
							v2Box.ymax,
							v2Box.xmax,
						],
						description: v2Box.label,
					};
					handleShowBox(displayBox, newBoxIndex);
				}
				showAlert("success", "Bounding box added at " + timestamp);
			} else {
				showAlert("error", result.error || "Failed to add box");
			}
		} catch (error) {
			showAlert("error", `Error: ${error}`);
		}
	}

	// Navigate to previous annotation (chronologically by time)
	function navigateToPreviousAnnotation() {
		if ($annotations.length === 0) return;

		const currentIndex = activeAnnotationIndex;
		let targetIndex = currentIndex - 1;

		// Wrap around to last annotation if at beginning
		if (targetIndex < 0) {
			targetIndex = $annotations.length - 1;
		}

		navigateToAnnotation(targetIndex);
	}

	// Navigate to next annotation (chronologically by time)
	function navigateToNextAnnotation() {
		if ($annotations.length === 0) return;

		const currentIndex = activeAnnotationIndex;
		let targetIndex = currentIndex + 1;

		// Wrap around to first annotation if at end
		if (targetIndex >= $annotations.length) {
			targetIndex = 0;
		}

		navigateToAnnotation(targetIndex);
	}

	// Navigate to a specific annotation
	function navigateToAnnotation(index: number) {
		if (index < 0 || index >= $annotations.length) return;

		activeAnnotationIndex = index;
		clearBoundingBox(false);
		const ann = $annotations[index];

		// Identify the target timestamp to seek to
		let targetTimestamp = "";
		let marker: ActiveTimeMarker | null = null;

		if (ann.question_time_span?.start) {
			targetTimestamp = ann.question_time_span.start;
			const tsSeconds = parseTimestamp(targetTimestamp);

			marker = {
				type: "timespan",
				startTime: tsSeconds,
				endTime: ann.question_time_span.end
					? parseTimestamp(ann.question_time_span.end)
					: undefined,
				annotationIndex: index,
				field: "question_time_span",
			};
		} else if (ann.answer_evidence?.[0]?.time_spans?.[0]?.start) {
			// Fallback to evidence start if no question time
			const ev = ann.answer_evidence[0];
			// We know time_spans[0] exists because of the check above
			const span = ev.time_spans![0];
			targetTimestamp = span.start || "";
			const tsSeconds = parseTimestamp(targetTimestamp);

			marker = {
				type: "timespan",
				startTime: tsSeconds,
				endTime: span.end ? parseTimestamp(span.end) : undefined,
				annotationIndex: index,
				field: "evidence_time_span",
				evidenceIndex: 0,
				spanIndex: 0,
			};
		} else if (ann.time_span?.start) {
			targetTimestamp = ann.time_span.start;
			const tsSeconds = parseTimestamp(targetTimestamp);

			marker = {
				type: "timespan",
				startTime: tsSeconds,
				endTime: ann.time_span.end
					? parseTimestamp(ann.time_span.end)
					: undefined,
				annotationIndex: index,
				field: "time_span",
			};
		}

		// Update the active time marker
		activeTimeMarker = marker;

		// Seek to the timestamp
		if (targetTimestamp) {
			const tsSeconds = parseTimestamp(targetTimestamp);
			if (videoPlayer) {
				videoPlayer.currentTime = tsSeconds;
				videoCurrentTime = tsSeconds; // Explicitly update state for immediate UI feedback
			}
		}

		// Scroll annotation into view
		setTimeout(() => {
			const annElement = document.querySelector(
				`[data-annotation-index="${index}"]`,
			);
			if (annElement) {
				annElement.scrollIntoView({
					behavior: "smooth",
					block: "nearest",
				});
			}
		}, 100);
	}

	// Handle new box creation from canvas
	async function handleBoxCreate(box: LocationBox) {
		// ...

		const sourceFile = getSourceFileForIndex(activeAnnotationIndex);
		if (!$currentVideo || !sourceFile || activeAnnotationIndex < 0) {
			showAlert(
				"error",
				"Please select an annotation first to add a bounding box",
			);
			boxDrawMode = false;
			boundingBoxCanvas?.disableDrawMode();
			return;
		}

		const annotation = $annotations[activeAnnotationIndex];

		// Add video path to the new box
		const newBox = {
			...box,
			video_path: activeVideoSource,
		};

		const updatedAnnotation = {
			...annotation,
			location: {
				...annotation.location,
				boxes: [...(annotation.location?.boxes || []), newBox],
			},
		};

		const localIndex = getLocalIndexInFile(activeAnnotationIndex);
		try {
			const result = await apiClient.updateAnnotation(
				$currentVideo.filename,
				sourceFile,
				localIndex,
				updatedAnnotation,
			);

			if (result.success) {
				updateAnnotationInStore(
					activeAnnotationIndex,
					updatedAnnotation,
				);
				showAlert("success", "Bounding box added");
			} else {
				showAlert(
					"error",
					result.error || "Failed to add bounding box",
				);
			}
		} catch (error) {
			showAlert("error", `Error: ${error}`);
		}

		boxDrawMode = false;
		boundingBoxCanvas?.disableDrawMode();
	}

	// Get total annotation count across all files for the video
	const totalAnnotationCount = $derived(
		annotationFiles.reduce(
			(sum, file) => sum + (file.annotation_count || 0),
			0,
		),
	);

	// Context menu handlers
	function handleTimelineContextMenu(
		e: MouseEvent,
		time: number,
		annotation?: Annotation,
		evidenceIndex?: number,
	) {
		e.preventDefault();
		const annIndex = annotation ? $annotations.indexOf(annotation) : -1;
		contextMenu = {
			show: true,
			x: e.clientX,
			y: e.clientY,
			time,
			annotation,
			annotationIndex: annIndex,
			evidenceIndex,
		};
	}

	function closeContextMenu() {
		contextMenu = { ...contextMenu, show: false };
	}

	async function addBoundingBoxAtTime() {
		if (
			!$currentVideo ||
			contextMenu.annotationIndex === undefined ||
			contextMenu.annotationIndex < 0
		) {
			showAlert("error", "Please select an annotation first");
			closeContextMenu();
			return;
		}

		const annIdx = contextMenu.annotationIndex;
		const annotation = $annotations[annIdx];
		const sourceFile = getSourceFileForIndex(annIdx);
		if (!sourceFile) {
			closeContextMenu();
			return;
		}

		// Create a default bounding box at the cursor time
		const timestamp = formatTimestamp(contextMenu.time);
		const newBox: LocationBox = {
			box_2d: [100, 100, 200, 200], // Default coordinates
			timestamp,
			description: "",
			video_path: activeVideoSource,
		};

		const updatedAnnotation = {
			...annotation,
			location: {
				...annotation.location,
				boxes: [...(annotation.location?.boxes || []), newBox],
			},
		};

		const localIndex = getLocalIndexInFile(annIdx);
		try {
			const result = await apiClient.updateAnnotation(
				$currentVideo.filename,
				sourceFile,
				localIndex,
				updatedAnnotation,
			);

			if (result.success) {
				updateAnnotationInStore(annIdx, updatedAnnotation);
				showAlert("success", "Bounding box added");
				// Keep annotation selected
				activeAnnotationIndex = annIdx;
			} else {
				showAlert(
					"error",
					result.error || "Failed to add bounding box",
				);
			}
		} catch (error) {
			showAlert("error", `Error: ${error}`);
		}

		closeContextMenu();
	}

	async function addAnswerEvidenceAtTime() {
		if (
			!$currentVideo ||
			contextMenu.annotationIndex === undefined ||
			contextMenu.annotationIndex < 0
		) {
			showAlert("error", "Please select an annotation first");
			closeContextMenu();
			return;
		}

		const annIdx = contextMenu.annotationIndex;
		const annotation = $annotations[annIdx];
		const sourceFile = getSourceFileForIndex(annIdx);
		if (!sourceFile) {
			closeContextMenu();
			return;
		}

		const timestamp = formatTimestamp(contextMenu.time);
		const newEvidence = {
			time_spans: [{ start: timestamp, end: timestamp }],
			video_path: activeVideoSource,
			reason: "",
			room: "",
			modalities: [],
			bounding_boxes: [],
		};

		const updatedAnnotation = {
			...annotation,
			answer_evidence: [
				...(annotation.answer_evidence || []),
				newEvidence,
			],
		};

		const localIndex = getLocalIndexInFile(annIdx);
		try {
			const result = await apiClient.updateAnnotation(
				$currentVideo.filename,
				sourceFile,
				localIndex,
				updatedAnnotation,
			);

			if (result.success) {
				updateAnnotationInStore(annIdx, updatedAnnotation);
				showAlert("success", "Answer evidence added");
				// Keep annotation selected
				activeAnnotationIndex = annIdx;
			} else {
				showAlert("error", result.error || "Failed to add evidence");
			}
		} catch (error) {
			showAlert("error", `Error: ${error}`);
		}

		closeContextMenu();
	}

	function createNewAnnotationAtTime() {
		closeContextMenu();
		// Open the add modal with the time pre-filled
		openAddModal();
		// TODO: Pre-fill the timestamp in the modal
	}

	// Timeline drag handlers
	function handleTimelineDragStart(
		type: "question" | "evidence",
		annotationIndex: number,
		evidenceIndex?: number,
		spanIndex?: number,
		edge?: "start" | "end",
	) {
		if (!edge) return;

		const annotation = $annotations[annotationIndex];
		let originalTime = 0;

		if (type === "question" && annotation.question_time_span) {
			originalTime =
				edge === "start"
					? parseTimestamp(
							annotation.question_time_span.start || "0:00",
						)
					: parseTimestamp(
							annotation.question_time_span.end || "0:00",
						);
		} else if (
			type === "evidence" &&
			evidenceIndex !== undefined &&
			annotation.answer_evidence
		) {
			const evidence = annotation.answer_evidence[evidenceIndex];
			const span = evidence.time_spans?.[spanIndex || 0];
			if (span) {
				originalTime =
					edge === "start"
						? parseTimestamp(span.start || "0:00")
						: parseTimestamp(span.end || "0:00");
			}
		}

		timelineDragState = {
			type,
			annotationIndex,
			evidenceIndex,
			spanIndex,
			edge,
			originalTime,
		};

		// Keep the annotation selected
		activeAnnotationIndex = annotationIndex;
	}

	function handleTimelineDrag(newTime: number) {
		if (!timelineDragState) return;
		// Seek to the new time for visual feedback
		if (videoPlayer) {
			videoPlayer.currentTime = newTime;
		}
	}

	async function handleTimelineDragEnd() {
		if (!timelineDragState || !$currentVideo) {
			timelineDragState = null;
			return;
		}

		const { type, annotationIndex, evidenceIndex, spanIndex, edge } =
			timelineDragState;
		const annotation = { ...$annotations[annotationIndex] };
		const sourceFile = getSourceFileForIndex(annotationIndex);

		if (!sourceFile) {
			timelineDragState = null;
			return;
		}

		const newTimeStr = formatTimestamp(videoPlayer?.currentTime || 0);

		try {
			if (type === "question" && annotation.question_time_span) {
				if (edge === "start") {
					annotation.question_time_span = {
						...annotation.question_time_span,
						start: newTimeStr,
					};
				} else {
					annotation.question_time_span = {
						...annotation.question_time_span,
						end: newTimeStr,
					};
				}
			} else if (
				type === "evidence" &&
				evidenceIndex !== undefined &&
				annotation.answer_evidence
			) {
				// Deep copy the answer_evidence array to ensure reactivity
				annotation.answer_evidence = [...annotation.answer_evidence];
				const evidence = {
					...annotation.answer_evidence[evidenceIndex],
				};

				if (evidence.time_spans && spanIndex !== undefined) {
					// Deep copy the time_spans array
					evidence.time_spans = [...evidence.time_spans];
					const span = { ...evidence.time_spans[spanIndex] };

					if (edge === "start") {
						span.start = newTimeStr;
					} else {
						span.end = newTimeStr;
					}

					evidence.time_spans[spanIndex] = span;
				}

				annotation.answer_evidence[evidenceIndex] = evidence;
			}

			const localIndex = getLocalIndexInFile(annotationIndex);
			const result = await apiClient.updateAnnotation(
				$currentVideo.filename,
				sourceFile,
				localIndex,
				annotation,
			);

			if (result.success) {
				updateAnnotationInStore(annotationIndex, annotation);
				showAlert("success", "Timespan updated");
				// Keep annotation selected
				activeAnnotationIndex = annotationIndex;
			} else {
				showAlert("error", result.error || "Failed to update timespan");
			}
		} catch (error) {
			showAlert("error", `Error: ${error}`);
		}

		timelineDragState = null;
	}

	function openDebugView(type: "raw" | "fullraw" | "thinking" | "file") {
		// For debug view, use the first selected file
		if (selectedAnnotationFiles.length === 0) return;

		const file = annotationFiles.find(
			(f) => f.filename === selectedAnnotationFiles[0],
		);
		if (!file) return;

		if (type === "raw") {
			debugModalTitle = "Raw Model Response";
			debugModalContent =
				file.raw_response || "No raw response available for this file.";
			debugModalType = "text";
		} else if (type === "fullraw") {
			debugModalTitle = "Full Raw Response (includes thinking)";
			if (file.full_raw_response) {
				debugModalContent = file.full_raw_response;
			} else if (file.raw_response) {
				debugModalContent =
					"(No full raw response available. Showing raw response instead.)\n\n" +
					file.raw_response;
			} else {
				debugModalContent =
					"No full raw response available for this file.";
			}
			debugModalType = "text";
		} else if (type === "thinking") {
			debugModalTitle = "Model Thoughts";
			debugModalContent =
				file.thinking || "No thinking logs available for this file.";
			debugModalType = "markdown";
		} else if (type === "file") {
			debugModalTitle = "Raw Annotation File";
			debugModalContent = JSON.stringify(file, null, 2);
			debugModalType = "json";
		}

		debugModalOpen = true;
	}
</script>

{#if $playerSectionActive && $currentVideo}
	<Card>
		<CardHeader class="flex-row items-center justify-between">
			<div>
				<CardTitle class="text-lg font-semibold"
					>Review & Edit Annotations</CardTitle
				>
				<p class="text-sm text-muted-foreground mt-1">
					{$currentVideo.filename} • {totalAnnotationCount} annotation{totalAnnotationCount !==
					1
						? "s"
						: ""} across {annotationFiles.length} file{annotationFiles.length !==
					1
						? "s"
						: ""}
				</p>
			</div>
			<Button variant="outline" onclick={goBack}>← Back to Videos</Button>
		</CardHeader>
		<CardContent>
			<!-- Annotation Files Panel -->
			<AnnotationFilePanel
				videoFilename={$currentVideo.filename}
				{annotationFiles}
				selectedFiles={selectedAnnotationFiles}
				onSelectionChange={handleFileSelectionChange}
				onRefresh={refreshAnnotationFiles}
				onDebugView={openDebugView}
			/>

			<!-- Video Player Section (vertical stack layout) -->
			<div class="space-y-4">
				<!-- Video Player with Bounding Box Canvas -->
				<div class="relative flex flex-col overflow-hidden">
					<!-- Stream Toggle -->
					<!-- Video Source Toggle -->
					<div class="flex justify-center mb-4">
						<div
							class="inline-flex rounded-lg border border-gray-200 p-1 bg-white shadow-sm z-10 items-center gap-2"
						>
							<span
								class="text-xs font-semibold uppercase text-gray-500 ml-2"
								>Video Source:</span
							>
							<select
								class="h-9 rounded-md border-gray-200 text-sm focus:border-primary focus:ring-primary min-w-[200px]"
								value={activeVideoSource}
								onchange={(e) =>
									setActiveVideoSource(e.currentTarget.value)}
							>
								{#each availableVideoSources as source}
									{@const displayName = (() => {
										if (
											source.includes(
												"/api/serve-video?path=",
											)
										) {
											const encodedPath =
												source.split("path=")[1];
											if (encodedPath) {
												const decodedPath =
													decodeURIComponent(
														encodedPath,
													);
												return (
													decodedPath
														.split("/")
														.pop() || source
												);
											}
										}
										return (
											source.split("/").pop() || source
										);
									})()}
									<option value={source}>
										{displayName}
									</option>
								{/each}
							</select>
						</div>
					</div>

					<div
						class="relative video-player-wrapper flex-shrink-1 min-h-0 overflow-hidden"
					>
						<!-- Seeking overlay -->
						{#if isVideoSeeking}
							<div
								class="absolute inset-0 flex items-center justify-center bg-black/30 z-20 rounded-lg"
							>
								<div class="spinner"></div>
							</div>
						{/if}

						<!-- Video and canvas wrapper (separate from controls to prevent canvas stretch) -->
						<div
							class="relative aspect-square mx-auto"
							style="max-height: 650px; max-width: 650px; width: 100%;"
						>
							<video
								bind:this={videoPlayer}
								src={activeVideoSource}
								preload="metadata"
								class="w-full h-full object-contain rounded-t-lg bg-black cursor-pointer"
								onplay={() => {
									isPlaying = true;
									handleVideoPlay();
								}}
								onpause={() => {
									isPlaying = false;
								}}
								onloadedmetadata={() => {
									if (videoPlayer) {
										videoDuration =
											videoPlayer.duration || 0;
									}
								}}
								onloadeddata={() => {
									handleVideoReady();
									if (videoPlayer) {
										videoDuration =
											videoPlayer.duration || 0;
									}
									// Initialize audio amplification on first load
									if (!audioContext) {
										initAudioAmplification();
									}
								}}
								oncanplay={handleVideoReady}
								ontimeupdate={() => {
									if (videoPlayer && !isVideoSeeking) {
										videoCurrentTime =
											videoPlayer.currentTime;
									}
								}}
								onseeking={() => {
									isVideoSeeking = true;
								}}
								onseeked={() => {
									isVideoSeeking = false;
								}}
								onclick={() => {
									if (videoPlayer) {
										if (videoPlayer.paused) {
											videoPlayer.play();
										} else {
											videoPlayer.pause();
										}
									}
								}}
							>
								<track kind="captions" />
							</video>
							<BoundingBoxCanvas
								bind:this={boundingBoxCanvas}
								videoElement={videoPlayer}
								{activeBox}
								{activeBoxIndex}
								onBoxUpdate={handleBoxUpdate}
								onBoxCreate={handleBoxCreate}
							/>
						</div>

						<!-- Custom video controls -->
						<div
							class="video-controls bg-gray-900/95 px-3 py-2 rounded-b-lg"
						>
							<!-- Progress bar with hover preview -->
							<VideoProgressBar
								videoElement={videoPlayer}
								videoFilename={$currentVideo?.filename || ""}
								duration={videoDuration}
								currentTime={videoCurrentTime}
								annotations={$annotations}
								onSeek={(time) => {
									if (videoPlayer) {
										videoCurrentTime = time;
										videoPlayer.currentTime = time;
										clearBoundingBox(false);
									}
								}}
								activeTimeMarker={activeTimeMarker
									? {
											type: activeTimeMarker.type,
											startTime:
												activeTimeMarker.startTime,
											endTime: activeTimeMarker.endTime,
										}
									: undefined}
								onTimeMarkerUpdate={(marker) => {
									handleTimeMarkerUpdate(marker);
								}}
								onTimeMarkerDragEnd={() => {
									saveTimeMarkerChanges();
								}}
								onAnnotationSelect={(annIndex) => {
									// Select the annotation
									activeAnnotationIndex = annIndex;
									clearBoundingBox(false);
									// Ensure panel is open
									annotationsPanelCollapsed = false;
									// Scroll annotation into view
									setTimeout(() => {
										const annElement =
											document.querySelector(
												`[data-annotation-index="${annIndex}"]`,
											);
										if (annElement) {
											annElement.scrollIntoView({
												behavior: "smooth",
												block: "nearest",
											});
										}
									}, 100);
								}}
								selectedAnnotationIndex={activeAnnotationIndex}
							/>

							<!-- Control buttons row -->
							<VideoControls
								{isPlaying}
								{volumeAmplification}
								onTogglePlay={() => {
									if (videoPlayer) {
										if (videoPlayer.paused)
											videoPlayer.play();
										else videoPlayer.pause();
									}
								}}
								onToggleMute={() => {
									if (videoPlayer)
										videoPlayer.muted = !videoPlayer.muted;
								}}
								onVolumeChange={setVolumeAmplification}
								onFullscreen={() => {
									if (videoPlayer) {
										if (document.fullscreenElement)
											document.exitFullscreen();
										else videoPlayer.requestFullscreen();
									}
								}}
							/>
						</div>
					</div>

					<BoundingBoxControls
						{showBoxControls}
						{activeBox}
						{activeBoxIndex}
						{activeAnnotationIndex}
						{boxEditMode}
						{boxDrawMode}
						{editingBoxTimestamp}
						{editingBoxDescription}
						onSave={saveBoxWithDetails}
						onCancel={cancelBoxEditing}
						onDelete={deleteBox}
						onToggleDraw={toggleBoxDrawMode}
						onTimestampChange={(v) => (editingBoxTimestamp = v)}
						onDescriptionChange={(v) => (editingBoxDescription = v)}
					/>
				</div>

				<!-- Annotation Timeline -->
				<div
					class="mt-4 px-4 py-2 bg-white rounded-lg border border-gray-200"
				>
					<AnnotationTimeline
						duration={videoDuration}
						currentTime={videoCurrentTime}
						annotations={$annotations}
						selectedAnnotationIndex={activeAnnotationIndex}
						windowSeconds={180}
						onSeek={(time) => {
							if (videoPlayer) {
								videoPlayer.currentTime = time;
							}
						}}
						onAnnotationSelect={(index) => {
							activeAnnotationIndex = index;
						}}
						onContextMenu={handleTimelineContextMenu}
						onTimespanDragStart={handleTimelineDragStart}
						onTimespanDrag={handleTimelineDrag}
						onTimespanDragEnd={handleTimelineDragEnd}
						onBoxClick={(
							box,
							boxIndex,
							annotationIndex,
							evidenceIndex,
						) => {
							handleShowBox(
								box,
								boxIndex,
								annotationIndex,
								evidenceIndex,
							);
						}}
						onBoxTimestampDragEnd={async (
							annotationIndex,
							boxIndex,
							newTime,
							evidenceIndex,
						) => {
							const sourceFile =
								getSourceFileForIndex(annotationIndex);
							if (!$currentVideo || !sourceFile) return;
							const annotation = {
								...$annotations[annotationIndex],
							};
							const newTimeStr = formatTimestamp(newTime);

							if (
								evidenceIndex !== undefined &&
								evidenceIndex >= 0 &&
								annotation.answer_evidence?.[evidenceIndex]
							) {
								const updatedEvidence = [
									...annotation.answer_evidence,
								];
								const ev = {
									...updatedEvidence[evidenceIndex],
								};
								if (ev.bounding_boxes) {
									ev.bounding_boxes = ev.bounding_boxes.map(
										(b, i) =>
											i === boxIndex
												? {
														...b,
														timestamp: newTimeStr,
													}
												: b,
									);
								}
								updatedEvidence[evidenceIndex] = ev;
								annotation.answer_evidence = updatedEvidence;
							} else if (annotation.location?.boxes?.[boxIndex]) {
								const updatedBoxes = [
									...(annotation.location.boxes || []),
								];
								updatedBoxes[boxIndex] = {
									...updatedBoxes[boxIndex],
									timestamp: newTimeStr,
								};
								annotation.location = {
									...annotation.location,
									boxes: updatedBoxes,
								};
							}

							const localIndex =
								getLocalIndexInFile(annotationIndex);
							try {
								const result = await apiClient.updateAnnotation(
									$currentVideo.filename,
									sourceFile,
									localIndex,
									annotation,
								);
								if (result.success) {
									updateAnnotationInStore(
										annotationIndex,
										annotation,
									);
									showAlert(
										"success",
										`Box timestamp updated to ${newTimeStr}`,
									);
								} else {
									showAlert(
										"error",
										result.error ||
											"Failed to update box timestamp",
									);
								}
							} catch (error) {
								showAlert("error", `Error: ${error}`);
							}
						}}
					/>
				</div>

				<ActionBar
					onAddAnnotation={openAddModal}
					onShowSummary={showSummary}
				/>

				<AnnotationsPanel
					annotations={$annotations}
					{activeAnnotationIndex}
					{annotationsLoading}
					{boxDrawMode}
					{activeVideoSource}
					{annotationSourceFiles}
					currentVideoPath={$currentVideo?.path ||
						`/uploads/${$currentVideo?.filename}`}
					collapsed={annotationsPanelCollapsed}
					onNavigateNext={navigateToNextAnnotation}
					onNavigatePrevious={navigateToPreviousAnnotation}
					onSeek={(ts, videoPath) => {
						// Delegate seek with the complex marker logic
						const index = activeAnnotationIndex;
						activeAnnotationIndex = index;
						const ann = $annotations[index];
						const tsSeconds = parseTimestamp(ts);
						let marker: ActiveTimeMarker | null = null;

						if (
							ann?.question_time_span?.start &&
							parseTimestamp(ann.question_time_span.start) ===
								tsSeconds
						) {
							marker = {
								type: "timespan",
								startTime: tsSeconds,
								endTime: ann.question_time_span.end
									? parseTimestamp(ann.question_time_span.end)
									: undefined,
								annotationIndex: index,
								field: "question_time_span",
							};
						}

						if (!marker && ann?.answer_evidence) {
							for (
								let ei = 0;
								ei < ann.answer_evidence.length;
								ei++
							) {
								const ev = ann.answer_evidence[ei];
								if (ev.time_spans) {
									for (
										let si = 0;
										si < ev.time_spans.length;
										si++
									) {
										const span = ev.time_spans[si];
										if (
											span.start &&
											parseTimestamp(span.start) ===
												tsSeconds
										) {
											marker = {
												type: "timespan",
												startTime: tsSeconds,
												endTime: span.end
													? parseTimestamp(span.end)
													: undefined,
												annotationIndex: index,
												field: "evidence_time_span",
												evidenceIndex: ei,
												spanIndex: si,
											};
											break;
										}
									}
								}
								if (marker) break;
							}
						}

						if (
							!marker &&
							ann?.time_span?.start &&
							parseTimestamp(ann.time_span.start) === tsSeconds
						) {
							marker = {
								type: "timespan",
								startTime: tsSeconds,
								endTime: ann.time_span.end
									? parseTimestamp(ann.time_span.end)
									: undefined,
								annotationIndex: index,
								field: "time_span",
							};
						}

						activeTimeMarker = marker;

						const resolvedVideoPath = videoPath
							? resolveVideoSource(videoPath)
							: null;
						if (
							resolvedVideoPath &&
							resolvedVideoPath !== activeVideoSource
						) {
							pendingSeek = {
								timestamp: parseTimestamp(ts),
								autoPlay: false,
							};
							setActiveVideoSource(resolvedVideoPath, false);
						} else {
							// Enable autoplay when clicking Play button or timestamp
							seekTo(ts, false);
						}
					}}
					onShowBox={(
						box,
						boxIndex,
						annotationIndex,
						evidenceIndex,
					) =>
						handleShowBox(
							box,
							boxIndex,
							annotationIndex,
							evidenceIndex,
						)}
					onEdit={handleEdit}
					onReview={handleReview}
					onDelete={handleDelete}
					onSelect={handleSelectAnnotation}
					onQuickAdd={handleQuickAddBox}
					onToggleCollapse={() =>
						(annotationsPanelCollapsed =
							!annotationsPanelCollapsed)}
				/>
			</div></CardContent
		>
	</Card>

	<!-- Edit Modal -->
	<EditAnnotationModal
		annotation={editingAnnotation}
		open={editModalOpen}
		currentVideoPath={$currentVideo?.path ||
			`/uploads/${$currentVideo?.filename}`}
		onSave={handleSaveEdit}
		onCancel={handleCancelEdit}
	/>

	<!-- Add Modal -->
	<AddAnnotationModal
		open={addModalOpen}
		currentVideoPath={$currentVideo?.path ||
			`/uploads/${$currentVideo?.filename}`}
		currentTime={formatTimestamp(videoPlayer?.currentTime || 0)}
		onAdd={handleAddAnnotation}
		onCancel={() => (addModalOpen = false)}
	/>

	<SummaryModal
		open={summaryModalOpen}
		summaryData={summaryData ?? {}}
		onClose={() => (summaryModalOpen = false)}
	/>

	<PromptPreviewModal
		open={promptPreviewModalOpen}
		content={promptPreviewContent}
		onClose={() => (promptPreviewModalOpen = false)}
	/>

	<DebugModal
		bind:open={debugModalOpen}
		title={debugModalTitle}
		content={debugModalContent}
		contentType={debugModalType}
	/>

	<!-- Context Menu -->
	{#if contextMenu.show}
		<!-- Backdrop to close menu on outside click -->
		<!-- svelte-ignore a11y_click_events_have_key_events -->
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="fixed inset-0 z-40" onclick={closeContextMenu}></div>

		<!-- Context Menu -->
		<div
			class="fixed z-50 bg-white border border-gray-200 rounded-lg shadow-lg py-1 min-w-[200px]"
			style="left: {contextMenu.x}px; top: {contextMenu.y}px;"
		>
			<div class="px-3 py-2 text-xs font-semibold text-gray-500 border-b">
				At {formatTimestamp(contextMenu.time)}
			</div>

			{#if contextMenu.annotation && contextMenu.annotationIndex !== undefined && contextMenu.annotationIndex >= 0}
				<button
					class="w-full text-left px-4 py-2 hover:bg-gray-100 text-sm flex items-center gap-2"
					onclick={addBoundingBoxAtTime}
				>
					<span>📦</span>
					<span>Add Bounding Box</span>
				</button>
				<button
					class="w-full text-left px-4 py-2 hover:bg-gray-100 text-sm flex items-center gap-2"
					onclick={addAnswerEvidenceAtTime}
				>
					<span>📄</span>
					<span>Add Answer Evidence</span>
				</button>
				<div class="border-t my-1"></div>
				<div class="px-4 py-1 text-xs text-gray-500">
					Selected: Q{contextMenu.annotationIndex + 1}
				</div>
			{:else}
				<div class="px-4 py-2 text-sm text-gray-500">
					Select an annotation first
				</div>
				<div class="border-t my-1"></div>
			{/if}

			<button
				class="w-full text-left px-4 py-2 hover:bg-gray-100 text-sm flex items-center gap-2"
				onclick={createNewAnnotationAtTime}
			>
				<span>➕</span>
				<span>New Annotation</span>
			</button>
		</div>
	{/if}
{/if}
