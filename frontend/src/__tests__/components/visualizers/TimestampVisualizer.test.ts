/**
 * Unit tests for TimestampVisualizer component
 * Tests that the timestamp visualizer renders correctly and handles interactions
 */

import { describe, test, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import TimestampVisualizer from '$lib/components/visualizers/TimestampVisualizer.svelte';

describe('TimestampVisualizer', () => {
	describe('renders correctly with valid timestamp', () => {
		test('displays timestamp when provided', () => {
			render(TimestampVisualizer, {
				props: { value: '00:05' }
			});

			expect(screen.getByText('00:05')).toBeTruthy();
		});

		test('displays timestamp icon emoji', () => {
			render(TimestampVisualizer, {
				props: { value: '00:05' }
			});

			expect(screen.getByText('📍')).toBeTruthy();
		});

		test('has timestamp-visualizer container class', () => {
			const { container } = render(TimestampVisualizer, {
				props: { value: '00:10' }
			});

			expect(container.querySelector('.timestamp-visualizer')).toBeTruthy();
		});
	});

	describe('handles empty/undefined values', () => {
		test('shows fallback message when value is undefined', () => {
			const { container } = render(TimestampVisualizer, { props: { value: undefined } });

			expect(container.textContent).toContain('No time specified');
		});

		test('shows fallback when value is empty string', () => {
			const { container } = render(TimestampVisualizer, {
				props: { value: '' }
			});

			expect(container.textContent).toContain('No time specified');
		});
	});

	describe('click interaction', () => {
		test('calls onSeek with timestamp when clicked', async () => {
			const mockOnSeek = vi.fn();
			render(TimestampVisualizer, {
				props: {
					value: '00:05',
					onSeek: mockOnSeek
				}
			});

			const button = screen.getByRole('button');
			await fireEvent.click(button);

			expect(mockOnSeek).toHaveBeenCalledWith('00:05');
		});

		test('does not call onSeek when no timestamp', async () => {
			const mockOnSeek = vi.fn();
			render(TimestampVisualizer, {
				props: {
					value: undefined,
					onSeek: mockOnSeek
				}
			});

			// No button should exist when value is undefined
			expect(screen.queryByRole('button')).toBeFalsy();
			expect(mockOnSeek).not.toHaveBeenCalled();
		});

		test('renders as button when onSeek provided', () => {
			const mockOnSeek = vi.fn();
			render(TimestampVisualizer, {
				props: {
					value: '00:05',
					onSeek: mockOnSeek
				}
			});

			expect(screen.getByRole('button')).toBeTruthy();
		});
	});

	describe('video path handling', () => {
		test('shows video name when from different video', () => {
			const { container } = render(TimestampVisualizer, {
				props: {
					value: '00:05',
					videoPath: '/path/to/video.mp4',
					currentVideoPath: '/path/to/current.mp4'
				}
			});

			expect(container.textContent).toContain('video.mp4');
		});

		test('does not show video name when from same video', () => {
			const { container } = render(TimestampVisualizer, {
				props: {
					value: '00:05',
					videoPath: '/path/to/video.mp4',
					currentVideoPath: '/path/to/video.mp4'
				}
			});

			expect(container.textContent).not.toContain('📹');
		});

		test('does not show video name when no videoPath', () => {
			const { container } = render(TimestampVisualizer, {
				props: {
					value: '00:05',
					currentVideoPath: '/path/to/current.mp4'
				}
			});

			expect(container.textContent).not.toContain('📹');
		});
	});
});
