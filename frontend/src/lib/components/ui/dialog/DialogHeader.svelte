<script lang="ts">
	interface Props {
		class?: string;
		children?: import('svelte').Snippet;
	}

	let { class: className = '', children }: Props = $props();
</script>

<div class="p-4 border-b border-gray-200 dark:border-gray-700 {className}">
	{@render children?.()}
</div>
