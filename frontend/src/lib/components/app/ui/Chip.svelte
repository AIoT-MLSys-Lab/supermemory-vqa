<script lang="ts">
    import { cn } from "$lib/utils";
    import {
        SKILL_CLASSES,
        SKILL_DEFAULT_CLASS,
        SKILL_LABEL,
        MODALITY_CLASSES,
        MODALITY_DEFAULT_CLASS,
    } from "$lib/theme";

    type ChipKind = "skill" | "modality" | "custom";

    interface Props {
        /** The raw value (e.g. skill type key or modality key). */
        value: string;
        /** What kind of chip: determines the colour mapping. */
        kind?: ChipKind;
        /** Override label text (by default derived from `value`). */
        label?: string;
        /** Extra CSS classes. */
        class?: string;
    }

    let { value, kind = "custom", label, class: className }: Props = $props();

    const resolvedClasses = $derived.by(() => {
        if (kind === "skill")
            return SKILL_CLASSES[value] ?? SKILL_DEFAULT_CLASS;
        if (kind === "modality")
            return MODALITY_CLASSES[value] ?? MODALITY_DEFAULT_CLASS;
        return "bg-secondary text-foreground border border-border";
    });

    const resolvedLabel = $derived(label ?? SKILL_LABEL[value] ?? value);
</script>

<span
    class={cn(
        "inline-flex items-center text-sm font-semibold px-2.5 py-0.5 rounded-full whitespace-nowrap",
        resolvedClasses,
        className,
    )}
>
    {resolvedLabel}
</span>
