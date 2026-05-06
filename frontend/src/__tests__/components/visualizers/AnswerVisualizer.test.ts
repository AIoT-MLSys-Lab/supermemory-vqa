/**
 * Unit tests for AnswerVisualizer component
 * Tests that the answer visualizer renders correctly for different input states
 */

import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import AnswerVisualizer from '$lib/components/visualizers/AnswerVisualizer.svelte';

describe('AnswerVisualizer', () => {
	describe('renders correctly with valid answer', () => {
		test('displays answer text when provided', () => {
			render(AnswerVisualizer, { props: { value: 'It is a red apple.' } });
			
			expect(screen.getByText('It is a red apple.')).toBeTruthy();
		});

		test('displays A: prefix label', () => {
			render(AnswerVisualizer, { props: { value: 'Test answer' } });
			
			expect(screen.getByText('A:')).toBeTruthy();
		});

		test('has annotation-answer container class', () => {
			const { container } = render(AnswerVisualizer, { props: { value: 'Test' } });
			
			expect(container.querySelector('.annotation-answer')).toBeTruthy();
		});
	});

	describe('handles empty/undefined values', () => {
		test('shows placeholder when value is undefined', () => {
			render(AnswerVisualizer, { props: { value: undefined } });
			
			expect(screen.getByText('No answer provided')).toBeTruthy();
		});

		test('shows placeholder when value is empty string', () => {
			render(AnswerVisualizer, { props: { value: '' } });
			
			expect(screen.getByText('No answer provided')).toBeTruthy();
		});

		test('shows placeholder when value is whitespace only', () => {
			render(AnswerVisualizer, { props: { value: '   ' } });
			
			expect(screen.getByText('No answer provided')).toBeTruthy();
		});
	});

	describe('styling and structure', () => {
		test('answer text is wrapped in paragraph element', () => {
			const { container } = render(AnswerVisualizer, { props: { value: 'Test answer' } });
			
			const paragraph = container.querySelector('p');
			expect(paragraph).toBeTruthy();
			expect(paragraph?.textContent).toContain('Test answer');
		});

		test('placeholder text uses italic styling', () => {
			const { container } = render(AnswerVisualizer, { props: { value: undefined } });
			
			const emElement = container.querySelector('em');
			expect(emElement).toBeTruthy();
			expect(emElement?.textContent).toBe('No answer provided');
		});
	});
});
