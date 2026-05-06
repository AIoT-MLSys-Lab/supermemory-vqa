<script lang="ts">
	import { unescapeHtml } from "$lib/utils";

	interface Props {
		value?: string;
		prefix?: string;
		placeholder?: string;
		style?: "question" | "answer" | "default";
	}

	let {
		value,
		prefix = "",
		placeholder = "No text provided",
		style = "default",
	}: Props = $props();

	// Determine styling based on type
	const containerClass = $derived(
		style === "question"
			? "annotation-question"
			: style === "answer"
				? "annotation-answer"
				: "annotation-text",
	);

	const textClass = $derived(
		style === "question"
			? "text-base font-medium"
			: style === "answer"
				? "text-base text-foreground"
				: "text-base",
	);

	const prefixClass = $derived(
		"text-primary" + (style === "answer" ? " font-medium" : ""),
	);
</script>

<div class={containerClass}>
	{#if value && value.trim()}
		<p class={textClass}>
			{#if prefix}
				<span class={prefixClass}>{prefix}</span>
			{/if}
			{typeof value === "object" && value !== null
				? unescapeHtml((value as any).text)
				: unescapeHtml(value)}
		</p>
	{:else}
		<p class="text-muted-foreground italic">
			{#if prefix}
				{prefix}
			{/if}
			<em>{placeholder}</em>
		</p>
	{/if}
</div>
