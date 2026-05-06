<script lang="ts">
    import AnnotationFileSelector from "./AnnotationFileSelector.svelte";
    import { IconButton } from "./ui";
    import type { AnnotationFile } from "$lib/types";

    interface Props {
        videoFilename: string;
        annotationFiles: AnnotationFile[];
        selectedFiles: string[];
        onSelectionChange: (filenames: string[]) => void;
        onRefresh: () => void;
        onDebugView: (type: "raw" | "fullraw" | "thinking" | "file") => void;
    }

    let {
        videoFilename,
        annotationFiles,
        selectedFiles,
        onSelectionChange,
        onRefresh,
        onDebugView,
    }: Props = $props();

    let collapsed = $state(false);
</script>

<div class="border rounded-lg bg-card mb-4">
    <div class="flex items-center justify-between p-3 border-b bg-muted/30">
        <h3 class="text-sm font-semibold">
            Annotation Files ({annotationFiles.length})
        </h3>
        <button
            type="button"
            class="p-1.5 rounded hover:bg-secondary transition-colors"
            onclick={() => (collapsed = !collapsed)}
            title={collapsed ? "Expand panel" : "Collapse panel"}
            aria-label={collapsed
                ? "Expand annotation files panel"
                : "Collapse annotation files panel"}
        >
            <svg
                xmlns="http://www.w3.org/2000/svg"
                class="h-4 w-4 transition-transform {collapsed
                    ? 'rotate-180'
                    : ''}"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                viewBox="0 0 24 24"
            >
                <path d="M18 15l-6-6-6 6" />
            </svg>
        </button>
    </div>
    {#if !collapsed}
        <div class="p-3">
            <AnnotationFileSelector
                {videoFilename}
                {annotationFiles}
                {selectedFiles}
                {onSelectionChange}
                {onRefresh}
            />

            <div class="flex gap-1 mb-2 justify-end">
                {#if selectedFiles.length > 0}
                    <IconButton
                        label="View Raw Response"
                        onclick={() => onDebugView("raw")}
                        variant="outline"
                        size="sm"
                        class="h-8 w-8 p-0"
                    >
                        {#snippet icon()}
                            <svg
                                xmlns="http://www.w3.org/2000/svg"
                                class="h-4 w-4"
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                stroke-width="2"
                                ><path
                                    d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"
                                /><polyline points="14 2 14 8 20 8" /></svg
                            >
                        {/snippet}
                    </IconButton>
                    <IconButton
                        label="View Full Raw Response"
                        onclick={() => onDebugView("fullraw")}
                        variant="outline"
                        size="sm"
                        class="h-8 w-8 p-0"
                    >
                        {#snippet icon()}
                            <svg
                                xmlns="http://www.w3.org/2000/svg"
                                class="h-4 w-4"
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                stroke-width="2"
                                ><path
                                    d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"
                                /><polyline points="14 2 14 8 20 8" /><line
                                    x1="16"
                                    y1="13"
                                    x2="8"
                                    y2="13"
                                /><line x1="16" y1="17" x2="8" y2="17" /></svg
                            >
                        {/snippet}
                    </IconButton>
                    <IconButton
                        label="View Model Thinking"
                        onclick={() => onDebugView("thinking")}
                        variant="outline"
                        size="sm"
                        class="h-8 w-8 p-0"
                    >
                        {#snippet icon()}
                            <svg
                                xmlns="http://www.w3.org/2000/svg"
                                class="h-4 w-4"
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                stroke-width="2"
                                ><circle cx="12" cy="12" r="10" /><path
                                    d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"
                                /><line
                                    x1="12"
                                    y1="17"
                                    x2="12.01"
                                    y2="17"
                                /></svg
                            >
                        {/snippet}
                    </IconButton>
                    <IconButton
                        label="View Annotation File"
                        onclick={() => onDebugView("file")}
                        variant="outline"
                        size="sm"
                        class="h-8 w-8 p-0"
                    >
                        {#snippet icon()}
                            <svg
                                xmlns="http://www.w3.org/2000/svg"
                                class="h-4 w-4"
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                stroke-width="2"
                                ><path
                                    d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"
                                /><polyline points="13 2 13 9 20 9" /></svg
                            >
                        {/snippet}
                    </IconButton>
                {/if}
            </div>
        </div>
    {/if}
</div>
