<script lang="ts">
    import Badge from "$lib/components/ui/badge/Badge.svelte";
    import {
        type ReviewStatus,
        type ProcessingStatus,
        REVIEW_BADGE_VARIANT,
        REVIEW_LABEL,
        PROCESSING_BADGE_VARIANT,
        PROCESSING_LABEL,
    } from "$lib/theme";

    type Status = ReviewStatus | ProcessingStatus | string;

    interface Props {
        /** The status to display. */
        status: Status;
        /** Extra CSS classes. */
        class?: string;
    }

    let { status, class: className }: Props = $props();

    // Merge both maps; review statuses take precedence.
    const variantMap: Record<string, string> = {
        ...PROCESSING_BADGE_VARIANT,
        ...REVIEW_BADGE_VARIANT,
    };

    const labelMap: Record<string, string> = {
        ...PROCESSING_LABEL,
        ...REVIEW_LABEL,
    };

    const variant = $derived(
        (variantMap[status] ?? "secondary") as
            | "default"
            | "secondary"
            | "destructive"
            | "outline"
            | "success"
            | "warning"
            | "info",
    );

    const label = $derived(labelMap[status] ?? status);
</script>

<Badge {variant} class={className}>
    {label}
</Badge>
