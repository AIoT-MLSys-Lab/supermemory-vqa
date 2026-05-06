<script lang="ts">
	import { cn } from '$lib/utils';
	import type { HTMLSelectAttributes } from 'svelte/elements';
	import type { Snippet } from 'svelte';

	interface Props extends HTMLSelectAttributes {
		class?: string;
		value?: string;
		children?: Snippet;
	}

	let { class: className, value = $bindable(''), children, ...restProps }: Props = $props();
</script>

<select
	bind:value
	class={cn(
		'flex h-9 w-full items-center justify-between whitespace-nowrap rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50',
		className
	)}
	{...restProps}
>
	{#if children}
		{@render children()}
	{/if}
</select>
