<script lang="ts">
	import Input from "$lib/components/ui/input/Input.svelte";
	import Label from "$lib/components/ui/label/Label.svelte";
	import type { TextData } from "$lib/types/annotation-data-types";
	import { unescapeHtml } from "$lib/utils";

	interface Props {
		data: TextData;
		label?: string;
		placeholder?: string;
		multiline?: boolean;
		rows?: number;
		onChange: (newData: TextData) => void;
	}

	let {
		data,
		label = "Text",
		placeholder = "Enter text...",
		multiline = false,
		rows = 3,
		onChange,
	}: Props = $props();

	function handleChange(e: Event) {
		const target = e.currentTarget as HTMLInputElement | HTMLTextAreaElement;
		onChange({
			...data,
			value: target.value,
		});
	}
</script>

<div class="text-editor space-y-2">
	{#if label}
		<Label>{label}</Label>
	{/if}
	{#if multiline}
		<textarea
			value={unescapeHtml(data.value || "")}
			oninput={handleChange}
			class="w-full border rounded-lg p-3 min-h-[{rows * 24}px] focus:ring-2 focus:ring-primary focus:outline-none"
			{placeholder}
		></textarea>
	{:else}
		<Input type="text" value={unescapeHtml(data.value || "")} oninput={handleChange} {placeholder} />
	{/if}
</div>
