/**
 * Unit tests for Button UI component
 * Tests that Button renders correctly with different variants and sizes
 */

import { describe, test, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import Button from '$lib/components/ui/button/Button.svelte';

describe('Button', () => {
	describe('renders basic button', () => {
		test('renders with default styling', () => {
			const { container } = render(Button);
			
			const button = container.querySelector('button');
			expect(button).toBeTruthy();
		});

		test('renders as button element', () => {
			const { container } = render(Button);
			
			expect(container.querySelector('button')).toBeTruthy();
		});
	});

	describe('variant styling', () => {
		test('applies default variant styling', () => {
			const { container } = render(Button, { props: { variant: 'default' } });
			
			const button = container.querySelector('button');
			expect(button?.className).toContain('bg-primary');
		});

		test('applies destructive variant styling', () => {
			const { container } = render(Button, { props: { variant: 'destructive' } });
			
			const button = container.querySelector('button');
			expect(button?.className).toContain('bg-destructive');
		});

		test('applies outline variant styling', () => {
			const { container } = render(Button, { props: { variant: 'outline' } });
			
			const button = container.querySelector('button');
			expect(button?.className).toContain('border-primary');
		});

		test('applies secondary variant styling', () => {
			const { container } = render(Button, { props: { variant: 'secondary' } });
			
			const button = container.querySelector('button');
			expect(button?.className).toContain('bg-secondary');
		});

		test('applies ghost variant styling', () => {
			const { container } = render(Button, { props: { variant: 'ghost' } });
			
			const button = container.querySelector('button');
			expect(button?.className).toContain('hover:bg-accent');
		});

		test('applies link variant styling', () => {
			const { container } = render(Button, { props: { variant: 'link' } });
			
			const button = container.querySelector('button');
			expect(button?.className).toContain('underline-offset-4');
		});
	});

	describe('size styling', () => {
		test('applies default size styling', () => {
			const { container } = render(Button, { props: { size: 'default' } });
			
			const button = container.querySelector('button');
			expect(button?.className).toContain('h-10');
		});

		test('applies sm size styling', () => {
			const { container } = render(Button, { props: { size: 'sm' } });
			
			const button = container.querySelector('button');
			expect(button?.className).toContain('h-9');
		});

		test('applies lg size styling', () => {
			const { container } = render(Button, { props: { size: 'lg' } });
			
			const button = container.querySelector('button');
			expect(button?.className).toContain('h-12');
		});

		test('applies icon size styling', () => {
			const { container } = render(Button, { props: { size: 'icon' } });
			
			const button = container.querySelector('button');
			expect(button?.className).toContain('h-10');
			expect(button?.className).toContain('w-10');
		});
	});

	describe('click handling', () => {
		test('fires click event when clicked', async () => {
			const handleClick = vi.fn();
			const { container } = render(Button, { props: { onclick: handleClick } });
			
			const button = container.querySelector('button');
			await fireEvent.click(button!);
			
			expect(handleClick).toHaveBeenCalledTimes(1);
		});
	});

	describe('disabled state', () => {
		test('applies disabled styling when disabled', () => {
			const { container } = render(Button, { props: { disabled: true } });
			
			const button = container.querySelector('button');
			expect(button?.disabled).toBe(true);
		});

		test('has disabled pointer events class', () => {
			const { container } = render(Button, { props: { disabled: true } });
			
			const button = container.querySelector('button');
			expect(button?.className).toContain('disabled:pointer-events-none');
		});
	});

	describe('custom class', () => {
		test('accepts additional className', () => {
			const { container } = render(Button, { props: { class: 'my-custom-class' } });
			
			const button = container.querySelector('button');
			expect(button?.className).toContain('my-custom-class');
		});
	});

	describe('base styling', () => {
		test('has base styling classes', () => {
			const { container } = render(Button);
			
			const button = container.querySelector('button');
			expect(button?.className).toContain('inline-flex');
			expect(button?.className).toContain('items-center');
			expect(button?.className).toContain('justify-center');
			expect(button?.className).toContain('rounded-md');
		});

		test('has transition effects', () => {
			const { container } = render(Button);
			
			const button = container.querySelector('button');
			expect(button?.className).toContain('transition-all');
		});
	});
});
