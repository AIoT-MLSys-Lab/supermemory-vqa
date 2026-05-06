<script lang="ts">
	import { cn } from '$lib/utils';
	import { tv, type VariantProps } from 'tailwind-variants';
	import type { HTMLAttributes } from 'svelte/elements';
	import type { Snippet } from 'svelte';

	const alertVariants = tv({
		base: 'relative w-full rounded-lg border px-4 py-3 text-sm',
		variants: {
			variant: {
				default: 'bg-background text-foreground',
				destructive: 'border-destructive/50 text-destructive dark:border-destructive bg-red-50 dark:bg-red-950',
				success: 'border-green-500/50 text-green-700 dark:text-green-400 bg-green-50 dark:bg-green-950',
				info: 'border-blue-500/50 text-blue-700 dark:text-blue-400 bg-blue-50 dark:bg-blue-950'
			}
		},
		defaultVariants: {
			variant: 'default'
		}
	});

	type Variant = VariantProps<typeof alertVariants>['variant'];

	interface Props extends HTMLAttributes<HTMLDivElement> {
		variant?: Variant;
		class?: string;
		children?: Snippet;
	}

	let { variant = 'default', class: className, children, ...restProps }: Props = $props();
</script>

<div role="alert" class={cn(alertVariants({ variant }), className)} {...restProps}>
	{#if children}
		{@render children()}
	{/if}
</div>
