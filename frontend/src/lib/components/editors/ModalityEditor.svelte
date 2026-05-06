<script lang="ts">
	import Label from "$lib/components/ui/label/Label.svelte";
	import type { ModalityListData } from "$lib/types/annotation-data-types";

	interface Props {
		data: ModalityListData;
		label?: string;
		onChange: (newData: ModalityListData) => void;
	}

	let { data, label = "Modalities", onChange }: Props = $props();

	function toggleModality(modality: string) {
		const currentModalities = data.value || [];
		const newModalities = currentModalities.includes(modality)
			? currentModalities.filter((m) => m !== modality)
			: [...currentModalities, modality];

		onChange({
			...data,
			value: newModalities,
		});
	}

	const isChecked = (modality: string) => {
		return (data.value || []).includes(modality);
	};
</script>

<div class="modality-editor space-y-2">
	{#if label}
		<Label>{label}</Label>
	{/if}
	<div class="grid grid-cols-2 gap-2">
		{#each data.availableModalities as modality}
			<div class="flex items-center space-x-2">
				<input
					type="checkbox"
					id={`modality-${modality}`}
					checked={isChecked(modality)}
					onchange={() => toggleModality(modality)}
					class="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
				/>
				<Label for={`modality-${modality}`} class="font-normal cursor-pointer">
					{modality}
				</Label>
			</div>
		{/each}
	</div>
</div>
