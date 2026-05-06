/**
 * Unit tests for TextVisualizer component
 * Tests that the unified text visualizer renders correctly for different input states
 * and different styles (question, answer, default)
 */

import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import TextVisualizer from '$lib/components/visualizers/TextVisualizer.svelte';

describe('TextVisualizer', () => {
	describe('renders correctly with valid text', () => {
		test('displays text when provided', () => {
			render(TextVisualizer, { props: { value: 'Sample text content' } });

			expect(screen.getByText('Sample text content')).toBeTruthy();
		});

		test('displays custom prefix when provided', () => {
			render(TextVisualizer, { props: { value: 'Test', prefix: 'Q:' } });

			expect(screen.getByText('Q:')).toBeTruthy();
		});

		test('works without prefix', () => {
			render(TextVisualizer, { props: { value: 'Test text' } });

			expect(screen.getByText('Test text')).toBeTruthy();
		});
	});

	describe('question style', () => {
		test('displays question text with Q: prefix', () => {
			render(TextVisualizer, {
				props: {
					value: 'What is on the table?',
					prefix: 'Q:',
					style: 'question'
				}
			});

			expect(screen.getByText('What is on the table?')).toBeTruthy();
			expect(screen.getByText('Q:')).toBeTruthy();
		});

		test('has annotation-question container class', () => {
			const { container } = render(TextVisualizer, {
				props: {
					value: 'Test',
					style: 'question'
				}
			});

			expect(container.querySelector('.annotation-question')).toBeTruthy();
		});

		test('shows custom placeholder for questions', () => {
			render(TextVisualizer, {
				props: {
					value: undefined,
					prefix: 'Q:',
					placeholder: 'No question provided',
					style: 'question'
				}
			});

			expect(screen.getByText('No question provided')).toBeTruthy();
		});
	});

	describe('answer style', () => {
		test('displays answer text with A: prefix', () => {
			render(TextVisualizer, {
				props: {
					value: 'It is a red apple.',
					prefix: 'A:',
					style: 'answer'
				}
			});

			expect(screen.getByText('It is a red apple.')).toBeTruthy();
			expect(screen.getByText('A:')).toBeTruthy();
		});

		test('has annotation-answer container class', () => {
			const { container } = render(TextVisualizer, {
				props: {
					value: 'Test',
					style: 'answer'
				}
			});

			expect(container.querySelector('.annotation-answer')).toBeTruthy();
		});

		test('shows custom placeholder for answers', () => {
			render(TextVisualizer, {
				props: {
					value: undefined,
					prefix: 'A:',
					placeholder: 'No answer provided',
					style: 'answer'
				}
			});

			expect(screen.getByText('No answer provided')).toBeTruthy();
		});
	});

	describe('default style', () => {
		test('has annotation-text container class', () => {
			const { container } = render(TextVisualizer, {
				props: {
					value: 'Test',
					style: 'default'
				}
			});

			expect(container.querySelector('.annotation-text')).toBeTruthy();
		});
	});

	describe('handles empty/undefined values', () => {
		test('shows placeholder when value is undefined', () => {
			render(TextVisualizer, { props: { value: undefined, placeholder: 'No text provided' } });

			expect(screen.getByText('No text provided')).toBeTruthy();
		});

		test('shows placeholder when value is empty string', () => {
			render(TextVisualizer, { props: { value: '', placeholder: 'No text provided' } });

			expect(screen.getByText('No text provided')).toBeTruthy();
		});

		test('shows placeholder when value is whitespace only', () => {
			render(TextVisualizer, { props: { value: '   ', placeholder: 'No text provided' } });

			expect(screen.getByText('No text provided')).toBeTruthy();
		});

		test('shows prefix with placeholder when both provided', () => {
			render(TextVisualizer, {
				props: {
					value: undefined,
					prefix: 'Q:',
					placeholder: 'No question provided'
				}
			});

			expect(screen.getByText('Q:')).toBeTruthy();
			expect(screen.getByText('No question provided')).toBeTruthy();
		});
	});

	describe('styling and structure', () => {
		test('text is wrapped in paragraph element', () => {
			const { container } = render(TextVisualizer, { props: { value: 'Test text' } });

			const paragraph = container.querySelector('p');
			expect(paragraph).toBeTruthy();
			expect(paragraph?.textContent).toContain('Test text');
		});

		test('placeholder text uses italic styling', () => {
			const { container } = render(TextVisualizer, {
				props: {
					value: undefined,
					placeholder: 'No text provided'
				}
			});

			const emElement = container.querySelector('em');
			expect(emElement).toBeTruthy();
			expect(emElement?.textContent).toBe('No text provided');
		});
	});
});
