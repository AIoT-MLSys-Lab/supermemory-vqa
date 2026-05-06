<script lang="ts">
	import Label from "$lib/components/ui/label/Label.svelte";
	import { apiClient } from "$lib/api";
	import { showAlert } from "$lib/stores";
	import type { AnnotationFile } from "$lib/types";

	interface Props {
		videoFilename: string;
		annotationFiles: AnnotationFile[];
		selectedFiles: string[];
		onSelectionChange: (filenames: string[]) => void;
		onRefresh: () => void;
		children?: import("svelte").Snippet;
	}

	let {
		videoFilename,
		annotationFiles,
		selectedFiles,
		onSelectionChange,
		onRefresh,
		children,
	}: Props = $props();

	let creating = $state(false);
	let deleting = $state(false);

	function handleCheckboxChange(filename: string, checked: boolean) {
		if (checked) {
			// Add to selection
			onSelectionChange([...selectedFiles, filename]);
		} else {
			// Remove from selection
			onSelectionChange(selectedFiles.filter((f) => f !== filename));
		}
	}

	function selectAll() {
		onSelectionChange(annotationFiles.map((f) => f.filename));
	}

	function selectNone() {
		onSelectionChange([]);
	}

	async function createNewFile() {
		creating = true;
		try {
			const result = await apiClient.createAnnotationFile(videoFilename);
			if (result.success) {
				showAlert("success", "New annotation file created");
				onRefresh();
			} else {
				showAlert("error", result.error || "Failed to create file");
			}
		} catch (error) {
			showAlert("error", `Error: ${error}`);
		} finally {
			creating = false;
		}
	}

	async function deleteSelectedFiles() {
		if (selectedFiles.length === 0) return;
		const selectedFileCount = selectedFiles.length;
		if (
			!confirm(
				`Delete ${selectedFileCount} annotation file${selectedFileCount > 1 ? "s" : ""}? This cannot be undone.`,
			)
		)
			return;

		deleting = true;
		try {
			let successCount = 0;
			let failCount = 0;
			for (const filename of selectedFiles) {
				const result = await apiClient.deleteAnnotationFile(
					videoFilename,
					filename,
				);
				if (result.success) {
					successCount++;
				} else {
					failCount++;
				}
			}
			if (successCount > 0) {
				showAlert(
					"success",
					`Deleted ${successCount} annotation file${successCount > 1 ? "s" : ""}`,
				);
				onRefresh();
			}
			if (failCount > 0) {
				showAlert(
					"error",
					`Failed to delete ${failCount} file${failCount > 1 ? "s" : ""}`,
				);
			}
		} catch (error) {
			showAlert("error", `Error: ${error}`);
		} finally {
			deleting = false;
		}
	}
</script>

<div class="p-4 bg-secondary rounded-lg mb-4">
	<div class="flex items-center justify-between mb-3">
		<Label class="text-sm font-semibold">Annotation Files</Label>
		<div class="flex gap-2">
			<button
				type="button"
				class="text-xs text-primary hover:text-primary/80 hover:underline"
				onclick={selectAll}
				disabled={annotationFiles.length === 0}
			>
				Select All
			</button>
			<span class="text-border">|</span>
			<button
				type="button"
				class="text-xs text-primary hover:text-primary/80 hover:underline"
				onclick={selectNone}
				disabled={selectedFiles.length === 0}
			>
				Select None
			</button>
		</div>
	</div>

	{#if annotationFiles.length === 0}
		<p class="text-sm text-muted-foreground italic py-2">No annotation files</p>
	{:else}
		<div class="space-y-2 max-h-48 overflow-y-auto">
			{#each annotationFiles as file, index}
				<label
					class="flex items-center gap-2 p-2 rounded hover:bg-background cursor-pointer"
				>
					<input
						type="checkbox"
						checked={selectedFiles.includes(file.filename)}
						onchange={(e) =>
							handleCheckboxChange(
								file.filename,
								e.currentTarget.checked,
							)}
						class="w-4 h-4 text-primary rounded border-border focus:ring-primary"
					/>
					<span class="text-sm flex-1">
						<span class="font-medium">#{index + 1}:</span>
						<span class="text-foreground">{file.filename}</span>
						<span class="text-muted-foreground"
							>({file.annotations?.length || 0} annotations)</span
						>
					</span>
				</label>
			{/each}
		</div>
	{/if}

	<div class="flex items-center gap-2 mt-2 pt-2 border-t border-border">
		{@render children?.()}
		<button
			type="button"
			class="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
			title="Create New File"
			onclick={createNewFile}
			disabled={creating}
		>
			{#if creating}
				<span class="spinner w-3 h-3"></span>
			{:else}
				<svg
					xmlns="http://www.w3.org/2000/svg"
					class="h-3.5 w-3.5"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="2"
					><line x1="12" y1="5" x2="12" y2="19" /><line
						x1="5"
						y1="12"
						x2="19"
						y2="12"
					/></svg
				>
			{/if}
			New
		</button>
		<button
			type="button"
			class="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded bg-destructive/10 text-destructive hover:bg-destructive/20 disabled:opacity-50 transition-colors"
			title="Delete Selected Files"
			onclick={deleteSelectedFiles}
			disabled={deleting || selectedFiles.length === 0}
		>
			{#if deleting}
				<span class="spinner w-3 h-3"></span>
			{:else}
				<svg
					xmlns="http://www.w3.org/2000/svg"
					class="h-3.5 w-3.5"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="2"
					><polyline points="3 6 5 6 21 6" /><path
						d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"
					/></svg
				>
			{/if}
			Delete ({selectedFiles.length})
		</button>
	</div>
</div>
