<script lang="ts">
    import Button from "$lib/components/ui/button/Button.svelte";

    interface Props {
        open: boolean;
        content: string;
        onClose: () => void;
    }

    let { open, content, onClose }: Props = $props();
</script>

{#if open}
    <div
        class="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
        role="button"
        tabindex="0"
        onclick={onClose}
        onkeydown={(e) => {
            if (e.key === "Enter" || e.key === " ") onClose();
        }}
    >
        <div
            class="bg-white rounded-lg shadow-xl w-full max-w-4xl max-h-[90vh] overflow-hidden"
            role="dialog"
            aria-modal="true"
            tabindex="-1"
            onclick={(e) => e.stopPropagation()}
            onkeydown={(e) => e.stopPropagation()}
        >
            <div
                class="p-4 bg-card border-b border-border flex justify-between items-center"
            >
                <h2 class="text-xl font-bold text-foreground">
                    Prompt Preview
                </h2>
                <Button variant="ghost" onclick={onClose}>Close</Button>
            </div>
            <div class="p-6 overflow-y-auto max-h-[calc(90vh-80px)]">
                <pre
                    class="bg-gray-100 p-4 rounded-lg overflow-x-auto whitespace-pre-wrap text-sm font-mono">{content}</pre>
            </div>
        </div>
    </div>
{/if}
