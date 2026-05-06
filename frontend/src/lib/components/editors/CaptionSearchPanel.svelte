<script lang="ts">
	import Button from '$lib/components/ui/button/Button.svelte';
	import Input from '$lib/components/ui/input/Input.svelte';
	import Label from '$lib/components/ui/label/Label.svelte';
	import apiClient from '$lib/api';
	import type { CaptionSearchResult, TimeSpan } from '$lib/types';

	interface SearchSelection {
		video_id: string;
		video_path?: string;
		start_time: string;
		end_time: string;
	}

	type SearchMode = 'question' | 'evidence';

	/** Why a search result is invalid in evidence mode */
	type InvalidReason = 'after_question' | 'overlaps_evidence';

	interface ClassifiedResult {
		result: CaptionSearchResult;
		valid: boolean;
		reason?: InvalidReason;
	}

	interface Props {
		onSelect: (selection: SearchSelection) => void;
		/** Search mode: 'question' shows all results, 'evidence' filters/classifies them */
		mode?: SearchMode;
		/** Question start time (MM:SS or H:MM:SS) — used in evidence mode to reject results >= this time */
		questionStartTime?: string;
		/** Existing evidence time spans — used in evidence mode to reject overlapping results */
		existingEvidenceSpans?: TimeSpan[];
	}

	let {
		onSelect,
		mode = 'question',
		questionStartTime,
		existingEvidenceSpans = []
	}: Props = $props();

	let query = $state('');
	let useRegex = $state(true);
	let useSemantic = $state(true);
	let selectedKeys = $state<string[]>([]);
	let availableKeys = $state<string[]>([]);
	let results = $state<CaptionSearchResult[]>([]);
	let total = $state(0);
	let page = $state(1);
	let perPage = 10;
	let loading = $state(false);
	let error = $state('');

	/** Parse a time string like "MM:SS" or "H:MM:SS" to total seconds */
	function parseTimeToSeconds(time: string | undefined): number {
		if (!time || !time.trim()) return -1;
		const parts = time.trim().split(':').map(Number);
		if (parts.some(isNaN)) return -1;
		if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
		if (parts.length === 2) return parts[0] * 60 + parts[1];
		return parts[0];
	}

	/** Check if two time ranges overlap. Both are [start, end] in seconds. */
	function timeRangesOverlap(
		aStart: number,
		aEnd: number,
		bStart: number,
		bEnd: number
	): boolean {
		if (aStart < 0 || aEnd < 0 || bStart < 0 || bEnd < 0) return false;
		return aStart < bEnd && bStart < aEnd;
	}

	/** Classify results in evidence mode */
	const classifiedResults = $derived.by((): ClassifiedResult[] => {
		if (mode !== 'evidence' || results.length === 0) {
			return results.map((r) => ({ result: r, valid: true }));
		}

		const qStartSec = parseTimeToSeconds(questionStartTime);
		const evidenceRanges = (existingEvidenceSpans || [])
			.map((span) => ({
				start: parseTimeToSeconds(span.start),
				end: parseTimeToSeconds(span.end)
			}))
			.filter((r) => r.start >= 0 && r.end >= 0);

		return results.map((r) => {
			const rStart = parseTimeToSeconds(r.start_time);
			const rEnd = parseTimeToSeconds(r.end_time);

			// Rule 1: result must be entirely before question start time
			if (qStartSec >= 0 && rStart >= 0 && rStart >= qStartSec) {
				return { result: r, valid: false, reason: 'after_question' as InvalidReason };
			}

			// Rule 2: result must not overlap with any existing evidence time span
			for (const ev of evidenceRanges) {
				if (timeRangesOverlap(rStart, rEnd, ev.start, ev.end)) {
					return { result: r, valid: false, reason: 'overlaps_evidence' as InvalidReason };
				}
			}

			return { result: r, valid: true };
		});
	});

	/** Valid results first, then invalid */
	const sortedResults = $derived.by((): ClassifiedResult[] => {
		const valid = classifiedResults.filter((c) => c.valid);
		const invalid = classifiedResults.filter((c) => !c.valid);
		return [...valid, ...invalid];
	});

	const validCount = $derived(classifiedResults.filter((c) => c.valid).length);
	const invalidCount = $derived(classifiedResults.filter((c) => !c.valid).length);

	$effect(() => {
		if (!query.trim()) {
			results = [];
			total = 0;
			error = '';
		}
	});

	async function runSearch(reset: boolean = true) {
		if (!query.trim()) return;
		if (reset) {
			page = 1;
			results = [];
		}
		loading = true;
		error = '';
		try {
			const res = await apiClient.searchCaptions({
				query,
				regex: useRegex,
				semantic: useSemantic,
				keys: selectedKeys,
				page,
				per_page: perPage
			});
			if (!res.success || !res.data) {
				error = res.error || 'Search failed';
				return;
			}
			availableKeys = res.data.available_keys || [];
			total = res.data.total || 0;
			results = reset ? res.data.results : [...results, ...(res.data.results || [])];
		} catch (err) {
			error = err instanceof Error ? err.message : 'Search failed';
		} finally {
			loading = false;
		}
	}

	function toggleKey(key: string) {
		if (selectedKeys.includes(key)) {
			selectedKeys = selectedKeys.filter((k) => k !== key);
		} else {
			selectedKeys = [...selectedKeys, key];
		}
	}

	function loadMore() {
		page = page + 1;
		void runSearch(false);
	}

	function selectResult(result: CaptionSearchResult) {
		onSelect({
			video_id: result.video_id,
			video_path: result.video_path || `${result.video_id}.mp4`,
			start_time: result.start_time,
			end_time: result.end_time
		});
	}

	function getReasonLabel(reason?: InvalidReason): string {
		if (reason === 'after_question') return 'After question start time';
		if (reason === 'overlaps_evidence') return 'Overlaps existing evidence';
		return '';
	}
</script>

<div class="space-y-2 border rounded-md p-3 bg-secondary/30">
	<div class="flex items-center gap-2">
		<Input
			type="text"
			bind:value={query}
			placeholder="Search captions (e.g. yellow scissors)"
			onkeydown={(e) => e.key === 'Enter' && runSearch(true)}
		/>
		<Button size="sm" onclick={() => runSearch(true)} disabled={loading || !query.trim()}>
			{loading ? 'Searching…' : 'Search'}
		</Button>
	</div>

	<div class="flex items-center gap-4 text-xs">
		<label class="flex items-center gap-1">
			<input type="checkbox" bind:checked={useRegex} />
			Regex
		</label>
		<label class="flex items-center gap-1">
			<input type="checkbox" bind:checked={useSemantic} />
			Semantic
		</label>
		<details>
			<summary class="cursor-pointer text-primary">Keys ({selectedKeys.length || 'all'})</summary>
			<div class="mt-2 grid grid-cols-2 gap-1 border rounded p-2 bg-white max-h-32 overflow-y-auto">
				{#each availableKeys as key}
					<label class="flex items-center gap-1">
						<input type="checkbox" checked={selectedKeys.includes(key)} onchange={() => toggleKey(key)} />
						{key}
					</label>
				{/each}
				{#if availableKeys.length === 0}
					<div class="text-muted-foreground">Run a search to load keys</div>
				{/if}
			</div>
		</details>
	</div>

	{#if error}
		<div class="text-xs text-destructive">{error}</div>
	{/if}

	{#if results.length > 0}
		<!-- Summary bar for evidence mode -->
		{#if mode === 'evidence' && invalidCount > 0}
			<div class="flex items-center gap-2 text-xs px-1 py-1 rounded bg-amber-50 border border-amber-200 text-amber-700">
				<svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor">
					<path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
				</svg>
				<span>{validCount} valid · {invalidCount} ineligible (shown below)</span>
			</div>
		{/if}

		<div class="space-y-2 max-h-64 overflow-y-auto pr-1">
			{#each sortedResults as { result, valid, reason }, idx}
				<!-- Separator between valid and invalid sections -->
				{#if mode === 'evidence' && !valid && idx > 0 && sortedResults[idx - 1].valid}
					<div class="separator-row flex items-center gap-2 py-1">
						<div class="flex-1 border-t border-dashed border-amber-300"></div>
						<span class="text-[10px] text-amber-500 font-medium uppercase tracking-wider whitespace-nowrap">Ineligible results</span>
						<div class="flex-1 border-t border-dashed border-amber-300"></div>
					</div>
				{/if}

				<div
					class="border rounded p-2 space-y-1 transition-opacity"
					class:bg-white={valid}
					class:result-invalid={!valid}
				>
					<div class="flex items-center justify-between gap-2">
						<div class="flex items-center gap-1.5 text-xs font-mono min-w-0">
							{#if !valid}
								<!-- Invalid reason icon + tooltip -->
								{#if reason === 'after_question'}
									<span class="invalid-icon" title={getReasonLabel(reason)}>
										<!-- Clock icon: after question  -->
										<svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5 text-orange-500 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor">
											<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.828a1 1 0 101.415-1.414L11 9.586V6z" clip-rule="evenodd" />
										</svg>
									</span>
								{:else if reason === 'overlaps_evidence'}
									<span class="invalid-icon" title={getReasonLabel(reason)}>
										<!-- Layers/overlap icon: conflicts with existing evidence -->
										<svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5 text-red-500 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor">
											<path d="M5 3a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2V5a2 2 0 00-2-2H5zM5 11a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2v-2a2 2 0 00-2-2H5zM11 5a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V5zM14 11a1 1 0 011 1v1h1a1 1 0 110 2h-1v1a1 1 0 11-2 0v-1h-1a1 1 0 110-2h1v-1a1 1 0 011-1z" />
										</svg>
									</span>
								{/if}
							{/if}
							<span class="truncate">{result.video_id} · {result.start_time} → {result.end_time}</span>
						</div>
						{#if valid}
							<Button size="sm" variant="outline" onclick={() => selectResult(result)}>Use</Button>
						{:else}
							<span class="text-[10px] text-muted-foreground whitespace-nowrap italic">{getReasonLabel(reason)}</span>
						{/if}
					</div>
					{#each result.matches.slice(0, 3) as match}
						<div class="text-xs has-tooltip">
							{#if match.mode === 'regex'}
								<span class="font-semibold text-emerald-600">Regex</span> [{match.key}] —
								<span>{@html match.snippet_html || ''}</span>
							{:else}
								<span class="font-semibold text-blue-600">Semantic</span> [{match.key}] —
								<span>{match.semantic_preview || ''}</span>
							{/if}
							<div class="full-context-tooltip">{match.full_text}</div>
						</div>
					{/each}
				</div>
			{/each}
		</div>
		{#if results.length < total}
			<div class="pt-1">
				<Button size="sm" variant="secondary" onclick={loadMore} disabled={loading}>
					{loading ? 'Loading…' : 'Load more'}
				</Button>
			</div>
		{/if}
	{:else if total === 0 && query.trim() && !loading}
		<div class="text-xs text-muted-foreground">No matches found.</div>
	{/if}
</div>

<style>
	.has-tooltip {
		position: relative;
		cursor: help;
	}
	.full-context-tooltip {
		display: none;
		position: absolute;
		z-index: 100;
		background: #1a1a1a;
		color: #fff;
		padding: 8px;
		border-radius: 6px;
		width: 300px;
		box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
		top: 100%;
		left: 0;
		font-size: 0.75rem;
		line-height: 1.35;
	}
	.has-tooltip:hover .full-context-tooltip {
		display: block;
	}
	:global(mark) {
		background: #fef08a;
		color: black;
		border-radius: 2px;
		padding: 0 2px;
		font-weight: 600;
	}

	/* De-emphasized invalid result styling */
	.result-invalid {
		background: #fafaf9;
		border-color: #e7e5e4;
		opacity: 0.55;
	}
	.result-invalid:hover {
		opacity: 0.75;
	}

	.invalid-icon {
		display: inline-flex;
		align-items: center;
		cursor: help;
	}
</style>
