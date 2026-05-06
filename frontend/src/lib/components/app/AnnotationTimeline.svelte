<script lang="ts">
    import { formatTimestamp, parseTimestamp } from "$lib/utils";
    import type { Annotation, LocationBox } from "$lib/types";

    let {
        duration = 0,
        currentTime = 0,
        annotations = [] as Annotation[],
        selectedAnnotationIndex = -1,
        windowSeconds = 180,
        onSeek = (_time: number) => {},
        onAnnotationSelect = undefined as ((index: number) => void) | undefined,
        onContextMenu = undefined as
            | ((
                  e: MouseEvent,
                  time: number,
                  annotation?: Annotation,
                  evidenceIndex?: number,
              ) => void)
            | undefined,
        onTimespanDragStart = undefined as
            | ((
                  type: "question" | "evidence",
                  annotationIndex: number,
                  evidenceIndex?: number,
                  spanIndex?: number,
                  edge?: "start" | "end",
              ) => void)
            | undefined,
        onTimespanDrag = undefined as ((newTime: number) => void) | undefined,
        onTimespanDragEnd = undefined as (() => void) | undefined,
        onBoxClick = undefined as
            | ((
                  box: LocationBox,
                  boxIndex: number,
                  annotationIndex: number,
                  evidenceIndex?: number,
              ) => void)
            | undefined,
        onBoxTimestampDragEnd = undefined as
            | ((
                  annotationIndex: number,
                  boxIndex: number,
                  newTime: number,
                  evidenceIndex?: number,
              ) => void)
            | undefined,
    }: {
        duration: number;
        currentTime: number;
        annotations: Annotation[];
        selectedAnnotationIndex?: number;
        windowSeconds?: number;
        onSeek: (time: number) => void;
        onAnnotationSelect?: (index: number) => void;
        onContextMenu?: (
            e: MouseEvent,
            time: number,
            annotation?: Annotation,
            evidenceIndex?: number,
        ) => void;
        onTimespanDragStart?: (
            type: "question" | "evidence",
            annotationIndex: number,
            evidenceIndex?: number,
            spanIndex?: number,
            edge?: "start" | "end",
        ) => void;
        onTimespanDrag?: (newTime: number) => void;
        onTimespanDragEnd?: () => void;
        onBoxClick?: (
            box: LocationBox,
            boxIndex: number,
            annotationIndex: number,
            evidenceIndex?: number,
        ) => void;
        onBoxTimestampDragEnd?: (
            annotationIndex: number,
            boxIndex: number,
            newTime: number,
            evidenceIndex?: number,
        ) => void;
    } = $props();

    let timelineBar: HTMLDivElement | undefined = $state();
    let isDragging = $state(false);
    let dragType = $state<"question" | "evidence" | null>(null);

    // Box marker drag state
    let isDraggingBoxMarker = $state(false);
    let draggingBoxInfo = $state<{
        annotationIndex: number;
        boxIndex: number;
        evidenceIndex?: number;
    } | null>(null);

    // Window: show ±windowSeconds around current time
    const windowStart = $derived(Math.max(0, currentTime - windowSeconds));
    const windowEnd = $derived(Math.min(duration, currentTime + windowSeconds));
    const windowDuration = $derived(windowEnd - windowStart);

    // Extract all timespans from annotations for display
    const timelineItems = $derived.by(() => {
        const items: Array<{
            type: "question" | "evidence";
            annotationIndex: number;
            evidenceIndex?: number;
            spanIndex?: number;
            startSec: number;
            endSec: number;
            annotation: Annotation;
            label: string;
            color: string;
        }> = [];

        annotations.forEach((ann, annIdx) => {
            // Question timespan
            if (ann.question_time_span) {
                const start = parseTimestamp(
                    ann.question_time_span.start || "0:00",
                );
                const end = parseTimestamp(
                    ann.question_time_span.end || "0:00",
                );
                if (start < windowEnd && end > windowStart) {
                    items.push({
                        type: "question",
                        annotationIndex: annIdx,
                        startSec: start,
                        endSec: end,
                        annotation: ann,
                        label: `Q${annIdx + 1}`,
                        color:
                            annIdx === selectedAnnotationIndex
                                ? "#3b82f6"
                                : "#60a5fa",
                    });
                }
            }

            // Evidence timespans
            if (ann.answer_evidence) {
                ann.answer_evidence.forEach((ev, evIdx) => {
                    const timespans = ev.time_spans || [];
                    timespans.forEach((span, spanIdx) => {
                        const start = parseTimestamp(span.start || "0:00");
                        const end = parseTimestamp(span.end || "0:00");
                        if (start < windowEnd && end > windowStart) {
                            items.push({
                                type: "evidence",
                                annotationIndex: annIdx,
                                evidenceIndex: evIdx,
                                spanIndex: spanIdx,
                                startSec: start,
                                endSec: end,
                                annotation: ann,
                                label: `A${annIdx + 1}.${evIdx + 1}`,
                                color:
                                    annIdx === selectedAnnotationIndex
                                        ? "#10b981"
                                        : "#34d399",
                            });
                        }
                    });
                });
            }
        });

        return items;
    });

    // Extract bounding box timestamp markers
    const boxMarkers = $derived.by(() => {
        const markers: Array<{
            annotationIndex: number;
            boxIndex: number;
            evidenceIndex?: number;
            timeSec: number;
            label: string;
            color: string;
            box: LocationBox;
        }> = [];

        annotations.forEach((ann, annIdx) => {
            // Question-level bounding boxes
            const qBoxes = ann.location?.boxes || [];
            qBoxes.forEach((box: LocationBox, bIdx: number) => {
                if (box.timestamp) {
                    const t = parseTimestamp(box.timestamp);
                    if (t >= windowStart && t <= windowEnd) {
                        markers.push({
                            annotationIndex: annIdx,
                            boxIndex: bIdx,
                            timeSec: t,
                            label: `B${bIdx + 1}`,
                            color:
                                annIdx === selectedAnnotationIndex
                                    ? "#f97316"
                                    : "#fb923c",
                            box,
                        });
                    }
                }
            });

            // Evidence-level bounding boxes
            if (ann.answer_evidence) {
                ann.answer_evidence.forEach((ev, evIdx) => {
                    const evBoxes = ev.bounding_boxes || [];
                    evBoxes.forEach((box: any, bIdx: number) => {
                        const ts = box.timestamp || box.time_offset;
                        if (ts) {
                            const t = parseTimestamp(ts);
                            if (t >= windowStart && t <= windowEnd) {
                                markers.push({
                                    annotationIndex: annIdx,
                                    boxIndex: bIdx,
                                    evidenceIndex: evIdx,
                                    timeSec: t,
                                    label: `B${evIdx + 1}.${bIdx + 1}`,
                                    color:
                                        annIdx === selectedAnnotationIndex
                                            ? "#a855f7"
                                            : "#c084fc",
                                    box: {
                                        box_2d: box.box_2d || [
                                            box.ymin,
                                            box.xmin,
                                            box.ymax,
                                            box.xmax,
                                        ],
                                        timestamp: ts,
                                        description:
                                            box.label || box.description,
                                    },
                                });
                            }
                        }
                    });
                });
            }
        });

        return markers;
    });

    function timeToPercent(time: number): number {
        if (windowDuration <= 0) return 0;
        return ((time - windowStart) / windowDuration) * 100;
    }

    const playheadPercent = $derived(timeToPercent(currentTime));

    function percentToTime(percent: number): number {
        return windowStart + (percent / 100) * windowDuration;
    }

    function handleClick(event: MouseEvent) {
        if (!timelineBar || windowDuration <= 0 || isDragging) return;
        const rect = timelineBar.getBoundingClientRect();
        const pct = (event.clientX - rect.left) / rect.width;
        const time = percentToTime(pct * 100);
        onSeek(Math.max(0, Math.min(duration, time)));
    }

    function handleRightClick(event: MouseEvent) {
        if (!timelineBar || !onContextMenu) return;
        event.preventDefault();
        const rect = timelineBar.getBoundingClientRect();
        const pct = (event.clientX - rect.left) / rect.width;
        const time = percentToTime(pct * 100);
        onContextMenu(event, Math.max(0, Math.min(duration, time)));
    }

    function handleItemClick(
        event: MouseEvent,
        item: (typeof timelineItems)[0],
    ) {
        event.stopPropagation();
        if (onAnnotationSelect) onAnnotationSelect(item.annotationIndex);
        onSeek(item.startSec);
    }

    function handleItemRightClick(
        event: MouseEvent,
        item: (typeof timelineItems)[0],
    ) {
        event.preventDefault();
        event.stopPropagation();
        if (onContextMenu) {
            onContextMenu(
                event,
                item.startSec,
                item.annotation,
                item.evidenceIndex,
            );
        }
    }

    function handleEdgeDragStart(
        event: MouseEvent,
        item: (typeof timelineItems)[0],
        edge: "start" | "end",
    ) {
        event.stopPropagation();
        if (!onTimespanDragStart) return;
        isDragging = true;
        dragType = item.type;
        onTimespanDragStart(
            item.type,
            item.annotationIndex,
            item.evidenceIndex,
            item.spanIndex,
            edge,
        );

        // Add global event listeners
        document.addEventListener("mousemove", handleDrag);
        document.addEventListener("mouseup", handleDragEnd);
    }

    function handleDrag(event: MouseEvent) {
        if (!isDragging || !timelineBar || !onTimespanDrag) return;
        const rect = timelineBar.getBoundingClientRect();
        const pct = Math.max(
            0,
            Math.min(100, ((event.clientX - rect.left) / rect.width) * 100),
        );
        const time = percentToTime(pct);
        onTimespanDrag(Math.max(0, Math.min(duration, time)));
    }

    function handleDragEnd() {
        if (isDragging && onTimespanDragEnd) {
            onTimespanDragEnd();
        }
        isDragging = false;
        dragType = null;
        document.removeEventListener("mousemove", handleDrag);
        document.removeEventListener("mouseup", handleDragEnd);
    }

    // Box marker drag handlers
    function handleBoxMarkerDragStart(
        event: MouseEvent,
        marker: (typeof boxMarkers)[0],
    ) {
        event.stopPropagation();
        event.preventDefault();
        isDraggingBoxMarker = true;
        draggingBoxInfo = {
            annotationIndex: marker.annotationIndex,
            boxIndex: marker.boxIndex,
            evidenceIndex: marker.evidenceIndex,
        };
        if (onAnnotationSelect) onAnnotationSelect(marker.annotationIndex);
        document.addEventListener("mousemove", handleBoxMarkerDrag);
        document.addEventListener("mouseup", handleBoxMarkerDragEnd);
    }

    function handleBoxMarkerDrag(event: MouseEvent) {
        if (!isDraggingBoxMarker || !timelineBar) return;
        const rect = timelineBar.getBoundingClientRect();
        const pct = Math.max(
            0,
            Math.min(100, ((event.clientX - rect.left) / rect.width) * 100),
        );
        const time = percentToTime(pct);
        onSeek(Math.max(0, Math.min(duration, time)));
    }

    function handleBoxMarkerDragEnd() {
        if (isDraggingBoxMarker && draggingBoxInfo && onBoxTimestampDragEnd) {
            // Get the current time from the timeline position
            const currentSeekTime = Math.max(
                0,
                Math.min(duration, percentToTime(playheadPercent)),
            );
            onBoxTimestampDragEnd(
                draggingBoxInfo.annotationIndex,
                draggingBoxInfo.boxIndex,
                currentSeekTime,
                draggingBoxInfo.evidenceIndex,
            );
        }
        isDraggingBoxMarker = false;
        draggingBoxInfo = null;
        document.removeEventListener("mousemove", handleBoxMarkerDrag);
        document.removeEventListener("mouseup", handleBoxMarkerDragEnd);
    }

    function handleBoxMarkerClick(
        event: MouseEvent,
        marker: (typeof boxMarkers)[0],
    ) {
        event.stopPropagation();
        if (onAnnotationSelect) onAnnotationSelect(marker.annotationIndex);
        onSeek(marker.timeSec);
        if (onBoxClick)
            onBoxClick(
                marker.box,
                marker.boxIndex,
                marker.annotationIndex,
                marker.evidenceIndex,
            );
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

<div class="annotation-timeline-container">
    <div class="timeline-label">
        <span class="text-xs font-medium text-muted-foreground"
            >Timeline (±{Math.round(windowSeconds / 60)}min)</span
        >
        <span class="text-xs text-muted-foreground"
            >{annotations.length} annotations</span
        >
    </div>
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <div
        bind:this={timelineBar}
        class="timeline-bar"
        role="slider"
        tabindex="0"
        aria-label="Annotation timeline"
        aria-valuenow={Math.round(currentTime)}
        aria-valuemin={Math.round(windowStart)}
        aria-valuemax={Math.round(windowEnd)}
        onclick={handleClick}
        oncontextmenu={handleRightClick}
        onkeydown={(e) => {
            if (e.key === "ArrowLeft") onSeek(Math.max(0, currentTime - 5));
            else if (e.key === "ArrowRight")
                onSeek(Math.min(duration, currentTime + 5));
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

            <!-- Question and Evidence blocks -->
            {#each timelineItems as item}
                {@const leftPct = Math.max(0, timeToPercent(item.startSec))}
                {@const rightPct = Math.min(100, timeToPercent(item.endSec))}
                {@const widthPct = rightPct - leftPct}
                {@const isSelected =
                    item.annotationIndex === selectedAnnotationIndex}
                <!-- svelte-ignore a11y_click_events_have_key_events -->
                <div
                    class="timeline-item"
                    class:selected={isSelected}
                    class:question={item.type === "question"}
                    class:evidence={item.type === "evidence"}
                    style="left: {leftPct}%; width: {widthPct}%; background-color: {item.color}40; border-color: {item.color};"
                    title="{item.label} ({formatTimestamp(
                        item.startSec,
                    )} - {formatTimestamp(item.endSec)})"
                    onclick={(e) => handleItemClick(e, item)}
                    oncontextmenu={(e) => handleItemRightClick(e, item)}
                    role="button"
                    tabindex="0"
                >
                    <!-- Resize handles for edges -->
                    {#if onTimespanDragStart}
                        <!-- svelte-ignore a11y_no_static_element_interactions -->
                        <div
                            class="resize-handle left"
                            onmousedown={(e) =>
                                handleEdgeDragStart(e, item, "start")}
                        ></div>
                        <!-- svelte-ignore a11y_no_static_element_interactions -->
                        <div
                            class="resize-handle right"
                            onmousedown={(e) =>
                                handleEdgeDragStart(e, item, "end")}
                        ></div>
                    {/if}
                    <span class="timeline-item-text">{item.label}</span>
                </div>
            {/each}

            <!-- Bounding box timestamp markers -->
            {#each boxMarkers as marker}
                {@const markerPct = timeToPercent(marker.timeSec)}
                {#if markerPct >= 0 && markerPct <= 100}
                    <!-- svelte-ignore a11y_no_static_element_interactions -->
                    <div
                        class="box-marker"
                        class:selected={marker.annotationIndex ===
                            selectedAnnotationIndex}
                        style="left: {markerPct}%; border-color: {marker.color}; background-color: {marker.color};"
                        title="{marker.label} @ {formatTimestamp(
                            marker.timeSec,
                        )}"
                        onclick={(e) => handleBoxMarkerClick(e, marker)}
                        onmousedown={(e) => handleBoxMarkerDragStart(e, marker)}
                        role="button"
                        tabindex="0"
                    >
                        <span class="box-marker-label">{marker.label}</span>
                    </div>
                {/if}
            {/each}

            <!-- Playhead -->
            <div
                class="timeline-playhead"
                style="left: {playheadPercent}%"
            ></div>
        </div>
    </div>
</div>

<style>
    .annotation-timeline-container {
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
        height: 80px;
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
        left: 2px;
        font-size: 9px;
        color: hsl(240 4% 46%);
        font-weight: 500;
        white-space: nowrap;
        pointer-events: none;
    }

    .timeline-item {
        position: absolute;
        top: 0;
        height: 50%;
        border: 2px solid;
        border-radius: 4px;
        cursor: pointer;
        transition: all 0.15s;
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 2;
        min-width: 4px;
    }

    .timeline-item.question {
        top: 5%;
        height: 40%;
    }

    .timeline-item.evidence {
        top: 55%;
        height: 40%;
    }

    .timeline-item.selected {
        border-width: 3px;
        z-index: 3;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
    }

    .timeline-item:hover {
        transform: scaleY(1.1);
        z-index: 4;
        box-shadow: 0 2px 12px rgba(0, 0, 0, 0.2);
    }

    .timeline-item-text {
        font-size: 10px;
        font-weight: 600;
        color: white;
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        padding: 0 4px;
    }

    .resize-handle {
        position: absolute;
        top: 0;
        bottom: 0;
        width: 8px;
        cursor: ew-resize;
        z-index: 10;
    }

    .resize-handle.left {
        left: -4px;
        background: linear-gradient(
            to right,
            rgba(255, 255, 255, 0.3),
            transparent
        );
    }

    .resize-handle.right {
        right: -4px;
        background: linear-gradient(
            to left,
            rgba(255, 255, 255, 0.3),
            transparent
        );
    }

    .resize-handle:hover {
        background: rgba(255, 255, 255, 0.5);
    }

    .box-marker {
        position: absolute;
        top: 0;
        bottom: 0;
        width: 3px;
        border-left: 1px dashed;
        cursor: ew-resize;
        z-index: 4;
        transition:
            width 0.1s,
            opacity 0.15s;
        opacity: 0.7;
    }

    .box-marker:hover,
    .box-marker.selected {
        width: 5px;
        opacity: 1;
    }

    .box-marker-label {
        position: absolute;
        top: -14px;
        left: 50%;
        transform: translateX(-50%);
        font-size: 8px;
        font-weight: 700;
        color: inherit;
        white-space: nowrap;
        pointer-events: none;
    }

    .timeline-playhead {
        position: absolute;
        top: 0;
        bottom: 0;
        width: 2px;
        background: red;
        z-index: 5;
        pointer-events: none;
    }

    .timeline-playhead::before {
        content: "";
        position: absolute;
        top: -4px;
        left: -4px;
        width: 0;
        height: 0;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 8px solid red;
    }
</style>
