/**
 * Unit tests for ModalitiesVisualizer component
 * Tests that the modalities visualizer renders correctly for different modality arrays
 */

import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import ModalitiesVisualizer from '$lib/components/visualizers/ModalitiesVisualizer.svelte';

describe('ModalitiesVisualizer', () => {
	describe('renders correctly with valid modalities', () => {
		test('displays single modality', () => {
			const { container } = render(ModalitiesVisualizer, { props: { value: ['visual'] } });

			expect(container.textContent).toContain('visual');
		});

		test('displays multiple modalities', () => {
			const { container } = render(ModalitiesVisualizer, { props: { value: ['visual', 'audio'] } });

			expect(container.textContent).toContain('visual');
			expect(container.textContent).toContain('audio');
		});

		test('displays text modality', () => {
			const { container } = render(ModalitiesVisualizer, { props: { value: ['text'] } });

			expect(container.textContent).toContain('text');
		});

		test('has modalities-visualizer container class', () => {
			const { container } = render(ModalitiesVisualizer, { props: { value: ['visual'] } });

			expect(container.querySelector('.modalities-visualizer')).toBeTruthy();
		});
	});

	describe('handles various modality combinations', () => {
		test('displays all three common modalities', () => {
			const { container } = render(ModalitiesVisualizer, { props: { value: ['visual', 'audio', 'text'] } });

			expect(container.textContent).toContain('visual');
			expect(container.textContent).toContain('audio');
			expect(container.textContent).toContain('text');
		});

		test('displays single visual modality', () => {
			const { container } = render(ModalitiesVisualizer, { props: { value: ['visual'] } });

			expect(container.textContent).toContain('visual');
		});

		test('displays single audio modality', () => {
			const { container } = render(ModalitiesVisualizer, { props: { value: ['audio'] } });

			expect(container.textContent).toContain('audio');
		});

		test('displays single text modality', () => {
			const { container } = render(ModalitiesVisualizer, { props: { value: ['text'] } });

			expect(container.textContent).toContain('text');
		});

		test('displays custom modality types', () => {
			const { container } = render(ModalitiesVisualizer, { props: { value: ['spatial', 'temporal'] } });

			expect(container.textContent).toContain('spatial');
			expect(container.textContent).toContain('temporal');
		});
	});

	describe('handles empty/undefined values', () => {
		test('shows placeholder when value is undefined', () => {
			const { container } = render(ModalitiesVisualizer, { props: { value: undefined } });

			expect(container.textContent).toContain('No modalities');
		});

		test('shows placeholder when value is empty array', () => {
			const { container } = render(ModalitiesVisualizer, { props: { value: [] } });

			expect(container.textContent).toContain('No modalities');
		});
	});

	describe('styling and structure', () => {
		test('modalities with values render with background styling', () => {
			const { container } = render(ModalitiesVisualizer, { props: { value: ['visual'] } });

			const span = container.querySelector('span');
			expect(span?.className).toContain('bg-indigo-50'); // visual class
		});

		test('placeholder uses italic styling', () => {
			const { container } = render(ModalitiesVisualizer, { props: { value: undefined } });

			const span = container.querySelector('span');
			expect(span?.className).toContain('italic');
		});

		test('modalities are rendered in a span element', () => {
			const { container } = render(ModalitiesVisualizer, { props: { value: ['visual', 'audio'] } });

			const spans = container.querySelectorAll('span');
			expect(spans.length).toBe(2);
			expect(spans[0]?.textContent).toContain('visual');
		});
	});

	describe('modality count variations', () => {
		test('handles single item array correctly', () => {
			const { container } = render(ModalitiesVisualizer, { props: { value: ['visual'] } });

			const spans = container.querySelectorAll('span');
			expect(spans.length).toBe(1);
			expect(spans[0]?.textContent).toContain('visual');
		});

		test('handles two item array correctly', () => {
			const { container } = render(ModalitiesVisualizer, { props: { value: ['visual', 'audio'] } });

			const spans = container.querySelectorAll('span');
			expect(spans.length).toBe(2);
			expect(container.textContent).toContain('visual');
			expect(container.textContent).toContain('audio');
		});

		test('handles many item array correctly', () => {
			const { container } = render(ModalitiesVisualizer, {
				props: { value: ['a', 'b', 'c', 'd', 'e'] }
			});

			const spans = container.querySelectorAll('span');
			expect(spans.length).toBe(5);
			expect(container.textContent).toContain('a');
			expect(container.textContent).toContain('e');
		});
	});
});
