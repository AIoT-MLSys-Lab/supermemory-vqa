<script lang="ts">
	import { Card, CardHeader, CardTitle, CardContent } from '$lib/components/ui/card';
	import Button from '$lib/components/ui/button/Button.svelte';
	import Input from '$lib/components/ui/input/Input.svelte';
	import Label from '$lib/components/ui/label/Label.svelte';
	import FolderBrowser from './FolderBrowser.svelte';
	import { apiClient } from '$lib/api';
	import { videos, showAlert, folderPath } from '$lib/stores';
	import { onMount } from 'svelte';

	let isUploading = $state(false);
	let isDragover = $state(false);
	let showFolderBrowser = $state(false);

	// Load current folder path on mount
	onMount(async () => {
		try {
			const result = await apiClient.getVideoFolder();
			if (result.success && result.data?.folder_path) {
				folderPath.set(result.data.folder_path);
			}
		} catch (error) {
			console.error('Error loading current folder:', error);
		}
	});

	async function setVideoFolder() {
		const path = $folderPath.trim();
		if (!path) {
			showAlert('error', 'Please enter a folder path');
			return;
		}
		try {
			const result = await apiClient.setVideoFolder(path);
			if (result.success) {
				showAlert('success', 'Video folder set successfully');
				// Reload videos
				const videoList = await apiClient.listVideos();
				videos.set(videoList);
			} else {
				showAlert('error', result.error || 'Failed to set folder');
			}
		} catch (error) {
			showAlert('error', `Error setting folder: ${error}`);
		}
	}

	function handleFolderSelect(path: string) {
		folderPath.set(path);
		showFolderBrowser = false;
		// Automatically set the folder after selection
		setVideoFolder();
	}

	function openFolderBrowser() {
		showFolderBrowser = true;
	}

	function closeFolderBrowser() {
		showFolderBrowser = false;
	}

	async function handleFileUpload(file: File) {
		if (!file.type.startsWith('video/')) {
			showAlert('error', 'Please select a video file');
			return;
		}

		isUploading = true;
		try {
			const result = await apiClient.uploadVideo(file);
			if (result.success) {
				showAlert('success', 'Video uploaded successfully');
				// Reload videos
				const videoList = await apiClient.listVideos();
				videos.set(videoList);
			} else {
				showAlert('error', result.error || 'Failed to upload video');
			}
		} catch (error) {
			showAlert('error', `Error uploading video: ${error}`);
		} finally {
			isUploading = false;
		}
	}

	function handleDrop(event: DragEvent) {
		event.preventDefault();
		isDragover = false;
		const files = event.dataTransfer?.files;
		if (files && files.length > 0) {
			handleFileUpload(files[0]);
		}
	}

	function handleDragOver(event: DragEvent) {
		event.preventDefault();
		isDragover = true;
	}

	function handleDragLeave() {
		isDragover = false;
	}

	function handleFileSelect(event: Event) {
		const target = event.target as HTMLInputElement;
		const files = target.files;
		if (files && files.length > 0) {
			handleFileUpload(files[0]);
		}
	}
</script>

{#if showFolderBrowser}
	<FolderBrowser onSelect={handleFolderSelect} onCancel={closeFolderBrowser} />
{/if}

<div class="grid md:grid-cols-2 gap-6">
	<!-- Folder Selection -->
	<Card>
		<CardHeader>
			<CardTitle>📁 Video Folder</CardTitle>
		</CardHeader>
		<CardContent>
			<div class="space-y-4">
				<div class="space-y-2">
					<Label for="folderPath">Specify folder containing videos</Label>
					<div class="flex gap-2">
						<Input
							id="folderPath"
							bind:value={$folderPath}
							placeholder="/path/to/videos"
							readonly
							aria-label="Selected folder path (use Browse button to change)"
						/>
						<Button onclick={openFolderBrowser}>Browse...</Button>
					</div>
					<p class="text-sm text-muted-foreground">
						Click "Browse..." to select a folder from the server
					</p>
				</div>
			</div>
		</CardContent>
	</Card>

	<!-- Upload Section -->
	<Card>
		<CardHeader>
			<CardTitle>📤 Upload Video</CardTitle>
		</CardHeader>
		<CardContent>
			<div
				class="upload-area {isDragover ? 'dragover' : ''}"
				ondrop={handleDrop}
				ondragover={handleDragOver}
				ondragleave={handleDragLeave}
				onclick={() => document.getElementById('fileInput')?.click()}
				role="button"
				tabindex="0"
				onkeydown={(e) => e.key === 'Enter' && document.getElementById('fileInput')?.click()}
			>
				{#if isUploading}
					<div class="flex flex-col items-center">
						<div class="spinner"></div>
						<p class="mt-4 text-foreground">Uploading...</p>
					</div>
				{:else}
					<div class="text-4xl mb-2">📹</div>
					<p><strong>Click to select</strong> or drag and drop a video file</p>
					<p class="text-sm text-muted-foreground mt-2">Supported formats: MP4, AVI, MOV, MKV, WebM</p>
				{/if}
				<input
					type="file"
					id="fileInput"
					accept="video/*"
					class="hidden"
					onchange={handleFileSelect}
				/>
			</div>
		</CardContent>
	</Card>
</div>
