<script lang="ts">
	interface Props {
		class?: string;
		children?: import("svelte").Snippet;
	}

	let { class: className = "", children }: Props = $props();
</script>

<div
	class="relative bg-white dark:bg-gray-900 rounded-lg shadow-xl border border-gray-200 dark:border-gray-700 w-full {className}"
	onclick={(e) => e.stopPropagation()}
	onkeydown={(e) => e.stopPropagation()}
	role="dialog"
	aria-modal="true"
	tabindex="-1"
>
	{@render children?.()}
</div>
