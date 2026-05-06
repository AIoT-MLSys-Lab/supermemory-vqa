<script lang="ts">
	import { cn } from '$lib/utils';
	import { tv, type VariantProps } from 'tailwind-variants';
	import type { HTMLAttributes } from 'svelte/elements';
	import type { Snippet } from 'svelte';

	const badgeVariants = tv({
		base: 'inline-flex items-center rounded-md border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
		variants: {
			variant: {
				default: 'border-transparent bg-primary text-primary-foreground shadow hover:bg-primary/80',
				secondary: 'border-border bg-secondary text-secondary-foreground hover:bg-secondary/80',
				destructive: 'border-transparent bg-destructive text-destructive-foreground shadow hover:bg-destructive/80',
				outline: 'text-foreground border-border',
				success: 'border-transparent bg-emerald-50 text-emerald-700 border border-emerald-200',
				warning: 'border-transparent bg-amber-50 text-amber-700 border border-amber-200',
				info: 'border-transparent bg-blue-50 text-blue-700 border border-blue-200',
				pending: 'border-border bg-zinc-50 text-zinc-600',
				approved: 'border-transparent bg-emerald-50 text-emerald-700 border border-emerald-200',
				rejected: 'border-transparent bg-rose-50 text-rose-700 border border-rose-200'
			}
		},
		defaultVariants: {
			variant: 'default'
		}
	});

	type Variant = VariantProps<typeof badgeVariants>['variant'];

	interface Props extends HTMLAttributes<HTMLSpanElement> {
		variant?: Variant;
		class?: string;
		children?: Snippet;
	}

	let { variant = 'default', class: className, children, ...restProps }: Props = $props();
</script>

<span class={cn(badgeVariants({ variant }), className)} {...restProps}>
	{#if children}
		{@render children()}
	{/if}
</span>
