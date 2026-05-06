<script lang="ts">
	import { Chip } from "$lib/components/app/ui";
	import type { SkillType } from "$lib/types";

	interface Props {
		value?: SkillType | string;
	}

	let { value }: Props = $props();
</script>

{#if value}
	<Chip {value} kind="skill" />
{:else}
	<Chip value="unknown" kind="skill" label="unknown" />
{/if}
