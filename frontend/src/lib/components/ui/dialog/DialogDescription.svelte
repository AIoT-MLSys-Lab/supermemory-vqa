<script lang="ts">
	interface Props {
		class?: string;
		children?: import('svelte').Snippet;
	}

	let { class: className = '', children }: Props = $props();
</script>

<p class="text-sm text-gray-500 dark:text-gray-400 mt-1 {className}">
	{@render children?.()}
</p>
