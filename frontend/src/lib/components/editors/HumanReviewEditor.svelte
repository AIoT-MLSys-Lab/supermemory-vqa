<script lang="ts">
	import Input from "$lib/components/ui/input/Input.svelte";
	import Label from "$lib/components/ui/label/Label.svelte";
	import Select from "$lib/components/ui/select/Select.svelte";
	import type { HumanReviewData } from "$lib/types/annotation-data-types";

	interface Props {
		data: HumanReviewData;
		label?: string;
		onChange: (newData: HumanReviewData) => void;
	}

	let { data, label = "Human Review", onChange }: Props = $props();

	function handleStatusChange(e: Event) {
		const target = e.currentTarget as HTMLSelectElement;
		const status = target.value as "accepted" | "rejected" | "pending";
		onChange({
			...data,
			value: {
				...data.value,
				status,
				reviewed: status !== "pending",
			},
		});
	}

	function handleCommentChange(e: Event) {
		const target = e.currentTarget as HTMLInputElement;
		onChange({
			...data,
			value: {
				...data.value,
				comment: target.value,
			},
		});
	}
</script>

<div class="human-review-editor space-y-4 p-4 border rounded-lg bg-secondary/50">
	{#if label}
		<Label>{label}</Label>
	{/if}
	<div class="grid grid-cols-2 gap-4">
		<div class="space-y-2">
			<Label for="review-status">Status</Label>
			<Select
				id="review-status"
				value={data.value?.status || "pending"}
				onchange={handleStatusChange}
			>
				<option value="pending">⏳ Pending</option>
				<option value="accepted">✓ Accepted</option>
				<option value="rejected">✗ Rejected</option>
			</Select>
		</div>
		<div class="space-y-2">
			<Label for="review-comment">Comment</Label>
			<Input
				id="review-comment"
				type="text"
				value={data.value?.comment || ""}
				oninput={handleCommentChange}
				placeholder="Optional review comment"
			/>
		</div>
	</div>
</div>
