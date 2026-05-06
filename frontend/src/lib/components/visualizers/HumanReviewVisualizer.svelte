<script lang="ts">
	import { StatusBadge } from "$lib/components/app/ui";
	import type { HumanReview } from "$lib/types";
	import type { ReviewStatus } from "$lib/theme";

	interface Props {
		value?: HumanReview;
	}

	let { value }: Props = $props();

	function getReviewStatus(review?: HumanReview): ReviewStatus {
		if (!review) return "pending";
		return (
			(review.status as ReviewStatus) ||
			(review.reviewed ? "accepted" : "pending")
		);
	}

	const reviewStatus = $derived(getReviewStatus(value));
</script>

<div class="human-review-visualizer">
	<StatusBadge status={reviewStatus} />

	{#if value?.comment}
		<div class="mt-2 p-2 bg-secondary rounded text-sm">
			<strong>Review Comment:</strong>
			{value.comment}
		</div>
	{/if}
</div>
