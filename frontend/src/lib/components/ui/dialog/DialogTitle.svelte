<script lang="ts">
	interface Props {
		class?: string;
		children?: import('svelte').Snippet;
	}

	let { class: className = '', children }: Props = $props();
</script>

<h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100 {className}">
	{@render children?.()}
</h2>
