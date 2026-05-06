/**
 * Unit tests for QuestionTimeSpanVisualizer component
 * Tests that the question time span visualizer renders correctly 
 * and distinguishes from regular time span
 */

import { describe, test, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import QuestionTimeSpanVisualizer from '$lib/components/visualizers/QuestionTimeSpanVisualizer.svelte';

describe('QuestionTimeSpanVisualizer', () => {
	describe('renders correctly with valid time span', () => {
		test('displays start and end time when both provided', () => {
			render(QuestionTimeSpanVisualizer, { 
				props: { value: { start: '00:02', end: '00:08' } } 
			});
			
			expect(screen.getByText('00:02')).toBeTruthy();
			expect(screen.getByText('00:08')).toBeTruthy();
		});

		test('displays question icon emoji to distinguish from regular time span', () => {
			render(QuestionTimeSpanVisualizer, { 
				props: { value: { start: '00:02', end: '00:08' } } 
			});
			
			expect(screen.getByText('❓')).toBeTruthy();
		});

		test('displays separator between times', () => {
			render(QuestionTimeSpanVisualizer, { 
				props: { value: { start: '00:02', end: '00:08' } } 
			});
			
			expect(screen.getByText('-')).toBeTruthy();
		});

		test('has question-time-span-visualizer container class', () => {
			const { container } = render(QuestionTimeSpanVisualizer, { 
				props: { value: { start: '00:00', end: '00:10' } } 
			});
			
			expect(container.querySelector('.question-time-span-visualizer')).toBeTruthy();
		});
	});

	describe('handles partial time span data', () => {
		test('shows placeholder for missing start time', () => {
			const { container } = render(QuestionTimeSpanVisualizer, { 
				props: { value: { end: '00:08' } } 
			});
			
			expect(container.textContent).toContain('??:??');
			expect(container.textContent).toContain('00:08');
		});

		test('shows placeholder for missing end time', () => {
			const { container } = render(QuestionTimeSpanVisualizer, { 
				props: { value: { start: '00:02' } } 
			});
			
			expect(container.textContent).toContain('00:02');
			expect(container.textContent).toContain('??:??');
		});
	});

	describe('handles empty/undefined values', () => {
		test('shows fallback message when value is undefined', () => {
			const { container } = render(QuestionTimeSpanVisualizer, { props: { value: undefined } });
			
			expect(container.textContent).toContain('No question time specified');
		});

		test('shows fallback when both start and end are undefined', () => {
			const { container } = render(QuestionTimeSpanVisualizer, { 
				props: { value: { start: undefined, end: undefined } } 
			});
			
			expect(container.textContent).toContain('No question time specified');
		});
	});

	describe('click interaction', () => {
		test('calls onSeek with start time when clicked', async () => {
			const mockOnSeek = vi.fn();
			render(QuestionTimeSpanVisualizer, { 
				props: { 
					value: { start: '00:02', end: '00:08' },
					onSeek: mockOnSeek
				} 
			});
			
			const button = screen.getByRole('button');
			await fireEvent.click(button);
			
			expect(mockOnSeek).toHaveBeenCalledWith('00:02');
		});

		test('does not call onSeek when no start time', async () => {
			const mockOnSeek = vi.fn();
			render(QuestionTimeSpanVisualizer, { 
				props: { 
					value: { end: '00:08' },
					onSeek: mockOnSeek
				} 
			});
			
			const button = screen.getByRole('button');
			await fireEvent.click(button);
			
			expect(mockOnSeek).not.toHaveBeenCalled();
		});

		test('button is clickable when onSeek and start time are provided', () => {
			const mockOnSeek = vi.fn();
			const { container } = render(QuestionTimeSpanVisualizer, { 
				props: { 
					value: { start: '00:02', end: '00:08' },
					onSeek: mockOnSeek
				} 
			});
			
			const button = container.querySelector('button');
			expect(button?.className).toContain('cursor-pointer');
		});
	});

	describe('styling differentiates from TimeSpanVisualizer', () => {
		test('has blue background styling for question context', () => {
			const { container } = render(QuestionTimeSpanVisualizer, {
				props: { value: { start: '00:02', end: '00:08' } }
			});

			const button = container.querySelector('button');
			expect(button?.className).toContain('bg-secondary');
			expect(button?.className).toContain('text-foreground');
		});

		test('has title attribute explaining purpose', () => {
			const mockOnSeek = vi.fn();
			const { container } = render(QuestionTimeSpanVisualizer, { 
				props: { 
					value: { start: '00:02', end: '00:08' },
					onSeek: mockOnSeek
				} 
			});
			
			const button = container.querySelector('button');
			expect(button?.getAttribute('title')).toContain('Click to seek to question time');
		});
	});

	describe('structure matches expected output', () => {
		test('renders as button element when time span exists', () => {
			const { container } = render(QuestionTimeSpanVisualizer, { 
				props: { value: { start: '00:02', end: '00:08' } } 
			});
			
			expect(container.querySelector('button')).toBeTruthy();
		});

		test('renders as span when no time span', () => {
			const { container } = render(QuestionTimeSpanVisualizer, { 
				props: { value: undefined } 
			});
			
			expect(container.querySelector('span')).toBeTruthy();
			expect(container.querySelector('button')).toBeFalsy();
		});
	});
});
