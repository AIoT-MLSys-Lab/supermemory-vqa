<script lang="ts">
    import type { LocationBox } from "$lib/types";

    interface Props {
        showBoxControls: boolean;
        activeBox: LocationBox | null;
        activeBoxIndex: number;
        activeAnnotationIndex: number;
        boxEditMode: boolean;
        boxDrawMode: boolean;
        editingBoxTimestamp: string;
        editingBoxDescription: string;
        onSave: () => void;
        onCancel: () => void;
        onDelete: () => void;
        onToggleDraw: () => void;
        onTimestampChange: (value: string) => void;
        onDescriptionChange: (value: string) => void;
    }

    let {
        showBoxControls,
        activeBox,
        activeBoxIndex,
        activeAnnotationIndex,
        boxEditMode,
        boxDrawMode,
        editingBoxTimestamp,
        editingBoxDescription,
        onSave,
        onCancel,
        onDelete,
        onToggleDraw,
        onTimestampChange,
        onDescriptionChange,
    }: Props = $props();
</script>

<!-- Keyboard shortcut hint -->
<div class="text-xs text-gray-500 mt-1">
    💡 Use ← → to seek ±5s, Space to play/pause, Arrow keys to move selected box
</div>

<!-- Box controls - use showBoxControls flag for stability -->
<div class="mt-1 space-y-1">
    {#if showBoxControls && activeBox}
        <!-- Box info row -->
        <div class="flex items-center gap-2 text-xs">
            <span
                class="px-1.5 py-0.5 bg-secondary text-foreground rounded font-medium"
            >
                Box {activeBoxIndex + 1}
            </span>
            <span class="text-muted-foreground"
                >@ {activeBox.timestamp || "N/A"}</span
            >
            {#if activeBox.description}
                <span
                    class="text-gray-600 truncate max-w-[150px]"
                    title={activeBox.description}
                >
                    {activeBox.description}
                </span>
            {/if}
            {#if boxEditMode}
                <span class="text-success text-[10px]">↔ Drag to edit</span>
            {/if}
        </div>

        <!-- Compact edit fields and actions -->
        <div class="flex items-center gap-2 flex-wrap">
            <input
                id="box-timestamp"
                type="text"
                class="w-16 px-1.5 py-0.5 text-xs border rounded"
                placeholder="00:00"
                title="Timestamp"
                value={editingBoxTimestamp}
                oninput={(e) => onTimestampChange(e.currentTarget.value)}
            />
            <input
                id="box-description"
                type="text"
                class="flex-1 min-w-[100px] px-1.5 py-0.5 text-xs border rounded"
                placeholder="Description"
                title="Description"
                value={editingBoxDescription}
                oninput={(e) => onDescriptionChange(e.currentTarget.value)}
            />
            <div class="flex items-center gap-1">
                <button
                    type="button"
                    class="p-1.5 rounded bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
                    title="Save Box"
                    onclick={onSave}
                >
                    <svg
                        xmlns="http://www.w3.org/2000/svg"
                        class="h-4 w-4"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2"
                        ><path
                            d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"
                        /><polyline points="17 21 17 13 7 13 7 21" /><polyline
                            points="7 3 7 8 15 8"
                        /></svg
                    >
                </button>
                <button
                    type="button"
                    class="p-1.5 rounded bg-gray-200 text-gray-700 hover:bg-gray-300 transition-colors"
                    title="Cancel"
                    onclick={onCancel}
                >
                    <svg
                        xmlns="http://www.w3.org/2000/svg"
                        class="h-4 w-4"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2"
                        ><line x1="18" y1="6" x2="6" y2="18" /><line
                            x1="6"
                            y1="6"
                            x2="18"
                            y2="18"
                        /></svg
                    >
                </button>
                <button
                    type="button"
                    class="p-1.5 rounded bg-destructive/10 text-destructive hover:bg-destructive/20 transition-colors"
                    title="Delete Box"
                    onclick={onDelete}
                >
                    <svg
                        xmlns="http://www.w3.org/2000/svg"
                        class="h-4 w-4"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2"
                        ><polyline points="3 6 5 6 21 6" /><path
                            d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"
                        /></svg
                    >
                </button>
            </div>
        </div>
    {/if}

    <!-- Add new box controls -->
    <div class="flex items-center gap-2">
        {#if activeAnnotationIndex >= 0}
            <button
                type="button"
                class="flex items-center gap-1 px-2 py-1 text-xs rounded transition-colors {boxDrawMode
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'}"
                title={boxDrawMode ? "Done Drawing" : "Draw New Box"}
                onclick={onToggleDraw}
            >
                <svg
                    xmlns="http://www.w3.org/2000/svg"
                    class="h-3.5 w-3.5"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    ><rect x="3" y="3" width="18" height="18" rx="2" /><line
                        x1="12"
                        y1="8"
                        x2="12"
                        y2="16"
                    /><line x1="8" y1="12" x2="16" y2="12" /></svg
                >
                {boxDrawMode ? "Done" : "Draw"}
            </button>
        {:else}
            <span class="text-xs text-gray-400 italic"
                >Select annotation to draw box</span
            >
        {/if}
    </div>
</div>
{#if boxDrawMode}
    <div class="mt-2 p-2 bg-warning/10 rounded text-sm text-warning">
        📝 Click and drag on the video to draw a new bounding box. Make sure an
        annotation is selected first.
    </div>
{/if}
