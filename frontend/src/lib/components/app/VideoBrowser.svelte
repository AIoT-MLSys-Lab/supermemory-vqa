<script lang="ts">
	import { apiClient } from '$lib/api';
	import { showAlert, folderPath } from '$lib/stores';
	import Button from '$lib/components/ui/button/Button.svelte';
	import { onMount } from 'svelte';

	interface Props {
		onSelect: (videoPath: string) => void;
		onCancel: () => void;
		currentVideoPath?: string;
	}

	let { onSelect, onCancel, currentVideoPath }: Props = $props();

	let currentPath = $state('');
	let parentPath = $state<string | null>(null);
	let directories = $state<{ name: string; path: string }[]>([]);
	let videoFiles = $state<{ name: string; path: string }[]>([]);
	let loading = $state(false);
	let selectedVideoPath = $state('');

	async function loadContent(path?: string) {
		loading = true;
		try {
			const result = await apiClient.browseFiles(path);
			if (result.success && result.data) {
				currentPath = result.data.current_path;
				parentPath = result.data.parent_path;
				directories = result.data.directories;
				videoFiles = result.data.video_files || [];
			} else {
				showAlert('error', result.error || 'Failed to load files');
			}
		} catch (error) {
			showAlert('error', `Error loading files: ${error}`);
		} finally {
			loading = false;
		}
	}

	function navigateToFolder(path: string) {
		loadContent(path);
	}

	function navigateUp() {
		if (parentPath) {
			loadContent(parentPath);
		}
	}

	function selectVideo(videoPath: string) {
		selectedVideoPath = videoPath;
	}

	function confirmSelection() {
		if (selectedVideoPath) {
			onSelect(selectedVideoPath);
		}
	}

	function selectCurrentVideo() {
		if (currentVideoPath) {
			onSelect(currentVideoPath);
		}
	}

	onMount(() => {
		// Start from the video folder if available, otherwise from root
		const startPath = $folderPath || '';
		loadContent(startPath || undefined);
	});
</script>

<div class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
	<div class="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col">
		<!-- Header -->
		<div class="p-4 border-b">
			<h2 class="text-xl font-semibold">🎬 Select Video</h2>
			<p class="text-sm text-gray-600 mt-1">Browse and select a video file for the answer reference</p>
		</div>

		<!-- Quick Actions -->
		{#if currentVideoPath}
			<div class="p-4 bg-primary/5 border-b">
				<div class="flex items-center gap-2">
					<span class="text-sm text-foreground font-medium">Current video:</span>
					<span class="text-sm font-mono text-muted-foreground truncate flex-1" title={currentVideoPath}>
						{currentVideoPath.split('/').pop() || currentVideoPath}
					</span>
					<Button size="sm" variant="secondary" onclick={selectCurrentVideo}>
						Use Current
					</Button>
				</div>
			</div>
		{/if}

		<!-- Current Path -->
		<div class="p-4 bg-gray-50 border-b">
			<div class="flex items-center gap-2">
				<span class="text-sm font-medium text-gray-700">Path:</span>
				<span class="text-sm text-gray-900 font-mono flex-1 truncate" title={currentPath}>
					{currentPath || 'Loading...'}
				</span>
			</div>
		</div>

		<!-- Navigation -->
		<div class="p-4 border-b">
			<Button
				onclick={navigateUp}
				disabled={!parentPath || loading}
				class="w-full justify-start"
				variant="outline"
			>
				<span class="mr-2">⬆️</span>
				Parent Directory
			</Button>
		</div>

		<!-- Content List -->
		<div class="flex-1 overflow-y-auto p-4">
			{#if loading}
				<div class="flex items-center justify-center py-8">
					<div class="spinner"></div>
					<span class="ml-3 text-gray-600">Loading...</span>
				</div>
			{:else}
				<!-- Folders -->
				{#if directories.length > 0}
					<div class="mb-4">
						<h3 class="text-sm font-medium text-gray-500 mb-2">Folders</h3>
						<div class="space-y-1">
							{#each directories as dir}
								<button
									type="button"
									class="w-full text-left px-4 py-2 rounded-lg hover:bg-gray-100 transition-colors flex items-center gap-3 border border-gray-200"
									onclick={() => navigateToFolder(dir.path)}
								>
									<span class="text-xl">📁</span>
									<span class="flex-1 font-medium truncate">{dir.name}</span>
									<span class="text-gray-400">→</span>
								</button>
							{/each}
						</div>
					</div>
				{/if}

				<!-- Video Files -->
				{#if videoFiles.length > 0}
					<div>
						<h3 class="text-sm font-medium text-gray-500 mb-2">Video Files</h3>
						<div class="space-y-1">
							{#each videoFiles as video}
								<button
									type="button"
									class="w-full text-left px-4 py-2 rounded-lg transition-colors flex items-center gap-3 border {selectedVideoPath === video.path ? 'border-primary bg-primary/10' : 'border-gray-200 hover:bg-gray-100'}"
									onclick={() => selectVideo(video.path)}
								>
									<span class="text-xl">🎥</span>
									<span class="flex-1 font-medium truncate">{video.name}</span>
									{#if selectedVideoPath === video.path}
										<span class="text-primary">✓</span>
									{/if}
								</button>
							{/each}
						</div>
					</div>
				{/if}

				{#if directories.length === 0 && videoFiles.length === 0}
					<div class="text-center py-8 text-gray-500">
						<p>No folders or video files found</p>
					</div>
				{/if}
			{/if}
		</div>

		<!-- Actions -->
		<div class="p-4 border-t flex gap-3">
			<Button
				onclick={confirmSelection}
				disabled={loading || !selectedVideoPath}
				class="flex-1"
			>
				Select Video
			</Button>
			<Button
				onclick={onCancel}
				variant="outline"
				class="flex-1"
			>
				Cancel
			</Button>
		</div>
	</div>
</div>

<style>
	.spinner {
		border: 3px solid hsl(var(--color-border));
		border-top: 3px solid hsl(var(--color-primary));
		border-radius: 50%;
		width: 24px;
		height: 24px;
		animation: spin 1s linear infinite;
	}

	@keyframes spin {
		0% { transform: rotate(0deg); }
		100% { transform: rotate(360deg); }
	}
</style>
