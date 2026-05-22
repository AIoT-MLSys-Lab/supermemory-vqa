<script lang="ts">
    interface Props {
        isPlaying: boolean;
        volumeAmplification: number;
        onTogglePlay: () => void;
        onToggleMute: () => void;
        onVolumeChange: (value: number) => void;
        onFullscreen: () => void;
        tone?: "default" | "review";
    }

    let {
        isPlaying,
        volumeAmplification,
        onTogglePlay,
        onToggleMute,
        onVolumeChange,
        onFullscreen,
        tone = "default",
    }: Props = $props();

    const isReviewTone = $derived(tone === "review");
</script>

<div class="mt-2 flex items-center gap-3 {isReviewTone ? 'rounded-md bg-slate-900 px-3 py-2 text-slate-100' : ''}">
    <!-- Play/Pause button -->
    <button
        type="button"
        class="{isReviewTone ? 'text-slate-100 hover:text-sky-300' : 'text-foreground hover:text-primary'} transition-colors p-1"
        onclick={onTogglePlay}
        aria-label={isPlaying ? "Pause" : "Play"}
    >
        {#if isPlaying}
            <svg
                xmlns="http://www.w3.org/2000/svg"
                class="h-6 w-6"
                fill="currentColor"
                viewBox="0 0 24 24"
            >
                <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" />
            </svg>
        {:else}
            <svg
                xmlns="http://www.w3.org/2000/svg"
                class="h-6 w-6"
                fill="currentColor"
                viewBox="0 0 24 24"
            >
                <path d="M8 5v14l11-7z" />
            </svg>
        {/if}
    </button>

    <!-- Volume control -->
    <div class="flex items-center gap-2">
        <button
            type="button"
            class="{isReviewTone ? 'text-slate-100 hover:text-sky-300' : 'text-foreground hover:text-primary'} transition-colors p-1"
            onclick={onToggleMute}
            aria-label="Toggle mute"
        >
            <svg
                xmlns="http://www.w3.org/2000/svg"
                class="h-5 w-5"
                fill="currentColor"
                viewBox="0 0 24 24"
            >
                <path
                    d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02z"
                />
            </svg>
        </button>
        <input
            type="range"
            min="0"
            max="200"
            value={volumeAmplification}
            oninput={(e) => onVolumeChange(parseInt(e.currentTarget.value))}
            class="h-1 w-20 cursor-pointer appearance-none rounded-lg {isReviewTone ? 'bg-slate-700 accent-sky-400' : 'bg-muted'}"
        />
        <span class="w-10 text-xs {isReviewTone ? 'text-slate-300' : 'text-muted-foreground'}">{volumeAmplification}%</span>
    </div>

    <div class="flex-1"></div>

    <!-- Fullscreen button -->
    <button
        type="button"
        class="{isReviewTone ? 'text-slate-100 hover:text-sky-300' : 'text-foreground hover:text-primary'} transition-colors p-1"
        onclick={onFullscreen}
        aria-label="Toggle fullscreen"
    >
        <svg
            xmlns="http://www.w3.org/2000/svg"
            class="h-5 w-5"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            viewBox="0 0 24 24"
        >
            <path
                d="M8 3H5a2 2 0 00-2 2v3m18 0V5a2 2 0 00-2-2h-3m0 18h3a2 2 0 002-2v-3M3 16v3a2 2 0 002 2h3"
            />
        </svg>
    </button>
</div>
