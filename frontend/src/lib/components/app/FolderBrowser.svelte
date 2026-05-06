<script lang="ts">
	import { apiClient } from '$lib/api';
	import { showAlert } from '$lib/stores';
	import Button from '$lib/components/ui/button/Button.svelte';
	import { onMount } from 'svelte';

	interface Props {
		onSelect: (path: string) => void;
		onCancel: () => void;
	}

	let { onSelect, onCancel }: Props = $props();

	let currentPath = $state('');
	let parentPath = $state<string | null>(null);
	let directories = $state<{ name: string; path: string }[]>([]);
	let loading = $state(false);

	async function loadFolders(path?: string) {
		loading = true;
		try {
			const result = await apiClient.browseFolders(path);
			if (result.success && result.data) {
				currentPath = result.data.current_path;
				parentPath = result.data.parent_path;
				directories = result.data.directories;
			} else {
				showAlert('error', result.error || 'Failed to load folders');
			}
		} catch (error) {
			showAlert('error', `Error loading folders: ${error}`);
		} finally {
			loading = false;
		}
	}

	function navigateToFolder(path: string) {
		loadFolders(path);
	}

	function navigateUp() {
		if (parentPath) {
			loadFolders(parentPath);
		}
	}

	function selectCurrentFolder() {
		onSelect(currentPath);
	}

	onMount(() => {
		loadFolders();
	});
</script>

<div class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
	<div class="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col">
		<!-- Header -->
		<div class="p-4 border-b">
			<h2 class="text-xl font-semibold">Select Folder</h2>
		</div>

		<!-- Current Path -->
		<div class="p-4 bg-secondary border-b">
			<div class="flex items-center gap-2">
				<span class="text-sm font-medium text-foreground">Current Path:</span>
				<span class="text-sm text-foreground font-mono flex-1 truncate" title={currentPath}>
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
				{#if parentPath}
					<span class="ml-2 text-xs text-muted-foreground truncate">({parentPath})</span>
				{/if}
			</Button>
		</div>

		<!-- Folder List -->
		<div class="flex-1 overflow-y-auto p-4">
			{#if loading}
				<div class="flex items-center justify-center py-8">
					<div class="spinner"></div>
					<span class="ml-3 text-foreground">Loading folders...</span>
				</div>
			{:else if directories.length === 0}
				<div class="text-center py-8 text-muted-foreground">
					<p>No subdirectories found</p>
				</div>
			{:else}
				<div class="space-y-2">
					{#each directories as dir}
						<button
							type="button"
							class="w-full text-left px-4 py-3 rounded-lg hover:bg-secondary/80 transition-colors flex items-center gap-3 border border-border"
							onclick={() => navigateToFolder(dir.path)}
						>
							<span class="text-2xl">📁</span>
							<span class="flex-1 font-medium">{dir.name}</span>
							<span class="text-muted-foreground">→</span>
						</button>
					{/each}
				</div>
			{/if}
		</div>

		<!-- Actions -->
		<div class="p-4 border-t flex gap-3">
			<Button
				onclick={selectCurrentFolder}
				disabled={loading || !currentPath}
				class="flex-1"
			>
				Select This Folder
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
