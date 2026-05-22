<script lang="ts">
	import { Captions, Clock, Film, RotateCcw, Search } from "lucide-svelte";
	import Button from "$lib/components/ui/button/Button.svelte";
	import Badge from "$lib/components/ui/badge/Badge.svelte";
	import VideoControls from "./VideoControls.svelte";
	import VideoProgressBar from "./VideoProgressBar.svelte";
	import CaptionTimeline from "./CaptionTimeline.svelte";
	import CaptionSearchPanel from "$lib/components/editors/CaptionSearchPanel.svelte";
	import { apiClient } from "$lib/api";
	import { formatTimestamp, parseTimestamp } from "$lib/utils";
	import type { Caption, TimeSpan } from "$lib/types";
	import type { QAReviewClip } from "$lib/utils/qa-review";
	import { normalizeVideoFilename, videoSourceForFilename } from "$lib/utils/qa-review";

	interface SearchSelection {
		video_id: string;
		video_path?: string;
		start_time: string;
		end_time: string;
	}

	interface Props {
		clips: QAReviewClip[];
		activeClipKey: string;
		onClipSelect: (clipKey: string) => void;
		onCaptionSelect: (selection: SearchSelection) => void;
	}

	let { clips, activeClipKey, onClipSelect, onCaptionSelect }: Props = $props();

	let videoPlayer: HTMLVideoElement | undefined = $state();
	let videoDuration = $state(0);
	let videoCurrentTime = $state(0);
	let isPlaying = $state(false);
	let volumeAmplification = $state(100);
	let captionLoading = $state(false);
	let captions = $state<Caption[]>([]);
	let selectedCaptionIndex = $state(-1);

	const activeClip = $derived(clips.find((clip) => clip.key === activeClipKey) || clips[0]);
	const activeVideoSource = $derived(
		activeClip ? videoSourceForFilename(activeClip.videoFilename, activeClip.videoPath) : "",
	);
	const clipStart = $derived(parseTimestamp(activeClip?.timeSpan.start));
	const clipEnd = $derived(parseTimestamp(activeClip?.timeSpan.end));
	const overlappingCaptions = $derived.by(() => {
		if (!activeClip) return [];
		return captions
			.map((caption, index) => ({ caption, index }))
			.filter(({ caption }) => {
				const start = parseTimestamp(caption.start);
				const end = parseTimestamp(caption.end);
				return end >= clipStart && start <= clipEnd;
			});
	});
	const activeCaptionIndex = $derived.by(() => {
		const idx = captions.findIndex((caption) => {
			const start = parseTimestamp(caption.start);
			const end = parseTimestamp(caption.end);
			return videoCurrentTime >= start && videoCurrentTime <= end;
		});
		return idx;
	});

	$effect(() => {
		if (!activeClip) return;
		void loadCaptions(activeClip.videoFilename);
	});

	$effect(() => {
		if (videoPlayer && activeClip) {
			videoPlayer.currentTime = clipStart;
			videoCurrentTime = clipStart;
		}
	});

	async function loadCaptions(videoFilename: string) {
		const filename = normalizeVideoFilename(videoFilename);
		if (!filename) {
			captions = [];
			return;
		}
		captionLoading = true;
		try {
			const files = await apiClient.listCaptionFiles(filename);
			const detailed = await Promise.all(
				files.map(async (file) => {
					try {
						return await apiClient.getCaptionFile(filename, file.filename);
					} catch {
						return file;
					}
				}),
			);
			captions = detailed.flatMap((file) => file.captions || []);
		} catch {
			captions = [];
		} finally {
			captionLoading = false;
		}
	}

	function seekTo(time: number) {
		if (!videoPlayer) return;
		videoPlayer.currentTime = time;
		videoCurrentTime = time;
	}

	function replayClip() {
		if (!videoPlayer || !activeClip) return;
		videoPlayer.currentTime = clipStart;
		videoCurrentTime = clipStart;
		videoPlayer.play();
	}

	function setVolumeAmplification(value: number) {
		volumeAmplification = Math.max(0, Math.min(200, value));
		if (videoPlayer) videoPlayer.volume = Math.min(1, volumeAmplification / 100);
	}

	function handleTimeUpdate() {
		if (!videoPlayer) return;
		videoCurrentTime = videoPlayer.currentTime;
		if (activeClip && clipEnd > clipStart && videoPlayer.currentTime >= clipEnd) {
			videoPlayer.pause();
		}
	}
</script>

<div class="space-y-2 text-sm">
	<div class="flex items-center gap-2 rounded-md border border-border bg-card p-2">
		<Film class="h-4 w-4 shrink-0 text-muted-foreground" />
		<select
			class="h-8 flex-1 rounded-md border border-input bg-background px-2 text-xs text-foreground"
			value={activeClipKey}
			onchange={(e) => onClipSelect(e.currentTarget.value)}
			disabled={clips.length === 0}
		>
			{#each clips as clip}
				<option value={clip.key}>
					{clip.label} · {clip.videoFilename} · {clip.timeSpan.start || "?"}-{clip.timeSpan.end || "?"}
				</option>
			{/each}
		</select>
		<Button size="sm" variant="outline" class="h-8 w-8 border-border p-0 text-muted-foreground hover:text-foreground" onclick={replayClip} disabled={!activeClip} title="Replay clip">
			<RotateCcw class="h-3.5 w-3.5" />
		</Button>
	</div>

	<div class="overflow-hidden rounded-md border border-zinc-300 bg-zinc-950 shadow-sm">
		<div class="relative aspect-video bg-black">
			{#if activeVideoSource}
				<video
					bind:this={videoPlayer}
					src={activeVideoSource}
					preload="metadata"
					class="h-full w-full object-contain"
					onplay={() => (isPlaying = true)}
					onpause={() => (isPlaying = false)}
					onloadedmetadata={() => {
						if (videoPlayer) videoDuration = videoPlayer.duration || 0;
					}}
					ontimeupdate={handleTimeUpdate}
				>
					<track kind="captions" />
				</video>
			{:else}
				<div class="flex h-full items-center justify-center text-sm text-white/70">No clip selected</div>
			{/if}
			{#if activeClip}
				<div class="absolute left-2 top-2 flex items-center gap-1 rounded bg-black/70 px-2 py-1 font-mono text-[11px] text-white">
					<Clock class="h-3 w-3" />
					{activeClip.timeSpan.start || "?"}-{activeClip.timeSpan.end || "?"}
				</div>
			{/if}
			{#if activeCaptionIndex >= 0 && captions[activeCaptionIndex]}
				<div class="pointer-events-none absolute bottom-3 left-0 right-0 flex justify-center">
					<div class="max-w-[88%] rounded bg-black/75 px-2.5 py-1 text-center text-xs text-white">
						{captions[activeCaptionIndex].text}
					</div>
				</div>
			{/if}
		</div>
		<div class="border-t border-slate-700 bg-slate-900 px-2 py-1.5">
			<VideoProgressBar
				videoElement={videoPlayer}
				videoFilename={activeClip?.videoFilename || ""}
				duration={videoDuration}
				currentTime={videoCurrentTime}
				annotations={[]}
				onSeek={seekTo}
				tone="review"
			/>
			<VideoControls
				{isPlaying}
				{volumeAmplification}
				tone="review"
				onTogglePlay={() => {
					if (!videoPlayer) return;
					if (videoPlayer.paused) videoPlayer.play();
					else videoPlayer.pause();
				}}
				onToggleMute={() => {
					if (videoPlayer) videoPlayer.muted = !videoPlayer.muted;
				}}
				onVolumeChange={setVolumeAmplification}
				onFullscreen={() => {
					if (!videoPlayer) return;
					if (document.fullscreenElement) document.exitFullscreen();
					else videoPlayer.requestFullscreen();
				}}
			/>
		</div>
	</div>

	{#if captions.length > 0}
		<div class="rounded-md border border-border bg-card p-1.5">
			<CaptionTimeline
				duration={videoDuration}
				currentTime={videoCurrentTime}
				{captions}
				{selectedCaptionIndex}
				windowSeconds={90}
				onSeek={seekTo}
				onCaptionSelect={(index) => {
					selectedCaptionIndex = index;
					seekTo(parseTimestamp(captions[index]?.start));
				}}
			/>
		</div>
	{/if}

	<div class="rounded-md border border-amber-200 bg-amber-50/40">
		<div class="flex items-center justify-between border-b border-amber-200 px-2 py-1.5">
			<div class="flex items-center gap-1.5 text-xs font-semibold text-amber-800">
				<Captions class="h-3.5 w-3.5" />
				Captions
			</div>
			{#if activeClip}
				<Badge variant="secondary" class="font-mono text-[10px]">{formatTimestamp(clipStart)}-{formatTimestamp(clipEnd)}</Badge>
			{/if}
		</div>
		<div class="max-h-36 overflow-y-auto divide-y divide-amber-100">
			{#if captionLoading}
				<div class="p-2 text-xs text-muted-foreground">Loading captions...</div>
			{:else if overlappingCaptions.length > 0}
				{#each overlappingCaptions as item}
					<button
						type="button"
						class="block w-full px-2 py-1.5 text-left text-xs hover:bg-white"
						onclick={() => {
							selectedCaptionIndex = item.index;
							seekTo(parseTimestamp(item.caption.start));
						}}
					>
						<span class="font-mono text-[11px] text-amber-700">{item.caption.start}-{item.caption.end}</span>
						<span class="ml-2">{item.caption.text || item.caption.description?.activities || "(empty)"}</span>
					</button>
				{/each}
			{:else}
				<div class="p-2 text-xs text-muted-foreground">No overlapping captions found.</div>
			{/if}
		</div>
	</div>

	<details class="rounded-md border border-border bg-card p-2">
		<summary class="flex cursor-pointer list-none items-center gap-1.5 text-xs font-semibold text-muted-foreground">
			<Search class="h-3.5 w-3.5" />
			Caption Search
		</summary>
		<div class="mt-2">
		<CaptionSearchPanel
			mode={activeClip?.type === "evidence" ? "evidence" : "question"}
			questionStartTime={clips.find((clip) => clip.type === "question")?.timeSpan.start}
			existingEvidenceSpans={clips.filter((clip) => clip.type === "evidence").map((clip) => clip.timeSpan as TimeSpan)}
			onSelect={onCaptionSelect}
		/>
		</div>
	</details>
</div>
