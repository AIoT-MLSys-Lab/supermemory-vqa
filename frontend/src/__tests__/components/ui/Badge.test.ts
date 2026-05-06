/**
 * Unit tests for Badge UI component
 * Tests that Badge renders correctly with different variants
 */

import { describe, test, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import Badge from '$lib/components/ui/badge/Badge.svelte';

describe('Badge', () => {
	describe('renders basic badge', () => {
		test('renders as span element', () => {
			const { container } = render(Badge);
			
			expect(container.querySelector('span')).toBeTruthy();
		});
	});

	describe('variant styling', () => {
		test('applies default variant styling', () => {
			const { container } = render(Badge, { props: { variant: 'default' } });
			
			const span = container.querySelector('span');
			expect(span?.className).toContain('bg-primary');
		});

		test('applies secondary variant styling', () => {
			const { container } = render(Badge, { props: { variant: 'secondary' } });
			
			const span = container.querySelector('span');
			expect(span?.className).toContain('bg-secondary');
		});

		test('applies destructive variant styling', () => {
			const { container } = render(Badge, { props: { variant: 'destructive' } });
			
			const span = container.querySelector('span');
			expect(span?.className).toContain('bg-destructive');
		});

		test('applies outline variant styling', () => {
			const { container } = render(Badge, { props: { variant: 'outline' } });
			
			const span = container.querySelector('span');
			expect(span?.className).toContain('text-foreground');
		});

		test('applies success variant styling', () => {
			const { container } = render(Badge, { props: { variant: 'success' } });

			const span = container.querySelector('span');
			expect(span?.className).toContain('bg-emerald-50');
			expect(span?.className).toContain('text-emerald-700');
		});

		test('applies warning variant styling', () => {
			const { container } = render(Badge, { props: { variant: 'warning' } });

			const span = container.querySelector('span');
			expect(span?.className).toContain('bg-amber-50');
			expect(span?.className).toContain('text-amber-700');
		});

		test('applies info variant styling', () => {
			const { container } = render(Badge, { props: { variant: 'info' } });

			const span = container.querySelector('span');
			expect(span?.className).toContain('bg-blue-50');
			expect(span?.className).toContain('text-blue-700');
		});
	});

	describe('base styling', () => {
		test('has base styling classes', () => {
			const { container } = render(Badge);
			
			const span = container.querySelector('span');
			expect(span?.className).toContain('inline-flex');
			expect(span?.className).toContain('items-center');
			expect(span?.className).toContain('rounded-md');
		});

		test('has text styling', () => {
			const { container } = render(Badge);
			
			const span = container.querySelector('span');
			expect(span?.className).toContain('text-xs');
			expect(span?.className).toContain('font-semibold');
		});

		test('has transition effects', () => {
			const { container } = render(Badge);
			
			const span = container.querySelector('span');
			expect(span?.className).toContain('transition-colors');
		});
	});

	describe('custom class', () => {
		test('accepts additional className', () => {
			const { container } = render(Badge, { props: { class: 'my-custom-class' } });
			
			const span = container.querySelector('span');
			expect(span?.className).toContain('my-custom-class');
		});
	});
});
