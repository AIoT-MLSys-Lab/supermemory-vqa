<script lang="ts">
	import { cn } from '$lib/utils';
	import { tv, type VariantProps } from 'tailwind-variants';
	import type { HTMLButtonAttributes } from 'svelte/elements';
	import type { Snippet } from 'svelte';

	const buttonVariants = tv({
		base: 'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 active:scale-[0.98] shadow-sm hover:shadow-md',
		variants: {
			variant: {
				default: 'bg-primary text-primary-foreground hover:bg-primary/90 hover:scale-[1.02]',
				destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/90 hover:scale-[1.02]',
				outline: 'border-2 border-primary bg-background text-primary hover:bg-primary hover:text-primary-foreground hover:scale-[1.02]',
				secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80 hover:scale-[1.02]',
				ghost: 'hover:bg-accent hover:text-accent-foreground shadow-none hover:shadow-none',
				link: 'text-primary underline-offset-4 hover:underline shadow-none hover:shadow-none'
			},
			size: {
				default: 'h-10 px-5 py-2',
				sm: 'h-9 rounded-md px-4 text-xs',
				lg: 'h-12 rounded-md px-8 text-base',
				icon: 'h-10 w-10'
			}
		},
		defaultVariants: {
			variant: 'default',
			size: 'default'
		}
	});

	type Variant = VariantProps<typeof buttonVariants>['variant'];
	type Size = VariantProps<typeof buttonVariants>['size'];

	interface Props extends HTMLButtonAttributes {
		variant?: Variant;
		size?: Size;
		class?: string;
		children?: Snippet;
	}

	let {
		variant = 'default',
		size = 'default',
		class: className,
		children,
		...restProps
	}: Props = $props();
</script>

<button class={cn(buttonVariants({ variant, size }), className)} {...restProps}>
	{#if children}
		{@render children()}
	{/if}
</button>
