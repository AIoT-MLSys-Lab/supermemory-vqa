<script lang="ts">
    import AnnotationItem from "./AnnotationItem.svelte";
    import type { Annotation, LocationBox } from "$lib/types";

    interface Props {
        annotations: Annotation[];
        activeAnnotationIndex: number;
        annotationsLoading: boolean;
        boxDrawMode: boolean;
        activeVideoSource: string;
        annotationSourceFiles: string[];
        currentVideoPath: string;
        collapsed: boolean;
        onNavigateNext: () => void;
        onNavigatePrevious: () => void;
        onSeek: (ts: string, videoPath?: string) => void;
        onShowBox: (
            box: LocationBox,
            boxIndex: number,
            annotationIndex: number,
            evidenceIndex?: number,
        ) => void;
        onEdit: (index: number) => void;
        onReview: (index: number) => void;
        onDelete: (index: number) => void;
        onSelect: (index: number) => void;
        onQuickAdd: (index: number) => void;
        onToggleCollapse: () => void;
    }

    let {
        annotations,
        activeAnnotationIndex,
        annotationsLoading,
        boxDrawMode,
        activeVideoSource,
        annotationSourceFiles,
        currentVideoPath,
        collapsed,
        onNavigateNext,
        onNavigatePrevious,
        onSeek,
        onShowBox,
        onEdit,
        onReview,
        onDelete,
        onSelect,
        onQuickAdd,
        onToggleCollapse,
    }: Props = $props();
</script>

<!-- Expand Panel Button (shown when collapsed) -->
{#if collapsed}
    <div class="flex justify-center">
        <button
            type="button"
            class="px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors shadow-md flex items-center gap-2"
            onclick={onToggleCollapse}
            title="Expand annotations panel"
            aria-label="Expand annotations panel"
        >
            <span>Show Annotations ({annotations.length})</span>
            <svg
                xmlns="http://www.w3.org/2000/svg"
                class="h-4 w-4"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                viewBox="0 0 24 24"
            >
                <path d="M19 9l-7 7-7-7" />
            </svg>
        </button>
    </div>
{/if}

<!-- Annotations Panel -->
<div
    class="border rounded-lg bg-card overflow-hidden flex flex-col relative"
    style="max-height: calc(100vh - 250px);"
    class:hidden={collapsed}
>
    <!-- Sticky Header with Navigation -->
    <div
        class="sticky top-0 z-20 bg-card border-b px-3 py-2 flex items-center justify-between shadow-sm shrink-0"
    >
        <div class="flex items-center gap-2">
            <span class="text-sm font-semibold text-foreground">
                Annotations ({annotations.length})
            </span>
            <span class="text-xs text-muted-foreground mr-1">
                {activeAnnotationIndex >= 0
                    ? `${activeAnnotationIndex + 1} / ${annotations.length}`
                    : ""}
            </span>
        </div>

        <div class="flex items-center gap-1">
            <button
                type="button"
                class="p-1.5 rounded hover:bg-secondary transition-colors disabled:opacity-30 disabled:cursor-not-allowed text-foreground"
                onclick={onNavigatePrevious}
                disabled={annotations.length === 0}
                title="Previous annotation (Ctrl+[)"
                aria-label="Previous annotation"
            >
                <svg
                    xmlns="http://www.w3.org/2000/svg"
                    class="h-4 w-4"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    viewBox="0 0 24 24"
                >
                    <path d="M15 18l-6-6 6-6" />
                </svg>
            </button>
            <button
                type="button"
                class="p-1.5 rounded hover:bg-secondary transition-colors disabled:opacity-30 disabled:cursor-not-allowed text-foreground"
                onclick={onNavigateNext}
                disabled={annotations.length === 0}
                title="Next annotation (Ctrl+])"
                aria-label="Next annotation"
            >
                <svg
                    xmlns="http://www.w3.org/2000/svg"
                    class="h-4 w-4"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    viewBox="0 0 24 24"
                >
                    <path d="M9 18l6-6-6-6" />
                </svg>
            </button>
            <div class="w-px h-4 bg-border mx-1"></div>
            <button
                type="button"
                class="p-1.5 rounded hover:bg-secondary transition-colors text-foreground"
                onclick={onToggleCollapse}
                title="Collapse panel"
                aria-label="Collapse panel"
            >
                <svg
                    xmlns="http://www.w3.org/2000/svg"
                    class="h-4 w-4"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    viewBox="0 0 24 24"
                >
                    <path d="M6 9l6 6 6-6" />
                </svg>
            </button>
        </div>
    </div>

    <div class="overflow-y-auto p-3 space-y-2 flex-1">
        {#if annotationsLoading}
            <div class="flex flex-col items-center py-8">
                <div class="spinner"></div>
                <p class="mt-4 text-gray-600">Loading annotations...</p>
            </div>
        {:else if annotations.length === 0}
            <p class="text-center text-gray-500 py-8">
                No annotations yet. Generate annotations or add one manually.
            </p>
        {:else if activeAnnotationIndex >= 0 && activeAnnotationIndex < annotations.length}
            {@const annotation = annotations[activeAnnotationIndex]}
            {@const index = activeAnnotationIndex}
            <AnnotationItem
                {annotation}
                {index}
                isSelected={activeAnnotationIndex === index && boxDrawMode}
                {currentVideoPath}
                sourceFile={annotationSourceFiles[index]}
                onNext={onNavigateNext}
                onPrevious={onNavigatePrevious}
                onSeek={(ts, videoPath) => onSeek(ts, videoPath)}
                onShowBox={(box, boxIndex, evidenceIndex) =>
                    onShowBox(box, boxIndex, index, evidenceIndex)}
                {onEdit}
                {onReview}
                {onDelete}
                {onSelect}
                {onQuickAdd}
                {activeVideoSource}
            />
        {:else}
            <p class="text-center text-gray-500 py-4">
                No annotation selected. Use the progress bar markers or
                navigation arrows to select an annotation.
            </p>
        {/if}
    </div>
</div>
