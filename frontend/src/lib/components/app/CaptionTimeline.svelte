<script lang="ts">
    import { formatTimestamp, parseTimestamp } from "$lib/utils";
    import type { Caption } from "$lib/types";
    import { CONFIDENCE_COLOR, CONFIDENCE_COLOR_DEFAULT, type ConfidenceLevel } from "$lib/theme";

    let {
        duration = 0,
        currentTime = 0,
        captions = [] as Caption[],
        selectedCaptionIndex = -1,
        windowSeconds = 180,
        onSeek = (_time: number) => {},
        onCaptionSelect = undefined as ((index: number) => void) | undefined,
        onContextMenu = undefined as ((e: MouseEvent, time: number) => void) | undefined,
    }: {
        duration: number;
        currentTime: number;
        captions: Caption[];
        selectedCaptionIndex?: number;
        windowSeconds?: number;
        onSeek: (time: number) => void;
        onCaptionSelect?: (index: number) => void;
        onContextMenu?: (e: MouseEvent, time: number) => void;
    } = $props();

    let timelineBar: HTMLDivElement | undefined = $state();

    // Window: show ±windowSeconds around current time
    const windowStart = $derived(Math.max(0, currentTime - windowSeconds));
    const windowEnd = $derived(Math.min(duration, currentTime + windowSeconds));
    const windowDuration = $derived(windowEnd - windowStart);

    // Visible captions: those overlapping the window
    const visibleCaptions = $derived.by(() => {
        return captions
            .map((cap, idx) => {
                const start = parseTimestamp(cap.start);
                const end = parseTimestamp(cap.end);
                return { ...cap, startSec: start, endSec: end, originalIndex: idx };
            })
            .filter(c => c.endSec > windowStart && c.startSec < windowEnd);
    });

    function timeToPercent(time: number): number {
        if (windowDuration <= 0) return 0;
        return ((time - windowStart) / windowDuration) * 100;
    }

    const playheadPercent = $derived(timeToPercent(currentTime));

    function handleClick(event: MouseEvent) {
        if (!timelineBar || windowDuration <= 0) return;
        const rect = timelineBar.getBoundingClientRect();
        const pct = (event.clientX - rect.left) / rect.width;
        const time = windowStart + pct * windowDuration;
        onSeek(Math.max(0, Math.min(duration, time)));
    }

    function handleRightClick(event: MouseEvent) {
        if (!timelineBar || !onContextMenu) return;
        event.preventDefault();
        const rect = timelineBar.getBoundingClientRect();
        const pct = (event.clientX - rect.left) / rect.width;
        const time = windowStart + pct * windowDuration;
        onContextMenu(event, Math.max(0, Math.min(duration, time)));
    }

    function handleCaptionClick(event: MouseEvent, index: number, startSec: number) {
        event.stopPropagation();
        if (onCaptionSelect) onCaptionSelect(index);
        onSeek(startSec);
    }

    // Tick marks every 30 seconds within the window
    const tickMarks = $derived.by(() => {
        const marks: { time: number; label: string }[] = [];
        const interval = 30;
        const start = Math.ceil(windowStart / interval) * interval;
        for (let t = start; t <= windowEnd; t += interval) {
            marks.push({ time: t, label: formatTimestamp(t) });
        }
        return marks;
    });
</script>

<div class="caption-timeline-container">
    <div class="timeline-label">
        <span class="text-xs font-medium text-muted-foreground">Timeline (±{Math.round(windowSeconds / 60)}min)</span>
    </div>
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <div
        bind:this={timelineBar}
        class="timeline-bar"
        role="slider"
        tabindex="0"
        aria-label="Caption timeline"
        aria-valuenow={Math.round(currentTime)}
        aria-valuemin={Math.round(windowStart)}
        aria-valuemax={Math.round(windowEnd)}
        onclick={handleClick}
        oncontextmenu={handleRightClick}
        onkeydown={(e) => {
            if (e.key === 'ArrowLeft') onSeek(Math.max(0, currentTime - 5));
            else if (e.key === 'ArrowRight') onSeek(Math.min(duration, currentTime + 5));
        }}
    >
        <!-- Background track -->
        <div class="timeline-track">
            <!-- Tick marks -->
            {#each tickMarks as tick}
                <div
                    class="tick-mark"
                    style="left: {timeToPercent(tick.time)}%"
                >
                    <div class="tick-line"></div>
                    <span class="tick-label">{tick.label}</span>
                </div>
            {/each}

            <!-- Caption blocks -->
            {#each visibleCaptions as cap}
                {@const leftPct = Math.max(0, timeToPercent(cap.startSec))}
                {@const rightPct = Math.min(100, timeToPercent(cap.endSec))}
                {@const widthPct = rightPct - leftPct}
                {@const isSelected = cap.originalIndex === selectedCaptionIndex}
                {@const confColor = CONFIDENCE_COLOR[(cap.confidence ?? 'medium') as ConfidenceLevel] ?? CONFIDENCE_COLOR_DEFAULT}
                <!-- svelte-ignore a11y_click_events_have_key_events -->
                <div
                    class="caption-block"
                    class:selected={isSelected}
                    style="left: {leftPct}%; width: {widthPct}%; background-color: {confColor}20; border-color: {confColor};"
                    title="#{cap.originalIndex + 1} ({cap.start} - {cap.end}) [confidence: {cap.confidence ?? 'medium'}]"
                    onclick={(e) => handleCaptionClick(e, cap.originalIndex, cap.startSec)}
                    role="button"
                    tabindex="0"
                >
                    <span class="caption-block-text">#{cap.originalIndex + 1}</span>
                </div>
            {/each}

            <!-- Playhead -->
            <div class="timeline-playhead" style="left: {playheadPercent}%"></div>
        </div>
    </div>
</div>

<style>
    .caption-timeline-container {
        display: flex;
        flex-direction: column;
        gap: 4px;
        width: 100%;
        padding: 4px 0;
    }

    .timeline-label {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0 4px;
    }

    .timeline-bar {
        position: relative;
        width: 100%;
        height: 72px;
        cursor: pointer;
        overflow: visible;
    }

    .timeline-track {
        position: relative;
        width: 100%;
        height: 100%;
        background: hsl(240 5% 96%);
        border: 1px solid hsl(240 6% 90%);
        border-radius: 6px;
        overflow: hidden;
    }

    .tick-mark {
        position: absolute;
        top: 0;
        height: 100%;
        z-index: 1;
        pointer-events: none;
    }

    .tick-line {
        position: absolute;
        top: 0;
        left: 0;
        width: 1px;
        height: 100%;
        background: hsl(240 6% 85%);
    }

    .tick-label {
        position: absolute;
        bottom: 2px;
        left: 4px;
        font-size: 9px;
        color: hsl(240 4% 46%);
        font-variant-numeric: tabular-nums;
        white-space: nowrap;
    }

    .caption-block {
        position: absolute;
        top: 4px;
        height: calc(100% - 20px);
        border: 1.5px solid;
        border-radius: 4px;
        padding: 2px 4px;
        overflow: hidden;
        cursor: pointer;
        z-index: 2;
        transition: all 0.15s ease;
        display: flex;
        align-items: flex-start;
    }

    .caption-block:hover {
        z-index: 10;
        filter: brightness(0.95);
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    }

    .caption-block.selected {
        z-index: 15;
        box-shadow: 0 0 0 2px white, 0 0 0 4px rgba(0,0,0,0.3);
    }

    .caption-block-text {
        font-size: 10px;
        line-height: 1.2;
        color: hsl(240 10% 10%);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        max-width: 100%;
    }

    .timeline-playhead {
        position: absolute;
        top: 0;
        height: 100%;
        width: 2px;
        background: hsl(0 72% 51%);
        z-index: 20;
        transform: translateX(-50%);
        box-shadow: 0 0 4px hsla(0, 72%, 51%, 0.5);
        pointer-events: none;
    }
</style>
