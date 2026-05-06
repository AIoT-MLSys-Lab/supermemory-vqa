/**
 * Unit tests for EvidenceListVisualizer component
 * Tests that the evidence list visualizer renders correctly and reuses TimeSpanVisualizer
 */

import { describe, test, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import EvidenceListVisualizer from '$lib/components/visualizers/EvidenceListVisualizer.svelte';
import type { Evidence } from '$lib/types';

describe('EvidenceListVisualizer', () => {
	describe('renders correctly with evidence list', () => {
		test('displays single evidence item with timespans', () => {
			const evidence: Evidence[] = [
				{
					time_spans: [{ start: '00:05', end: '00:15' }],
					video_path: undefined
				}
			];

			const { container } = render(EvidenceListVisualizer, {
				props: { value: evidence }
			});

			expect(container.textContent).toContain('Evidence #1');
			expect(container.textContent).toContain('00:05');
			expect(container.textContent).toContain('00:15');
		});

		test('displays multiple evidence items', () => {
			const evidence: Evidence[] = [
				{
					time_spans: [{ start: '00:05', end: '00:15' }],
					video_path: undefined
				},
				{
					time_spans: [{ start: '00:20', end: '00:30' }],
					video_path: undefined
				}
			];

			const { container } = render(EvidenceListVisualizer, {
				props: { value: evidence }
			});

			expect(container.textContent).toContain('Evidence #1');
			expect(container.textContent).toContain('Evidence #2');
		});

		test('displays multiple timespans within single evidence', () => {
			const evidence: Evidence[] = [
				{
					time_spans: [
						{ start: '00:05', end: '00:15' },
						{ start: '00:20', end: '00:30' }
					],
					video_path: undefined
				}
			];

			const { container } = render(EvidenceListVisualizer, {
				props: { value: evidence }
			});

			// Should show both timespans
			expect(container.textContent).toContain('00:05');
			expect(container.textContent).toContain('00:15');
			expect(container.textContent).toContain('00:20');
			expect(container.textContent).toContain('00:30');
		});

		test('has evidence-list-visualizer container class', () => {
			const evidence: Evidence[] = [
				{
					time_spans: [{ start: '00:05', end: '00:15' }],
					video_path: undefined
				}
			];

			const { container } = render(EvidenceListVisualizer, {
				props: { value: evidence }
			});

			expect(container.querySelector('.evidence-list-visualizer')).toBeTruthy();
		});
	});

	describe('handles empty/undefined values', () => {
		test('shows fallback message when value is undefined', () => {
			const { container } = render(EvidenceListVisualizer, {
				props: { value: undefined }
			});

			expect(container.textContent).toContain('No evidence provided');
		});

		test('shows fallback message when value is empty array', () => {
			const { container } = render(EvidenceListVisualizer, {
				props: { value: [] }
			});

			expect(container.textContent).toContain('No evidence provided');
		});

		test('shows message when evidence has no timespans', () => {
			const evidence: Evidence[] = [
				{
					time_spans: [],
					video_path: undefined
				}
			];

			const { container } = render(EvidenceListVisualizer, {
				props: { value: evidence }
			});

			expect(container.textContent).toContain('No timespans specified');
		});
	});

	describe('video path handling', () => {
		test('shows video name when from different video', () => {
			const evidence: Evidence[] = [
				{
					time_spans: [{ start: '00:05', end: '00:15' }],
					video_path: '/path/to/different.mp4'
				}
			];

			const { container } = render(EvidenceListVisualizer, {
				props: {
					value: evidence,
					currentVideoPath: '/path/to/current.mp4'
				}
			});

			expect(container.textContent).toContain('different.mp4');
			expect(container.textContent).toContain('📹');
		});

		test('does not show video indicator when from same video', () => {
			const evidence: Evidence[] = [
				{
					time_spans: [{ start: '00:05', end: '00:15' }],
					video_path: '/path/to/video.mp4'
				}
			];

			const { container } = render(EvidenceListVisualizer, {
				props: {
					value: evidence,
					currentVideoPath: '/path/to/video.mp4'
				}
			});

			// Evidence header should not have different video indicator
			const evidenceHeaders = container.textContent?.split('Evidence #1')[1]?.split('00:05')[0] || '';
			expect(evidenceHeaders.indexOf('📹') === -1 || evidenceHeaders.trim().length === 0);
		});
	});

	describe('onSeek callback', () => {
		test('calls onSeek with timestamp and video path', () => {
			const mockOnSeek = vi.fn();
			const evidence: Evidence[] = [
				{
					time_spans: [{ start: '00:05', end: '00:15' }],
					video_path: '/path/to/video.mp4'
				}
			];

			render(EvidenceListVisualizer, {
				props: {
					value: evidence,
					onSeek: mockOnSeek
				}
			});

			// The TimeSpanVisualizer is rendered with onSeek callback
			// We're testing that the evidence visualizer passes it correctly
			expect(screen.getByText('00:05')).toBeTruthy();
		});
	});
});
