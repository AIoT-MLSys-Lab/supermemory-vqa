<script lang="ts">
    import { Tooltip as TooltipPrimitive } from "bits-ui";
    import { cn } from "$lib/utils";
    import type { Snippet } from "svelte";

    interface Props {
        /** The tooltip text to display. */
        text: string;
        /** Content that triggers the tooltip (slot). */
        children: Snippet;
        /** Side to show tooltip. */
        side?: "top" | "right" | "bottom" | "left";
        /** Extra classes on the content bubble. */
        class?: string;
        /** Delay in ms before showing. */
        delayDuration?: number;
    }

    let {
        text,
        children,
        side = "top",
        class: className,
        delayDuration = 200,
    }: Props = $props();
</script>

<TooltipPrimitive.Provider>
    <TooltipPrimitive.Root {delayDuration}>
        <TooltipPrimitive.Trigger>
            {@render children()}
        </TooltipPrimitive.Trigger>
        <TooltipPrimitive.Content
            {side}
            sideOffset={4}
            class={cn(
                "z-50 overflow-hidden rounded-md bg-primary px-3 py-1.5 text-xs text-primary-foreground shadow-md animate-in fade-in-0 zoom-in-95",
                className,
            )}
        >
            {text}
        </TooltipPrimitive.Content>
    </TooltipPrimitive.Root>
</TooltipPrimitive.Provider>
