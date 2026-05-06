<script lang="ts">
	import Label from "$lib/components/ui/label/Label.svelte";
	import Select from "$lib/components/ui/select/Select.svelte";
	import type { SkillTypeData } from "$lib/types/annotation-data-types";
	import type { SkillType } from "$lib/types";

	interface Props {
		data: SkillTypeData;
		label?: string;
		onChange: (newData: SkillTypeData) => void;
	}

	let { data, label = "Skill Type", onChange }: Props = $props();

	const skillOptions: SkillType[] = [
		"object_location_memory",
		"conversational_memory",
		"visual_recall",
		"timeline_reconstruction",
		"intent_recall",
		"in_context_retrieval",
		"unknown",
	];

	function handleChange(e: Event) {
		const target = e.currentTarget as HTMLSelectElement;
		onChange({
			...data,
			value: target.value as SkillType,
		});
	}
</script>

<div class="skill-type-editor space-y-2">
	{#if label}
		<Label for="skill-select">{label}</Label>
	{/if}
	<Select id="skill-select" value={data.value || "unknown"} onchange={handleChange}>
		{#each skillOptions as skill}
			<option value={skill}>{skill.replace(/_/g, " ")}</option>
		{/each}
	</Select>
</div>
