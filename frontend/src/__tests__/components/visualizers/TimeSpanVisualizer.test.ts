/**
 * Unit tests for TimeSpanVisualizer component
 * Tests that the time span visualizer renders correctly and handles interactions
 */

import { describe, test, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import TimeSpanVisualizer from '$lib/components/visualizers/TimeSpanVisualizer.svelte';

describe('TimeSpanVisualizer', () => {
	describe('renders correctly with valid time span', () => {
		test('displays start and end time when both provided', () => {
			render(TimeSpanVisualizer, { 
				props: { value: { start: '00:05', end: '00:15' } } 
			});
			
			expect(screen.getByText('00:05')).toBeTruthy();
			expect(screen.getByText('00:15')).toBeTruthy();
		});

		test('displays time icon emoji', () => {
			render(TimeSpanVisualizer, { 
				props: { value: { start: '00:05', end: '00:15' } } 
			});
			
			expect(screen.getByText('⏱️')).toBeTruthy();
		});

		test('displays separator between times', () => {
			render(TimeSpanVisualizer, { 
				props: { value: { start: '00:05', end: '00:15' } } 
			});
			
			expect(screen.getByText('-')).toBeTruthy();
		});

		test('has time-span-visualizer container class', () => {
			const { container } = render(TimeSpanVisualizer, { 
				props: { value: { start: '00:00', end: '00:10' } } 
			});
			
			expect(container.querySelector('.time-span-visualizer')).toBeTruthy();
		});
	});

	describe('handles partial time span data', () => {
		test('shows placeholder for missing start time', () => {
			const { container } = render(TimeSpanVisualizer, { 
				props: { value: { end: '00:15' } } 
			});
			
			expect(container.textContent).toContain('??:??');
			expect(container.textContent).toContain('00:15');
		});

		test('shows placeholder for missing end time', () => {
			const { container } = render(TimeSpanVisualizer, { 
				props: { value: { start: '00:05' } } 
			});
			
			expect(container.textContent).toContain('00:05');
			expect(container.textContent).toContain('??:??');
		});
	});

	describe('handles empty/undefined values', () => {
		test('shows fallback message when value is undefined', () => {
			const { container } = render(TimeSpanVisualizer, { props: { value: undefined } });
			
			expect(container.textContent).toContain('No time specified');
		});

		test('shows fallback when both start and end are undefined', () => {
			const { container } = render(TimeSpanVisualizer, { 
				props: { value: { start: undefined, end: undefined } } 
			});
			
			expect(container.textContent).toContain('No time specified');
		});
	});

	describe('click interaction', () => {
		test('calls onSeek with start time when clicked', async () => {
			const mockOnSeek = vi.fn();
			render(TimeSpanVisualizer, { 
				props: { 
					value: { start: '00:05', end: '00:15' },
					onSeek: mockOnSeek
				} 
			});
			
			const button = screen.getByRole('button');
			await fireEvent.click(button);
			
			expect(mockOnSeek).toHaveBeenCalledWith('00:05');
		});

		test('does not call onSeek when no start time', async () => {
			const mockOnSeek = vi.fn();
			render(TimeSpanVisualizer, { 
				props: { 
					value: { end: '00:15' },
					onSeek: mockOnSeek
				} 
			});
			
			const button = screen.getByRole('button');
			await fireEvent.click(button);
			
			expect(mockOnSeek).not.toHaveBeenCalled();
		});

		test('button is clickable when onSeek and start time are provided', () => {
			const mockOnSeek = vi.fn();
			const { container } = render(TimeSpanVisualizer, { 
				props: { 
					value: { start: '00:05', end: '00:15' },
					onSeek: mockOnSeek
				} 
			});
			
			const button = container.querySelector('button');
			expect(button?.className).toContain('cursor-pointer');
		});
	});

	describe('styling and structure', () => {
		test('renders as button element when time span exists', () => {
			const { container } = render(TimeSpanVisualizer, { 
				props: { value: { start: '00:05', end: '00:15' } } 
			});
			
			expect(container.querySelector('button')).toBeTruthy();
		});

		test('renders as span when no time span', () => {
			const { container } = render(TimeSpanVisualizer, { 
				props: { value: undefined } 
			});
			
			expect(container.querySelector('span')).toBeTruthy();
			expect(container.querySelector('button')).toBeFalsy();
		});
	});

	describe('cross-video reference display', () => {
		test('shows video name when answer is from different video', () => {
			const { container } = render(TimeSpanVisualizer, { 
				props: { 
					value: { start: '00:05', end: '00:15' },
					videoPath: '/videos/other_video.mp4',
					currentVideoPath: '/videos/current_video.mp4'
				} 
			});
			
			expect(container.textContent).toContain('other_video.mp4');
		});

		test('does not show video name when answer is from same video', () => {
			const { container } = render(TimeSpanVisualizer, { 
				props: { 
					value: { start: '00:05', end: '00:15' },
					videoPath: '/videos/same_video.mp4',
					currentVideoPath: '/videos/same_video.mp4'
				} 
			});
			
			expect(container.textContent).not.toContain('📹');
		});

		test('does not show video name when videoPath is undefined', () => {
			const { container } = render(TimeSpanVisualizer, { 
				props: { 
					value: { start: '00:05', end: '00:15' },
					currentVideoPath: '/videos/current_video.mp4'
				} 
			});
			
			expect(container.textContent).not.toContain('📹');
		});
	});
});
