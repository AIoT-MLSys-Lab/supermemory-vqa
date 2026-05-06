<script lang="ts">
    interface Props {
        onAddAnnotation: () => void;
        onShowSummary: () => void;
    }

    let { onAddAnnotation, onShowSummary }: Props = $props();
</script>

<div class="flex flex-wrap gap-2 justify-center mt-4">
    <button
        type="button"
        class="inline-flex items-center gap-1 px-3 py-2 text-sm font-medium rounded bg-secondary text-secondary-foreground hover:bg-secondary/80 transition-colors"
        title="Add Annotation Manually"
        onclick={onAddAnnotation}
    >
        <svg
            xmlns="http://www.w3.org/2000/svg"
            class="h-4 w-4"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            ><line x1="12" y1="5" x2="12" y2="19" /><line
                x1="5"
                y1="12"
                x2="19"
                y2="12"
            /></svg
        >
        Add Annotation
    </button>
    <button
        type="button"
        class="inline-flex items-center gap-1 px-3 py-2 text-sm font-medium rounded bg-gray-100 text-gray-700 hover:bg-gray-200 transition-colors"
        title="View Summary"
        onclick={onShowSummary}
    >
        <svg
            xmlns="http://www.w3.org/2000/svg"
            class="h-4 w-4"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            ><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline
                points="17 8 12 3 7 8"
            /><line x1="12" y1="3" x2="12" y2="15" /></svg
        >
        Summary
    </button>
</div>
