<script lang="ts">
    import Button from "$lib/components/ui/button/Button.svelte";
    import Tooltip from "$lib/components/ui/tooltip/SimpleTooltip.svelte";
    import type { Snippet } from "svelte";
    import type { HTMLButtonAttributes } from "svelte/elements";

    interface Props extends HTMLButtonAttributes {
        /** Tooltip text and accessible label. */
        label: string;
        /** Optional visible text shown next to the icon. */
        text?: string;
        /** Icon snippet (SVG or component). */
        icon: Snippet;
        /** Button variant (re-exports from Button). */
        variant?:
            | "default"
            | "destructive"
            | "outline"
            | "secondary"
            | "ghost"
            | "link";
        /** Button size. */
        size?: "default" | "sm" | "lg" | "icon";
        /** Extra CSS classes. */
        class?: string;
        /** Tooltip placement. */
        tooltipSide?: "top" | "right" | "bottom" | "left";
    }

    let {
        label,
        text,
        icon,
        variant = "ghost",
        size = "icon",
        class: className,
        tooltipSide = "top",
        ...restProps
    }: Props = $props();
</script>

<Tooltip text={label} side={tooltipSide}>
    <Button
        {variant}
        size={text ? (size === "icon" ? "sm" : size) : size}
        class={className}
        aria-label={label}
        {...restProps}
    >
        {@render icon()}
        {#if text}
            <span class="ml-1">{text}</span>
        {/if}
    </Button>
</Tooltip>
