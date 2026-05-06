<script lang="ts">
	import {
		Card,
		CardHeader,
		CardTitle,
		CardContent,
	} from "$lib/components/ui/card";
	import Badge from "$lib/components/ui/badge/Badge.svelte";
	import {
		videos,
		currentVideo,
		playerSectionActive,
		videoLoading,
		showAlert,
	} from "$lib/stores";
	import type { Video } from "$lib/types";
	import { apiClient, type ConversionTask, type TaskEvent } from "$lib/api";
	import { onMount, onDestroy } from "svelte";

	// Fallback polling interval if SSE fails completely
	const POLL_INTERVAL_MS = 5000;
	// SSE reconnection settings
	const SSE_RECONNECT_DELAY_MS = 5000;
	const SSE_MAX_RECONNECT_ATTEMPTS = 10;

	let loading = $state(true);
	let processingFiles = $state<Map<string, ConversionTask>>(new Map());
	let eventSource: EventSource | null = null;
	let pollInterval: ReturnType<typeof setInterval> | null = null;
	let usingSSE = $state(false);
	let numWorkers = $state(0);
	let sseReconnectAttempts = 0;
	let sseReconnectTimeout: ReturnType<typeof setTimeout> | null = null;

	onMount(async () => {
		await loadVideos();
		// Try to connect via SSE first
		connectSSE();
	});

	onDestroy(() => {
		cleanupConnections();
	});

	function cleanupConnections() {
		if (eventSource) {
			eventSource.close();
			eventSource = null;
		}
		if (pollInterval) {
			clearInterval(pollInterval);
			pollInterval = null;
		}
		if (sseReconnectTimeout) {
			clearTimeout(sseReconnectTimeout);
			sseReconnectTimeout = null;
		}
	}

	function connectSSE() {
		// Clean up any existing connection first
		if (eventSource) {
			console.log(
				"Closing existing SSE connection before reconnecting...",
			);
			eventSource.close();
			eventSource = null;
		}

		try {
			console.log("Initiating SSE connection to /api/task-events...");
			eventSource = apiClient.createTaskEventSource(
				handleTaskEvent,
				handleSSEError,
				handleSSEOpen,
			);
			// Don't set usingSSE = true here - wait for onOpen callback
		} catch (error) {
			console.warn(
				"SSE Setup failed immediately, falling back to polling:",
				error,
			);
			startPolling();
		}
	}

	function handleSSEOpen() {
		// SSE connection successfully opened
		usingSSE = true;
		sseReconnectAttempts = 0; // Reset on successful connection

		// Stop polling if it was running (e.g., after successful reconnect)
		if (pollInterval) {
			clearInterval(pollInterval);
			pollInterval = null;
			console.log("Stopped polling - SSE connected");
		}

		console.log("SSE connected for real-time task updates");
	}

	function handleTaskEvent(event: TaskEvent) {
		switch (event.event) {
			case "init":
				// Initial state with all active tasks
				if (event.data?.active_tasks) {
					const newMap = new Map<string, ConversionTask>();
					for (const [taskId, task] of Object.entries(
						event.data.active_tasks,
					)) {
						newMap.set(task.filename, task);
					}
					processingFiles = newMap;
				}
				if (event.data?.num_workers !== undefined) {
					numWorkers = event.data.num_workers;
				}
				break;

			case "task_started":
				if (event.data?.filename) {
					processingFiles.set(
						event.data.filename,
						event.data as unknown as ConversionTask,
					);
					processingFiles = new Map(processingFiles);
					showAlert(
						"info",
						`Started converting ${event.data.filename} to MP4`,
					);
				}
				break;

			case "task_progress":
				if (
					event.data?.filename &&
					processingFiles.has(event.data.filename)
				) {
					const task = processingFiles.get(event.data.filename);
					if (task) {
						task.progress = event.data.progress || 0;
						task.message = event.data.message || "Processing...";
						processingFiles = new Map(processingFiles);
					}
				}
				break;

			case "task_completed":
				if (event.data?.filename) {
					const wasProcessing = processingFiles.has(
						event.data.filename,
					);
					processingFiles.delete(event.data.filename);
					processingFiles = new Map(processingFiles);

					if (wasProcessing) {
						if (event.data.status === "completed") {
							console.log(
								`[VideoList] Task completed successfully: ${event.data.filename}`,
							);
							showAlert(
								"success",
								`Conversion completed: ${event.data.filename}`,
							);
						} else if (event.data.status === "failed") {
							console.error(
								`[VideoList] Task failed: ${event.data.filename} - ${event.data.error}`,
							);
							showAlert(
								"error",
								`Conversion failed: ${event.data.error || "Unknown error"}`,
							);
						}
						// Reload videos to show the new file (silently)
						loadVideos(true);
					}
				}
				break;

			case "task_cancelled":
				if (event.data?.filename) {
					console.log(
						`[VideoList] Task cancelled: ${event.data.filename}`,
					);
					processingFiles.delete(event.data.filename);
					processingFiles = new Map(processingFiles);
				}
				break;

			case "heartbeat":
				// Connection is alive, nothing to do
				break;
		}
	}

	function handleSSEError(error: Event) {
		// SSE connection error - try to reconnect before falling back to polling
		console.warn("SSE connection error:", error);

		if (eventSource) {
			eventSource.close();
			eventSource = null;
		}

		// Try to reconnect a few times before giving up
		if (sseReconnectAttempts < SSE_MAX_RECONNECT_ATTEMPTS) {
			sseReconnectAttempts++;
			console.log(
				`SSE reconnection attempt ${sseReconnectAttempts}/${SSE_MAX_RECONNECT_ATTEMPTS} in ${SSE_RECONNECT_DELAY_MS}ms...`,
			);

			sseReconnectTimeout = setTimeout(() => {
				connectSSE();
			}, SSE_RECONNECT_DELAY_MS);
		} else {
			// Give up and fall back to polling
			console.error(
				`SSE failed after ${SSE_MAX_RECONNECT_ATTEMPTS} attempts, permanently falling back to polling`,
			);
			usingSSE = false;
			startPolling();
		}
	}

	function startPolling() {
		if (pollInterval) return;

		// Initial check
		checkProcessingStatus();

		// Start polling at a slower rate than before (5s instead of 2s)
		pollInterval = setInterval(checkProcessingStatus, POLL_INTERVAL_MS);
		console.log("Started polling for task status (fallback mode)");
	}

	async function loadVideos(silent = false) {
		if (!silent) {
			loading = true;
		}
		try {
			const videoList = await apiClient.listVideos();
			videos.set(videoList);
		} catch (error) {
			console.error("Failed to load videos:", error);
			showAlert("error", "Failed to load videos");
		} finally {
			if (!silent) {
				loading = false;
			}
		}
	}

	async function checkProcessingStatus() {
		try {
			const status = await apiClient.getAllConversionStatus();
			const newProcessingFiles = new Map<string, ConversionTask>();

			for (const [taskId, task] of Object.entries(status.active_tasks)) {
				newProcessingFiles.set(task.filename, task);
			}

			// Check if any tasks completed - reload videos if so
			const hadProcessing = processingFiles.size > 0;
			const completedTasks = [...processingFiles.keys()].filter(
				(filename) => !newProcessingFiles.has(filename),
			);

			processingFiles = newProcessingFiles;

			// If tasks completed, reload the video list
			if (hadProcessing && completedTasks.length > 0) {
				await loadVideos();
				for (const filename of completedTasks) {
					showAlert("success", `Conversion completed: ${filename}`);
				}
			}
		} catch (error) {
			console.error("Failed to check processing status:", error);
		}
	}

	function selectVideo(video: Video) {
		// Only allow selecting processed videos
		if (video.type === "vrs" && !video.is_processed) {
			showAlert("info", "Please process this VRS file first to view it");
			return;
		}
		currentVideo.set(video);
		playerSectionActive.set(true);
	}

	async function processVrs(video: Video, event: Event) {
		event.stopPropagation();
		if (processingFiles.has(video.filename)) return;

		try {
			const result = await apiClient.convertVrs(video.filename, true);
			if (result.success) {
				showAlert(
					"info",
					`Started converting ${video.filename} to MP4`,
				);
				// SSE will notify us when the task starts - no need to poll
				// If not using SSE, check status once
				if (!usingSSE) {
					await checkProcessingStatus();
				}
			} else {
				showAlert(
					"error",
					result.error || "Failed to start conversion",
				);
			}
		} catch (error) {
			console.error("Failed to start VRS conversion:", error);
			showAlert("error", "Failed to start VRS conversion");
		}
	}

	async function cancelProcessing(filename: string, event: Event) {
		event.stopPropagation();

		try {
			const result = await apiClient.cancelConversion(filename);
			if (result.success) {
				showAlert("info", `Cancelled conversion for ${filename}`);
				// Remove from processing map efficiently
				processingFiles.delete(filename);
				processingFiles = new Map(processingFiles);
			} else {
				showAlert(
					"error",
					result.error || "Failed to cancel conversion",
				);
			}
		} catch (error) {
			console.error("Failed to cancel conversion:", error);
			showAlert("error", "Failed to cancel conversion");
		}
	}

	async function recreateVideo(video: Video, event: Event) {
		event.stopPropagation();
		const vrsFilename = video.source_vrs_filename;
		if (!vrsFilename || processingFiles.has(vrsFilename)) return;

		try {
			const result = await apiClient.recreateVideo(video.filename, true);
			if (result.success) {
				showAlert(
					"info",
					`Started recreating ${video.filename} from VRS`,
				);
				// SSE will notify us when the task starts - no need to poll
				// If not using SSE, check status once
				if (!usingSSE) {
					await checkProcessingStatus();
				}
			} else {
				showAlert(
					"error",
					result.error || "Failed to start recreation",
				);
			}
		} catch (error) {
			console.error("Failed to start video recreation:", error);
			showAlert("error", "Failed to start video recreation");
		}
	}

	function isProcessing(filename: string): boolean {
		return processingFiles.has(filename);
	}

	function isVrsProcessing(video: Video): boolean {
		// For VRS files, check if the file itself is processing
		if (video.type === "vrs") {
			return processingFiles.has(video.filename);
		}
		// For videos with VRS source, check if the VRS is processing
		if (video.source_vrs_filename) {
			return processingFiles.has(video.source_vrs_filename);
		}
		return false;
	}

	function getProcessingFilename(video: Video): string {
		if (video.type === "vrs") {
			return video.filename;
		}
		return video.source_vrs_filename || video.filename;
	}
</script>

<Card>
	<CardHeader>
		<div class="flex items-center justify-between">
			<CardTitle class="text-lg font-semibold">Video Library</CardTitle>
			<div class="flex items-center gap-2 text-xs text-muted-foreground">
				{#if loading}
					<span>Loading...</span>
				{:else}
					<span>{$videos.length} {$videos.length === 1 ? 'video' : 'videos'}</span>
				{/if}
			</div>
		</div>
	</CardHeader>
	<CardContent>
		{#if loading}
			<div class="flex flex-col items-center py-12">
				<div class="spinner"></div>
				<p class="mt-4 text-sm text-muted-foreground">Loading videos...</p>
			</div>
		{:else if $videos.length === 0}
			<div class="text-center py-12 px-4">
				<div class="w-16 h-16 mx-auto mb-4 rounded-full bg-secondary flex items-center justify-center">
					<svg xmlns="http://www.w3.org/2000/svg" class="w-8 h-8 text-muted-foreground" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path d="M23 7l-7 5 7 5V7z"></path>
						<rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
					</svg>
				</div>
				<h3 class="text-sm font-medium text-foreground mb-2">No videos found</h3>
				<p class="text-sm text-muted-foreground max-w-sm mx-auto">
					Upload a video or set a video folder to get started with annotation.
				</p>
			</div>
		{:else}
			<div
				class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4"
			>
				{#each $videos as video}
					<div
						class="video-card text-left {$currentVideo?.filename ===
						video.filename
							? 'selected'
							: ''} {video.type === 'vrs'
							? 'vrs-file'
							: ''} {isVrsProcessing(video) ? 'processing' : ''}"
						onclick={() =>
							!isVrsProcessing(video) && selectVideo(video)}
						onkeydown={(e) =>
							e.key === "Enter" &&
							!isVrsProcessing(video) &&
							selectVideo(video)}
						role="button"
						tabindex="0"
					>
						<div class="flex items-center gap-2 mb-2">
							<!-- Icon based on file type -->
							{#if video.type === "vrs"}
								<!-- VRS icon -->
								<div
									class="w-8 h-8 flex-shrink-0 rounded bg-accent flex items-center justify-center vrs-icon-container"
									title="VRS Recording"
								>
									<!-- Inline VRS Logo SVG matching the official branding from facebookresearch.github.io/vrs -->
									<svg
										class="w-6 h-6 vrs-logo"
										viewBox="0 0 100 100"
										xmlns="http://www.w3.org/2000/svg"
									>
										<defs>
											<linearGradient
												id="vrsGradient"
												x1="0%"
												y1="0%"
												x2="100%"
												y2="100%"
											>
												<stop
													offset="0%"
													stop-color="hsl(var(--color-primary))"
													stop-opacity="1"
												/>
												<stop
													offset="100%"
													stop-color="hsl(var(--color-primary))"
													stop-opacity="0.6"
												/>
											</linearGradient>
										</defs>
										<rect
											x="5"
											y="5"
											width="90"
											height="90"
											rx="15"
											fill="url(#vrsGradient)"
										/>
										<text
											x="50"
											y="62"
											text-anchor="middle"
											font-family="Arial, sans-serif"
											font-size="28"
											font-weight="bold"
											fill="white">VRS</text
										>
									</svg>
								</div>
							{:else}
								<!-- Video icon with green background for processed -->
								<div
									class="w-8 h-8 flex-shrink-0 rounded {video.is_processed
										? 'bg-success/20'
										: 'bg-secondary'} flex items-center justify-center"
									title={video.is_processed
										? "Processed Video"
										: "Video"}
								>
									<span class="text-lg">🎥</span>
								</div>
							{/if}
							<h3
								class="font-medium text-sm truncate flex-1"
								title={video.filename}
							>
								{video.filename}
							</h3>
							<!-- Action buttons -->
							{#if isVrsProcessing(video)}
								<!-- Stop button when processing -->
								<button
									class="action-btn stop-btn"
									onclick={(e) =>
										cancelProcessing(
											getProcessingFilename(video),
											e,
										)}
									title="Stop conversion"
								>
									<svg
										xmlns="http://www.w3.org/2000/svg"
										class="w-4 h-4"
										viewBox="0 0 24 24"
										fill="currentColor"
									>
										<rect
											x="6"
											y="6"
											width="12"
											height="12"
											rx="1"
										></rect>
									</svg>
								</button>
							{:else if video.type === "vrs"}
								<!-- Process VRS button -->
								<button
									class="action-btn process-btn"
									onclick={(e) => processVrs(video, e)}
									title="Convert to MP4"
								>
									<svg
										xmlns="http://www.w3.org/2000/svg"
										class="w-4 h-4"
										viewBox="0 0 24 24"
										fill="none"
										stroke="currentColor"
										stroke-width="2"
										stroke-linecap="round"
										stroke-linejoin="round"
									>
										<polygon points="5 3 19 12 5 21 5 3"
										></polygon>
									</svg>
								</button>
							{:else if video.has_source_vrs}
								<!-- Recreate video button -->
								<button
									class="action-btn recreate-btn"
									onclick={(e) => recreateVideo(video, e)}
									title="Recreate from VRS"
								>
									<svg
										xmlns="http://www.w3.org/2000/svg"
										class="w-4 h-4"
										viewBox="0 0 24 24"
										fill="none"
										stroke="currentColor"
										stroke-width="2"
										stroke-linecap="round"
										stroke-linejoin="round"
									>
										<path
											d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"
										></path>
										<path d="M3 3v5h5"></path>
										<path
											d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"
										></path>
										<path d="M16 16h5v5"></path>
									</svg>
								</button>
							{/if}
						</div>
						<!-- Processing status -->
						{#if isVrsProcessing(video)}
							<div
								class="flex items-center gap-2 text-xs text-foreground mb-2 bg-primary/5 px-2 py-1 rounded-md"
							>
								<span class="spinner-small"></span>
								<span>Converting to MP4...</span>
							</div>
						{/if}
						<!-- Metadata row: duration and size -->
						<div
							class="flex items-center gap-3 text-xs text-muted-foreground mb-2"
						>
							{#if video.duration_formatted}
								<span title="Duration" class="flex items-center gap-1">
									<svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
										<circle cx="12" cy="12" r="10"></circle>
										<polyline points="12 6 12 12 16 14"></polyline>
									</svg>
									{video.duration_formatted}
								</span>
							{/if}
							{#if video.size_formatted}
								<span title="File size" class="flex items-center gap-1">
									<svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
										<path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"></path>
										<polyline points="13 2 13 9 20 9"></polyline>
									</svg>
									{video.size_formatted}
								</span>
							{/if}
						</div>
						<!-- Status badges -->
						<div class="flex items-center gap-2 flex-wrap">
							{#if video.type === "vrs"}
								<Badge variant="secondary">VRS Recording</Badge>
							{:else if video.is_processed}
								<Badge variant="success">Processed</Badge>
							{/if}
							{#if video.has_source_vrs}
								<Badge variant="info">Has VRS Source</Badge>
							{/if}
							{#if video.has_annotations}
								<Badge variant="success">
									{video.annotations_count || 0} annotations
								</Badge>
							{:else}
								<Badge variant="warning">No annotations</Badge>
							{/if}
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</CardContent>
</Card>

<style>
	.video-card.vrs-file {
		border-style: dashed;
		background-color: rgba(147, 51, 234, 0.05);
	}

	.video-card.processing {
		border-color: rgb(59, 130, 246);
		background-color: rgba(59, 130, 246, 0.05);
		animation: pulse-border 2s ease-in-out infinite;
	}

	@keyframes pulse-border {
		0%,
		100% {
			border-color: rgb(59, 130, 246);
		}
		50% {
			border-color: rgb(147, 197, 253);
		}
	}

	.action-btn {
		padding: 0.25rem;
		border-radius: 0.375rem;
		transition: all 0.2s;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.action-btn:hover:not(:disabled) {
		transform: scale(1.1);
	}

	.action-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.process-btn {
		background-color: rgba(34, 197, 94, 0.1);
		color: rgb(22, 163, 74);
	}

	.process-btn:hover:not(:disabled) {
		background-color: rgba(34, 197, 94, 0.2);
	}

	.recreate-btn {
		background-color: rgba(59, 130, 246, 0.1);
		color: rgb(37, 99, 235);
	}

	.recreate-btn:hover:not(:disabled) {
		background-color: rgba(59, 130, 246, 0.2);
	}

	.stop-btn {
		background-color: rgba(239, 68, 68, 0.1);
		color: rgb(220, 38, 38);
	}

	.stop-btn:hover:not(:disabled) {
		background-color: rgba(239, 68, 68, 0.2);
	}

	.spinner-small {
		width: 1rem;
		height: 1rem;
		border: 2px solid hsl(var(--color-border));
		border-top-color: currentColor;
		border-radius: 50%;
		animation: spin 1s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
</style>
