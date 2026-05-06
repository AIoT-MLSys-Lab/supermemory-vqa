<script lang="ts">
    import { formatTimestamp, parseTimestamp } from "$lib/utils";
    import type { Annotation, LocationBox } from "$lib/types";
    import { REVIEW_COLOR, type ReviewStatus } from "$lib/theme";

    // Active time marker for dragging on progress bar
    interface ActiveTimeMarker {
        type: "timespan" | "timestamp";
        startTime: number; // seconds
        endTime?: number; // seconds (only for timespan)
    }

    // Props
    let {
        videoElement = $bindable<HTMLVideoElement | undefined>(),
        videoFilename = "",
        duration = 0,
        currentTime = 0,
        annotations = [] as Annotation[],
        onSeek = (_time: number) => {},
        activeTimeMarker = undefined as ActiveTimeMarker | undefined,
        onTimeMarkerUpdate = undefined as
            | ((marker: ActiveTimeMarker) => void)
            | undefined,
        onTimeMarkerDragEnd = undefined as (() => void) | undefined,
        onAnnotationSelect = undefined as
            | ((annotationIndex: number) => void)
            | undefined,
        selectedAnnotationIndex = -1 as number,
    }: {
        videoElement?: HTMLVideoElement;
        videoFilename: string;
        duration: number;
        currentTime: number;
        annotations: Annotation[];
        onSeek: (time: number) => void;
        activeTimeMarker?: ActiveTimeMarker;
        onTimeMarkerUpdate?: (marker: ActiveTimeMarker) => void;
        onTimeMarkerDragEnd?: () => void;
        onAnnotationSelect?: (annotationIndex: number) => void;
        selectedAnnotationIndex?: number;
    } = $props();

    // State
    let progressBar: HTMLDivElement | undefined = $state();
    let previewCanvas: HTMLCanvasElement | undefined = $state();
    let previewVideo: HTMLVideoElement | undefined = $state();
    let isHovering = $state(false);
    let hoverPosition = $state(0); // 0-1 percentage
    let hoverTime = $state(0); // seconds
    let previewReady = $state(false);
    let isSeeking = $state(false);
    let previewImageUrl = $state("");

    // Time marker dragging state
    type DragTarget = "start" | "end" | "span" | null;
    let dragTarget = $state<DragTarget>(null);
    let dragStartMouseX = $state(0);
    let dragOriginalStart = $state(0);
    let dragOriginalEnd = $state(0);
    let isDraggingMarker = $state(false);
    let justFinishedDragging = $state(false);

    // Computed positions for active time marker bars
    const markerStartPercent = $derived(
        activeTimeMarker && duration > 0
            ? (activeTimeMarker.startTime / duration) * 100
            : -1,
    );
    const markerEndPercent = $derived(
        activeTimeMarker?.type === "timespan" &&
            activeTimeMarker.endTime != null &&
            duration > 0
            ? (activeTimeMarker.endTime / duration) * 100
            : -1,
    );

    // Determine cursor based on hover position over active markers
    function getMarkerCursor(clientX: number): string {
        if (!activeTimeMarker || !progressBar || duration <= 0)
            return "pointer";
        const rect = progressBar.getBoundingClientRect();
        const pos = (clientX - rect.left) / rect.width;
        const hitThreshold = 8 / rect.width; // 8px hit zone

        const startPos = activeTimeMarker.startTime / duration;

        if (
            activeTimeMarker.type === "timespan" &&
            activeTimeMarker.endTime != null
        ) {
            const endPos = activeTimeMarker.endTime / duration;
            if (Math.abs(pos - startPos) < hitThreshold) return "ew-resize";
            if (Math.abs(pos - endPos) < hitThreshold) return "ew-resize";
            if (pos > startPos + hitThreshold && pos < endPos - hitThreshold)
                return "grab";
        } else {
            if (Math.abs(pos - startPos) < hitThreshold) return "ew-resize";
        }
        return "pointer";
    }

    // Determine drag target from mouse position
    function getDragTarget(clientX: number): DragTarget {
        if (!activeTimeMarker || !progressBar || duration <= 0) return null;
        const rect = progressBar.getBoundingClientRect();
        const pos = (clientX - rect.left) / rect.width;
        const hitThreshold = 8 / rect.width;

        const startPos = activeTimeMarker.startTime / duration;

        if (
            activeTimeMarker.type === "timespan" &&
            activeTimeMarker.endTime != null
        ) {
            const endPos = activeTimeMarker.endTime / duration;
            if (Math.abs(pos - startPos) < hitThreshold) return "start";
            if (Math.abs(pos - endPos) < hitThreshold) return "end";
            if (pos > startPos + hitThreshold && pos < endPos - hitThreshold)
                return "span";
        } else {
            if (Math.abs(pos - startPos) < hitThreshold) return "start";
        }
        return null;
    }

    function handleMarkerMouseDown(event: MouseEvent) {
        if (!activeTimeMarker || !progressBar || !onTimeMarkerUpdate) return;

        const target = getDragTarget(event.clientX);
        if (!target) return;

        event.preventDefault();
        event.stopPropagation();

        dragTarget = target;
        dragStartMouseX = event.clientX;
        dragOriginalStart = activeTimeMarker.startTime;
        dragOriginalEnd =
            activeTimeMarker.endTime ?? activeTimeMarker.startTime;
        isDraggingMarker = true;

        // Add global mouse handlers for dragging
        window.addEventListener("mousemove", handleMarkerDrag);
        window.addEventListener("mouseup", handleMarkerDragEnd);
    }

    function handleMarkerDrag(event: MouseEvent) {
        if (
            !isDraggingMarker ||
            !dragTarget ||
            !progressBar ||
            !activeTimeMarker ||
            !onTimeMarkerUpdate
        )
            return;

        const rect = progressBar.getBoundingClientRect();
        const deltaX = event.clientX - dragStartMouseX;
        const deltaTime = (deltaX / rect.width) * duration;

        let newStart = activeTimeMarker.startTime;
        let newEnd = activeTimeMarker.endTime;

        if (
            dragTarget === "start" &&
            activeTimeMarker.type === "timespan" &&
            newEnd != null
        ) {
            // Dragging start of a timespan - clamp to [0, endTime]
            newStart = Math.max(
                0,
                Math.min(dragOriginalStart + deltaTime, newEnd),
            );
            onSeek(newStart);
        } else if (
            dragTarget === "start" &&
            activeTimeMarker.type === "timestamp"
        ) {
            // Dragging a timestamp marker - clamp to [0, duration]
            newStart = Math.max(
                0,
                Math.min(dragOriginalStart + deltaTime, duration),
            );
            onSeek(newStart);
        } else if (dragTarget === "end" && newEnd != null) {
            newEnd = Math.max(
                newStart,
                Math.min(dragOriginalEnd + deltaTime, duration),
            );
            onSeek(newEnd);
        } else if (dragTarget === "span" && newEnd != null) {
            const spanLength = dragOriginalEnd - dragOriginalStart;
            newStart = Math.max(
                0,
                Math.min(dragOriginalStart + deltaTime, duration - spanLength),
            );
            newEnd = newStart + spanLength;
            onSeek(newStart);
        }

        onTimeMarkerUpdate({
            ...activeTimeMarker,
            startTime: newStart,
            ...(newEnd != null ? { endTime: newEnd } : {}),
        });
    }

    function handleMarkerDragEnd() {
        isDraggingMarker = false;
        dragTarget = null;
        justFinishedDragging = true;
        // Reset the flag after a short delay to allow click event to see it
        setTimeout(() => {
            justFinishedDragging = false;
        }, 10);
        window.removeEventListener("mousemove", handleMarkerDrag);
        window.removeEventListener("mouseup", handleMarkerDragEnd);
        if (onTimeMarkerDragEnd) {
            onTimeMarkerDragEnd();
        }
    }

    // Collect all timestamp markers from annotations
    const timestampMarkers = $derived.by(() => {
        const markers: {
            time: number;
            type: "annotation" | "box";
            label: string;
            annotationIndex: number;
            reviewStatus?: string;
        }[] = [];

        annotations.forEach((ann, annIndex) => {
            // Question time span start (main annotation marker)
            if (ann.question_time_span?.start) {
                const time = parseTimestamp(ann.question_time_span.start);
                markers.push({
                    time,
                    type: "annotation",
                    label: `Q${annIndex + 1}`,
                    annotationIndex: annIndex,
                    reviewStatus: ann.human_review?.status || "pending",
                });
            }

            // Bounding box timestamps
            if (ann.location?.boxes) {
                ann.location.boxes.forEach(
                    (box: LocationBox, boxIndex: number) => {
                        if (box.timestamp) {
                            const time = parseTimestamp(box.timestamp);
                            markers.push({
                                time,
                                type: "box",
                                label: `Box ${boxIndex + 1}`,
                                annotationIndex: annIndex,
                                reviewStatus:
                                    ann.human_review?.status || "pending",
                            });
                        }
                    },
                );
            }

            // Answer evidence time spans
            if (ann.answer_evidence) {
                ann.answer_evidence.forEach((ev, evIndex) => {
                    if (ev.time_spans) {
                        ev.time_spans.forEach((ts) => {
                            if (ts.start) {
                                const time = parseTimestamp(ts.start);
                                markers.push({
                                    time,
                                    type: "annotation",
                                    label: `Ev${evIndex + 1}`,
                                    annotationIndex: annIndex,
                                    reviewStatus:
                                        ann.human_review?.status || "pending",
                                });
                            }
                        });
                    }
                });
            }
        });

        // Sort by time and remove duplicates
        return markers
            .filter((m) => m.time >= 0 && m.time <= duration)
            .sort((a, b) => a.time - b.time)
            .filter((m, i, arr) => i === 0 || m.time !== arr[i - 1].time);
    });

    // Calculate progress percentage
    const progress = $derived(
        duration > 0 ? (currentTime / duration) * 100 : 0,
    );

    // Handle mousedown on progress bar (for marker dragging)
    function handleProgressMouseDown(event: MouseEvent) {
        // Check if clicking on an active time marker to initiate drag
        if (activeTimeMarker && onTimeMarkerUpdate) {
            const target = getDragTarget(event.clientX);
            if (target) {
                handleMarkerMouseDown(event);
                return;
            }
        }
    }

    // Handle click on progress bar to seek
    function handleProgressClick(event: MouseEvent) {
        // Don't seek if we just finished dragging a marker
        if (justFinishedDragging) return;

        if (!progressBar || duration <= 0) return;
        const rect = progressBar.getBoundingClientRect();
        const clickPosition = (event.clientX - rect.left) / rect.width;
        const seekTime = clickPosition * duration;

        // Smart Seek/Snap: Check if we clicked near a marker
        // Threshold: 1% of duration or 10 pixels, whichever is larger
        const pixelThreshold = 10;
        const timeThreshold = Math.max(
            duration * 0.01,
            (pixelThreshold / rect.width) * duration,
        );

        let nearestMarker: (typeof timestampMarkers)[0] | null = null;
        let minDistance = Infinity;

        for (const marker of timestampMarkers) {
            const distance = Math.abs(marker.time - seekTime);
            if (distance < timeThreshold && distance < minDistance) {
                minDistance = distance;
                nearestMarker = marker;
            }
        }

        if (nearestMarker) {
            if (onAnnotationSelect) {
                onAnnotationSelect(nearestMarker.annotationIndex);
            }
            onSeek(nearestMarker.time);
        } else {
            onSeek(Math.max(0, Math.min(seekTime, duration)));
        }
    }

    // Handle click on annotation marker
    function handleMarkerClick(
        event: MouseEvent,
        marker: { annotationIndex: number; time: number },
    ) {
        event.stopPropagation(); // Prevent progress bar click
        if (onAnnotationSelect) {
            onAnnotationSelect(marker.annotationIndex);
        }
        // Also seek to the marker time
        onSeek(marker.time);
    }

    // Get marker color based on review status
    // Get marker color based on review status
    function getMarkerColor(
        reviewStatus?: string,
        isSelected?: boolean,
    ): string {
        const status = (reviewStatus || "pending") as ReviewStatus;
        return REVIEW_COLOR[status] ?? REVIEW_COLOR.pending;
    }

    // Handle mouse move for hover preview
    function handleMouseMove(event: MouseEvent) {
        if (!progressBar || duration <= 0) return;

        // Update cursor for active time markers
        if (activeTimeMarker && onTimeMarkerUpdate && !isDraggingMarker) {
            const cursor = getMarkerCursor(event.clientX);
            progressBar.style.cursor = cursor;
        }

        const rect = progressBar.getBoundingClientRect();
        hoverPosition = (event.clientX - rect.left) / rect.width;
        hoverPosition = Math.max(0, Math.min(1, hoverPosition));
        hoverTime = hoverPosition * duration;

        // Generate preview thumbnail
        generatePreview(hoverTime);
    }

    function handleMouseEnter() {
        isHovering = true;
    }

    function handleMouseLeave() {
        isHovering = false;
        previewImageUrl = "";
    }

    // Thumbnail cache: stores data URLs keyed by time bucket (1-second intervals)
    let thumbnailCache = $state(new Map<number, string>());
    let cachedVideoSrc = $state("");
    const CACHE_BUCKET_SIZE = 1; // seconds per bucket (1 second = ~1 thumbnail per second of video)

    // Get the cache bucket key for a given time
    function getCacheBucket(time: number): number {
        return Math.floor(time / CACHE_BUCKET_SIZE);
    }

    // Clear cache when video source changes
    $effect(() => {
        if (videoElement && videoElement.src !== cachedVideoSrc) {
            thumbnailCache = new Map();
            cachedVideoSrc = videoElement.src;
        }
    });

    // Generate preview thumbnail using server cache with client-side fallback
    async function generatePreview(time: number) {
        if (!videoElement) return;

        // Check local cache first
        const bucket = getCacheBucket(time);
        const cachedUrl = thumbnailCache.get(bucket);
        if (cachedUrl) {
            previewImageUrl = cachedUrl;
            previewReady = true;
            return;
        }

        // Don't generate if already fetching/seeking
        if (isSeeking) return;
        isSeeking = true;

        try {
            // Try server cache first (if we have a filename)
            if (videoFilename) {
                try {
                    const response = await fetch(
                        `/api/videos/thumbnail/${encodeURIComponent(videoFilename)}?t=${bucket}`,
                    );
                    if (response.ok) {
                        const blob = await response.blob();
                        const url = URL.createObjectURL(blob);
                        thumbnailCache.set(bucket, url);
                        previewImageUrl = url;
                        previewReady = true;
                        return;
                    }
                } catch {
                    // Server fetch failed, fall through to client-side generation
                }
            }

            // Client-side fallback using canvas
            if (!previewVideo || !previewCanvas) {
                previewReady = false;
                return;
            }

            // Use the same source as the main video
            if (previewVideo.src !== videoElement.src) {
                previewVideo.src = videoElement.src;
                previewVideo.preload = "metadata";
            }

            // Seek to bucket center for more consistent caching
            const bucketTime =
                bucket * CACHE_BUCKET_SIZE + CACHE_BUCKET_SIZE / 2;
            previewVideo.currentTime = Math.min(
                bucketTime,
                previewVideo.duration || time,
            );

            await new Promise<void>((resolve) => {
                const handler = () => {
                    previewVideo?.removeEventListener("seeked", handler);
                    resolve();
                };
                if (previewVideo) {
                    previewVideo.addEventListener("seeked", handler);
                } else {
                    resolve();
                }
            });

            // Draw frame to canvas
            const ctx = previewCanvas.getContext("2d");
            if (ctx && previewVideo.videoWidth > 0) {
                const aspectRatio =
                    previewVideo.videoWidth / previewVideo.videoHeight;
                previewCanvas.width = 160;
                previewCanvas.height = Math.round(160 / aspectRatio);
                ctx.drawImage(
                    previewVideo,
                    0,
                    0,
                    previewCanvas.width,
                    previewCanvas.height,
                );
                const dataUrl = previewCanvas.toDataURL("image/jpeg", 0.7);

                // Store in cache
                thumbnailCache.set(bucket, dataUrl);
                previewImageUrl = dataUrl;
                previewReady = true;
            }
        } catch {
            previewReady = false;
        } finally {
            isSeeking = false;
        }
    }

    // Calculate hover tooltip position
    const tooltipLeft = $derived.by(() => {
        if (!progressBar) return "50%";
        const tooltipWidth = 170; // approximate width
        const barWidth = progressBar.offsetWidth || 400;
        const rawLeft = hoverPosition * barWidth;
        const minLeft = tooltipWidth / 2;
        const maxLeft = barWidth - tooltipWidth / 2;
        const clampedLeft = Math.max(minLeft, Math.min(maxLeft, rawLeft));
        return `${clampedLeft}px`;
    });
</script>

<div class="video-progress-container">
    <!-- Progress bar -->
    <div
        bind:this={progressBar}
        class="video-progress-bar"
        role="slider"
        tabindex="0"
        aria-label="Video progress"
        aria-valuenow={Math.round(currentTime)}
        aria-valuemin={0}
        aria-valuemax={Math.round(duration)}
        onmousedown={handleProgressMouseDown}
        onclick={handleProgressClick}
        onmousemove={handleMouseMove}
        onmouseenter={handleMouseEnter}
        onmouseleave={handleMouseLeave}
        onkeydown={(e) => {
            if (e.key === "ArrowLeft") {
                onSeek(Math.max(0, currentTime - 5));
            } else if (e.key === "ArrowRight") {
                onSeek(Math.min(duration, currentTime + 5));
            }
        }}
    >
        <!-- Background track -->
        <div class="progress-track">
            <!-- Buffered range -->
            {#if videoElement && videoElement.buffered.length > 0}
                {@const bufferedEnd = videoElement.buffered.end(
                    videoElement.buffered.length - 1,
                )}
                <div
                    class="progress-buffered"
                    style="width: {(bufferedEnd / duration) * 100}%"
                ></div>
            {/if}

            <!-- Progress fill -->
            <div class="progress-fill" style="width: {progress}%"></div>

            <!-- Current position handle -->
            <div class="progress-handle" style="left: {progress}%"></div>

            {#each timestampMarkers as marker}
                {@const markerColor = getMarkerColor(
                    marker.reviewStatus,
                    marker.annotationIndex === selectedAnnotationIndex,
                )}
                <div
                    class="progress-marker {marker.type}"
                    class:selected={marker.annotationIndex ===
                        selectedAnnotationIndex}
                    style="left: {(marker.time / duration) *
                        100}%; background-color: {markerColor}; color: {markerColor};"
                    title="{marker.label} @ {formatTimestamp(
                        marker.time,
                    )} - {marker.reviewStatus || 'pending'}"
                    onclick={(e) => handleMarkerClick(e, marker)}
                    role="button"
                    tabindex="0"
                    onkeydown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            handleMarkerClick(
                                e as unknown as MouseEvent,
                                marker,
                            );
                        }
                    }}
                ></div>
            {/each}

            <!-- Active time marker bars -->
            {#if activeTimeMarker && markerStartPercent >= 0}
                <!-- Start bar -->
                <div
                    class="active-marker-bar active-marker-start"
                    style="left: {markerStartPercent}%"
                    title="Start: {formatTimestamp(activeTimeMarker.startTime)}"
                ></div>

                {#if activeTimeMarker.type === "timespan" && markerEndPercent >= 0}
                    <!-- Span highlight between start and end -->
                    <div
                        class="active-marker-span"
                        style="left: {markerStartPercent}%; width: {markerEndPercent -
                            markerStartPercent}%"
                    ></div>
                    <!-- End bar -->
                    <div
                        class="active-marker-bar active-marker-end"
                        style="left: {markerEndPercent}%"
                        title="End: {formatTimestamp(
                            activeTimeMarker.endTime ?? 0,
                        )}"
                    ></div>
                {/if}
            {/if}
        </div>

        <!-- Hover preview tooltip -->
        {#if isHovering}
            <div class="preview-tooltip" style="left: {tooltipLeft}">
                {#if previewImageUrl}
                    <img
                        src={previewImageUrl}
                        alt="Preview at {formatTimestamp(hoverTime)}"
                        class="preview-image"
                    />
                {:else}
                    <div class="preview-placeholder">
                        <span class="preview-loading">⏳</span>
                    </div>
                {/if}
                <div class="preview-time">{formatTimestamp(hoverTime)}</div>
            </div>
            <div class="hover-line" style="left: {hoverPosition * 100}%"></div>
        {/if}
    </div>

    <!-- Time display -->
    <div class="time-display">
        <span class="current-time">{formatTimestamp(currentTime)}</span>
        <span class="time-separator">/</span>
        <span class="total-time">{formatTimestamp(duration)}</span>
    </div>

    <!-- Hidden preview video and canvas -->
    <video
        bind:this={previewVideo}
        class="hidden-preview-video"
        muted
        preload="metadata"
        crossorigin="anonymous"
    >
        <track kind="captions" />
    </video>
    <canvas bind:this={previewCanvas} class="hidden-preview-canvas"></canvas>
</div>

<style>
    .video-progress-container {
        display: flex;
        align-items: center;
        gap: 12px;
        width: 100%;
        padding: 8px 0;
    }

    .video-progress-bar {
        position: relative;
        flex: 1;
        height: 24px;
        cursor: pointer;
        display: flex;
        align-items: center;
        overflow: visible;
    }

    .progress-track {
        position: relative;
        width: 100%;
        height: 6px;
        background: hsl(var(--color-border));
        border-radius: 3px;
        overflow: visible;
    }

    .progress-track:hover {
        height: 8px;
    }

    .progress-buffered {
        position: absolute;
        top: 0;
        left: 0;
        height: 100%;
        background: hsl(var(--color-muted));
        border-radius: 3px;
    }

    .progress-fill {
        position: absolute;
        top: 0;
        left: 0;
        height: 100%;
        background: hsl(var(--foreground));
        border-radius: 3px;
        transition: width 0.1s linear;
        z-index: 1;
    }

    .progress-handle {
        position: absolute;
        top: 50%;
        width: 14px;
        height: 14px;
        background: hsl(var(--color-primary));
        border: 2px solid white;
        border-radius: 50%;
        transform: translate(-50%, -50%);
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
        opacity: 0;
        transition: opacity 0.15s;
    }

    .video-progress-bar:hover .progress-handle {
        opacity: 1;
    }

    .progress-marker {
        position: absolute;
        top: 50%;
        width: 10px; /* Increased hit target width */
        height: 14px; /* Increased hit target height */
        transform: translate(-50%, -50%);
        border-radius: 2px;
        cursor: pointer;
        z-index: 20; /* High z-index */
        transition: all 0.2s ease;
    }

    /* Shape and Icon distinctions */
    .progress-marker::after {
        content: "";
        position: absolute;
        top: 100%; /* Position below the marker */
        left: 50%;
        transform: translateX(-50%);
        margin-top: 2px;
        font-size: 10px;
        font-weight: bold;
        color: white;
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.8);
        pointer-events: none;
    }

    /* Question = Main marker, maybe a small 'Q' or dot below? 
       User said "small icons beneath". 
       Let's use a distinct shape for the marker itself, and an indicator below.
    */
    .progress-marker.question {
        border-radius: 2px; /* Rectangle */
        width: 10px;
        height: 14px;
    }

    .progress-marker.question::after {
        content: "Q";
        font-size: 10px;
        color: currentColor; /* Matches marker status color */
        font-weight: 900;
        margin-top: 2px; /* Closer to marker */
        text-shadow: 0 0 2px rgba(0, 0, 0, 0.8); /* Stroke effect for visibility */
    }

    .progress-marker.evidence {
        border-radius: 50%; /* Circle */
        width: 12px;
        height: 12px;
    }

    .progress-marker.evidence::after {
        content: "";
        width: 5px;
        height: 5px;
        background: currentColor; /* Matches marker status color */
        border-radius: 50%;
        margin-top: 2px; /* Closer to marker */
        box-shadow: 0 0 2px rgba(0, 0, 0, 0.8);
        opacity: 1;
    }

    .progress-marker.box {
        border-radius: 0;
        width: 8px;
        height: 8px;
        opacity: 0.7;
    }

    /* Box has no icon */

    .progress-marker:hover,
    .progress-marker.selected {
        z-index: 30;
        transform: translate(-50%, -50%) scale(1.2); /* Scale up instead of fixed height/width change to preserve shape */
        box-shadow:
            0 0 0 2px white,
            0 4px 8px rgba(0, 0, 0, 0.4);
    }

    .progress-marker.selected {
        /* Stronger border for selected */
        box-shadow:
            0 0 0 2px white,
            0 0 0 4px rgba(0, 0, 0, 0.5);
        z-index: 35;
    }

    .preview-tooltip {
        position: absolute;
        bottom: 32px;
        transform: translateX(-50%);
        background: rgba(0, 0, 0, 0.9);
        border-radius: 8px;
        padding: 4px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        z-index: 100;
        pointer-events: none;
    }

    .preview-image {
        display: block;
        border-radius: 4px;
        max-width: 160px;
    }

    .preview-placeholder {
        width: 160px;
        height: 90px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: hsl(var(--color-muted-foreground));
        border-radius: 4px;
    }

    .preview-loading {
        font-size: 24px;
        animation: pulse 1s infinite;
    }

    @keyframes pulse {
        0%,
        100% {
            opacity: 1;
        }
        50% {
            opacity: 0.5;
        }
    }

    .preview-time {
        text-align: center;
        padding: 4px 8px;
        color: white;
        font-size: 12px;
        font-weight: 600;
        font-variant-numeric: tabular-nums;
    }

    .hover-line {
        position: absolute;
        top: 0;
        height: 24px;
        width: 2px;
        background: rgba(255, 255, 255, 0.7);
        transform: translateX(-50%);
        pointer-events: none;
    }

    .time-display {
        font-size: 13px;
        font-weight: 600;
        font-variant-numeric: tabular-nums;
        white-space: nowrap;
        color: hsl(var(--color-foreground));
        background: hsla(0, 0%, 100%, 0.9);
        padding: 2px 8px;
        border-radius: 4px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    }

    .current-time {
        color: hsl(var(--color-primary));
        font-weight: 700;
    }

    .time-separator {
        margin: 0 4px;
        color: hsl(var(--color-muted-foreground));
    }

    .total-time {
        color: hsl(var(--color-muted-foreground));
    }

    .hidden-preview-video,
    .hidden-preview-canvas {
        position: absolute;
        width: 1px;
        height: 1px;
        opacity: 0;
        pointer-events: none;
        overflow: hidden;
    }

    .active-marker-bar {
        position: absolute;
        top: 50%;
        width: 3px;
        height: 22px;
        transform: translate(-50%, -50%);
        border-radius: 1px;
        z-index: 5;
        pointer-events: none;
    }

    .active-marker-start {
        background: hsl(142 71% 45%); /* Success green */
        box-shadow: 0 0 4px hsla(142, 71%, 45%, 0.6);
    }

    .active-marker-end {
        background: hsl(0 72% 51%); /* Primary red */
        box-shadow: 0 0 4px hsla(0, 72%, 51%, 0.6);
    }

    .active-marker-span {
        position: absolute;
        top: 0;
        height: 100%;
        background: rgba(59, 130, 246, 0.25);
        border-radius: 2px;
        z-index: 3;
        pointer-events: none;
    }
</style>
