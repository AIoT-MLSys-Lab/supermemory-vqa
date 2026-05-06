<script lang="ts">
    import {
        Dialog,
        DialogContent,
        DialogHeader,
        DialogTitle,
        DialogDescription,
        DialogFooter,
    } from "$lib/components/ui/dialog";
    import Button from "$lib/components/ui/button/Button.svelte";
    import { marked } from "marked";

    let {
        open = $bindable(false),
        title,
        content,
        contentType,
    } = $props<{
        open: boolean;
        title: string;
        content: string;
        contentType: "markdown" | "json" | "text";
    }>();

    function copyToClipboard() {
        navigator.clipboard.writeText(content);
    }
</script>

<Dialog bind:open>
    <DialogContent class="max-w-4xl max-h-[85vh] flex flex-col">
        <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            <!-- Add description to avoid warning -->
            <DialogDescription>
                Review the {contentType} content below.
            </DialogDescription>
        </DialogHeader>

        <div
            class="flex-1 overflow-y-auto min-h-[300px] border rounded-md p-4 bg-muted/30"
        >
            {#if contentType === "markdown"}
                <div class="prose dark:prose-invert max-w-none">
                    <!-- eslint-disable-next-line svelte/no-at-html-tags -->
                    {@html marked(content)}
                </div>
            {:else if contentType === "json"}
                <pre
                    class="text-xs font-mono whitespace-pre-wrap">{content}</pre>
            {:else}
                <pre
                    class="text-sm font-mono whitespace-pre-wrap">{content}</pre>
            {/if}
        </div>

        <DialogFooter>
            <Button variant="outline" onclick={copyToClipboard}
                >Copy to Clipboard</Button
            >
            <Button onclick={() => (open = false)}>Close</Button>
        </DialogFooter>
    </DialogContent>
</Dialog>
