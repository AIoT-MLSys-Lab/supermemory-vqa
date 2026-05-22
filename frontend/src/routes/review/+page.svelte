<script lang="ts">
	import Button from "$lib/components/ui/button/Button.svelte";
	import Input from "$lib/components/ui/input/Input.svelte";
	import Badge from "$lib/components/ui/badge/Badge.svelte";
	import FolderBrowser from "$lib/components/app/FolderBrowser.svelte";
	import QAClipPanel from "$lib/components/app/QAClipPanel.svelte";
	import QAAnnotationEditor from "$lib/components/app/QAAnnotationEditor.svelte";
	import { apiClient } from "$lib/api";
	import type { Annotation, QAReviewItem } from "$lib/types";
	import {
		computeQAClips,
		syncAnnotationForSave,
		updateAnnotationClipSpan,
	} from "$lib/utils/qa-review";
	import { deepClone } from "$lib/utils";
	import { folderPath, getReviewStatus, showAlert } from "$lib/stores";
	import { ChevronLeft, ChevronRight, Filter, FolderOpen, RefreshCw, Search } from "lucide-svelte";
	import { onMount } from "svelte";

	let items = $state<QAReviewItem[]>([]);
	let loading = $state(false);
	let saving = $state(false);
	let changingFolder = $state(false);
	let showFolderBrowser = $state(false);
	let error = $state("");
	let folderInput = $state("");
	let activeIndex = $state(0);
	let editedAnnotation = $state<Annotation | null>(null);
	let activeClipKey = $state("");
	let statusFilter = $state<"all" | "pending" | "accepted" | "rejected">("all");
	let typeFilter = $state<"all" | "verified" | "rejected" | "legacy">("all");
	let searchQuery = $state("");

	const filteredItems = $derived.by(() => {
		const query = searchQuery.trim().toLowerCase();
		return items.filter((item) => {
			const ann = item.annotation;
			const status = getReviewStatus(ann.human_review);
			const type = ann.annotation_type || item.source?.annotation_type || "legacy";
			if (statusFilter !== "all" && status !== statusFilter) return false;
			if (typeFilter !== "all" && type !== typeFilter) return false;
			if (!query) return true;
			return [
				ann.question,
				ann.answer,
				ann.room,
				ann.skill,
				item.video_filename,
				item.annotation_filename,
			].some((value) => String(value || "").toLowerCase().includes(query));
		});
	});

	const activeItem = $derived(filteredItems[activeIndex] || null);
	const clips = $derived(
		editedAnnotation && activeItem
			? computeQAClips(editedAnnotation, activeItem.video_filename)
			: [],
	);
	const pendingCount = $derived(items.filter((item) => getReviewStatus(item.annotation.human_review) === "pending").length);
	const acceptedCount = $derived(items.filter((item) => getReviewStatus(item.annotation.human_review) === "accepted").length);
	const rejectedCount = $derived(items.filter((item) => getReviewStatus(item.annotation.human_review) === "rejected").length);

	onMount(() => {
		void loadCurrentFolder();
		void loadQueue();
	});

	$effect(() => {
		if (activeIndex >= filteredItems.length) activeIndex = Math.max(0, filteredItems.length - 1);
	});

	$effect(() => {
		if (activeItem) {
			editedAnnotation = syncAnnotationForSave(deepClone(activeItem.annotation));
		} else {
			editedAnnotation = null;
		}
	});

	$effect(() => {
		if (clips.length === 0) {
			activeClipKey = "";
		} else if (!clips.some((clip) => clip.key === activeClipKey)) {
			activeClipKey = clips[0].key;
		}
	});

	async function loadCurrentFolder() {
		try {
			const res = await apiClient.getVideoFolder();
			if (res.success && res.data?.folder_path) {
				folderPath.set(res.data.folder_path);
				folderInput = res.data.folder_path;
			}
		} catch (err) {
			console.error("Failed to load current video folder", err);
		}
	}

	async function loadQueue() {
		loading = true;
		error = "";
		try {
			const res = await apiClient.listQAReviewItems();
			items = res.items || [];
			activeIndex = 0;
		} catch (err) {
			error = err instanceof Error ? err.message : "Failed to load QA review queue";
		} finally {
			loading = false;
		}
	}

	async function applyVideoFolder(path = folderInput) {
		const nextPath = path.trim();
		if (!nextPath) {
			showAlert("error", "Please enter a video folder path");
			return;
		}
		changingFolder = true;
		try {
			const result = await apiClient.setVideoFolder(nextPath);
			if (!result.success) {
				showAlert("error", result.error || "Failed to update video folder");
				return;
			}
			folderPath.set(nextPath);
			folderInput = nextPath;
			activeIndex = 0;
			activeClipKey = "";
			editedAnnotation = null;
			await loadQueue();
			showAlert("success", "Video folder updated");
		} catch (err) {
			showAlert("error", err instanceof Error ? err.message : "Failed to update video folder");
		} finally {
			changingFolder = false;
		}
	}

	function handleFolderSelect(path: string) {
		showFolderBrowser = false;
		void applyVideoFolder(path);
	}

	function selectRelative(delta: number) {
		if (filteredItems.length === 0) return;
		activeIndex = Math.max(0, Math.min(filteredItems.length - 1, activeIndex + delta));
	}

	function resetActiveIndex() {
		activeIndex = 0;
	}

	async function saveActive() {
		if (!activeItem || !editedAnnotation) return;
		saving = true;
		try {
			const toSave = syncAnnotationForSave(editedAnnotation);
			const result = await apiClient.updateAnnotation(
				activeItem.video_filename,
				activeItem.annotation_filename,
				activeItem.annotation_index,
				toSave,
			);
			if (!result.success) {
				showAlert("error", result.error || "Failed to save QA");
				return;
			}
			items = items.map((item) =>
				item.id === activeItem.id ? { ...item, annotation: toSave } : item,
			);
			editedAnnotation = deepClone(toSave);
			showAlert("success", "QA saved");
		} catch (err) {
			showAlert("error", err instanceof Error ? err.message : "Failed to save QA");
		} finally {
			saving = false;
		}
	}

	function applyCaptionSelection(selection: {
		video_id: string;
		video_path?: string;
		start_time: string;
		end_time: string;
	}) {
		if (!editedAnnotation) return;
		const clip = clips.find((candidate) => candidate.key === activeClipKey) || clips[0];
		if (!clip) return;
		editedAnnotation = updateAnnotationClipSpan(
			editedAnnotation,
			clip,
			{ start: selection.start_time, end: selection.end_time },
			selection.video_path || selection.video_id,
		);
	}
</script>

{#if showFolderBrowser}
	<FolderBrowser onSelect={handleFolderSelect} onCancel={() => (showFolderBrowser = false)} />
{/if}

<main class="mx-auto max-w-[1800px] px-3 py-3 sm:px-4 lg:px-5">
	<div class="mb-3 flex flex-wrap items-center justify-between gap-2">
		<div class="min-w-0">
			<h1 class="text-lg font-semibold leading-tight text-foreground">QA Review</h1>
			<div class="mt-1 flex flex-wrap items-center gap-1.5 text-xs">
				<Badge variant="secondary">{filteredItems.length} / {items.length} QAs</Badge>
				<Badge variant="warning">{pendingCount} pending</Badge>
				<Badge variant="success">{acceptedCount} accepted</Badge>
				<Badge variant="rejected">{rejectedCount} rejected</Badge>
			</div>
		</div>
		<div class="flex items-center gap-1.5">
			<Button size="sm" variant="outline" class="h-8 gap-1.5" onclick={loadQueue} disabled={loading} title="Refresh queue">
				<RefreshCw class="h-3.5 w-3.5 {loading ? 'animate-spin' : ''}" />
				<span class="hidden sm:inline">{loading ? "Loading" : "Refresh"}</span>
			</Button>
			<Button size="sm" variant="outline" class="h-8 w-8 p-0" onclick={() => selectRelative(-1)} disabled={filteredItems.length === 0 || activeIndex <= 0} title="Previous QA">
				<ChevronLeft class="h-4 w-4" />
			</Button>
			<span class="min-w-16 rounded-md border border-border bg-card px-2 py-1 text-center text-xs text-muted-foreground">
				{filteredItems.length > 0 ? activeIndex + 1 : 0} / {filteredItems.length}
			</span>
			<Button size="sm" variant="outline" class="h-8 w-8 p-0" onclick={() => selectRelative(1)} disabled={filteredItems.length === 0 || activeIndex >= filteredItems.length - 1} title="Next QA">
				<ChevronRight class="h-4 w-4" />
			</Button>
		</div>
	</div>

	<div class="mb-3 rounded-md border border-sky-200 bg-sky-50/70 p-2 shadow-sm">
		<div class="grid gap-2 lg:grid-cols-[auto_minmax(280px,1fr)_auto_auto] lg:items-center">
			<div class="flex items-center gap-1.5 text-xs font-semibold text-sky-800">
				<FolderOpen class="h-3.5 w-3.5" />
				Video Folder
			</div>
			<Input
				class="h-8 bg-white font-mono text-xs"
				bind:value={folderInput}
				placeholder="C:\path\to\videos"
				onkeydown={(e) => {
					if (e.key === "Enter") void applyVideoFolder();
				}}
			/>
			<Button size="sm" variant="outline" class="h-8 bg-white" onclick={() => (showFolderBrowser = true)} disabled={changingFolder}>
				Browse
			</Button>
			<Button size="sm" class="h-8" onclick={() => applyVideoFolder()} disabled={changingFolder || !folderInput.trim()}>
				{changingFolder ? "Updating" : "Update"}
			</Button>
		</div>
	</div>

	<div class="mb-3 grid gap-2 rounded-md border border-border bg-card p-2 shadow-sm lg:grid-cols-[minmax(240px,1fr)_160px_150px_auto]">
		<label class="relative min-w-0">
			<Search class="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
			<Input
				class="h-8 pl-7 text-xs"
				value={searchQuery}
				placeholder="Search question, answer, room, skill, video, or file"
				oninput={(e) => {
					searchQuery = e.currentTarget.value;
					resetActiveIndex();
				}}
			/>
		</label>
		<select
			class="h-8 rounded-md border border-input bg-background px-2 text-xs"
			bind:value={statusFilter}
			onchange={resetActiveIndex}
		>
			<option value="all">All statuses</option>
			<option value="pending">Pending</option>
			<option value="accepted">Accepted</option>
			<option value="rejected">Rejected</option>
		</select>
		<select
			class="h-8 rounded-md border border-input bg-background px-2 text-xs"
			bind:value={typeFilter}
			onchange={resetActiveIndex}
		>
			<option value="all">All types</option>
			<option value="verified">Verified</option>
			<option value="rejected">Rejected</option>
			<option value="legacy">Legacy</option>
		</select>
		{#if activeItem}
			<div class="flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
				<Filter class="h-3.5 w-3.5 shrink-0" />
				<Badge variant="secondary" class="max-w-48 truncate">{activeItem.video_filename}</Badge>
				<span class="max-w-56 truncate" title={activeItem.annotation_filename}>{activeItem.annotation_filename}</span>
			</div>
		{/if}
	</div>

	{#if error}
		<div class="rounded-md border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">{error}</div>
	{:else if loading}
		<div class="rounded-md border border-border bg-card p-8 text-center text-muted-foreground">Loading QA queue...</div>
	{:else if !activeItem || !editedAnnotation}
		<div class="rounded-md border border-border bg-card p-8 text-center text-muted-foreground">No QAs match the current filters.</div>
	{:else}
		<div class="grid items-start gap-3 xl:grid-cols-[minmax(450px,0.86fr)_minmax(560px,1.14fr)]">
			<section class="sticky top-3 space-y-3">
				<div class="rounded-md border border-border bg-card p-2 shadow-sm">
					<QAClipPanel
						{clips}
						{activeClipKey}
						onClipSelect={(key) => (activeClipKey = key)}
						onCaptionSelect={applyCaptionSelection}
					/>
				</div>
			</section>

			<section class="rounded-md border border-border bg-card p-2 shadow-sm">
				<QAAnnotationEditor
					annotation={editedAnnotation}
					{clips}
					{activeClipKey}
					{saving}
					onChange={(annotation) => (editedAnnotation = annotation)}
					onSave={saveActive}
					onClipSelect={(key) => (activeClipKey = key)}
				/>
			</section>
		</div>
	{/if}
</main>
