/**
 * Unit tests for QuestionVisualizer component
 * Tests that the question visualizer renders correctly for different input states
 */

import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import QuestionVisualizer from '$lib/components/visualizers/QuestionVisualizer.svelte';

describe('QuestionVisualizer', () => {
	describe('renders correctly with valid question', () => {
		test('displays question text when provided', () => {
			render(QuestionVisualizer, { props: { value: 'What is on the table?' } });
			
			expect(screen.getByText('What is on the table?')).toBeTruthy();
		});

		test('displays Q: prefix label', () => {
			render(QuestionVisualizer, { props: { value: 'Test question' } });
			
			expect(screen.getByText('Q:')).toBeTruthy();
		});

		test('has annotation-question container class', () => {
			const { container } = render(QuestionVisualizer, { props: { value: 'Test' } });
			
			expect(container.querySelector('.annotation-question')).toBeTruthy();
		});
	});

	describe('handles empty/undefined values', () => {
		test('shows placeholder when value is undefined', () => {
			render(QuestionVisualizer, { props: { value: undefined } });
			
			expect(screen.getByText('No question provided')).toBeTruthy();
		});

		test('shows placeholder when value is empty string', () => {
			render(QuestionVisualizer, { props: { value: '' } });
			
			expect(screen.getByText('No question provided')).toBeTruthy();
		});

		test('shows placeholder when value is whitespace only', () => {
			render(QuestionVisualizer, { props: { value: '   ' } });
			
			expect(screen.getByText('No question provided')).toBeTruthy();
		});
	});

	describe('styling and structure', () => {
		test('question text is wrapped in paragraph element', () => {
			const { container } = render(QuestionVisualizer, { props: { value: 'Test question' } });
			
			const paragraph = container.querySelector('p');
			expect(paragraph).toBeTruthy();
			expect(paragraph?.textContent).toContain('Test question');
		});

		test('placeholder text uses italic styling', () => {
			const { container } = render(QuestionVisualizer, { props: { value: undefined } });
			
			const emElement = container.querySelector('em');
			expect(emElement).toBeTruthy();
			expect(emElement?.textContent).toBe('No question provided');
		});
	});
});
