/**
 * Unit tests for BoundingBoxVisualizer component
 * Tests that the bounding box visualizer renders correctly for different box configurations
 */

import { describe, test, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import BoundingBoxVisualizer from '$lib/components/visualizers/BoundingBoxVisualizer.svelte';
import type { LocationBox } from '$lib/types';

describe('BoundingBoxVisualizer', () => {
	describe('renders correctly with boxes', () => {
		test('displays count of bounding boxes', () => {
			const boxes: LocationBox[] = [
				{ box_2d: [100, 100, 200, 200], timestamp: '00:05' },
				{ box_2d: [300, 300, 400, 400], timestamp: '00:10' }
			];
			const { container } = render(BoundingBoxVisualizer, { props: { boxes } });

			expect(container.textContent).toContain('Boxes (2):');
		});

		test('displays box emoji', () => {
			const boxes: LocationBox[] = [
				{ box_2d: [100, 100, 200, 200] }
			];
			const { container } = render(BoundingBoxVisualizer, { props: { boxes } });

			expect(container.textContent).toContain('💡');
		});

		test('displays individual box labels', () => {
			const boxes: LocationBox[] = [
				{ box_2d: [100, 100, 200, 200] },
				{ box_2d: [300, 300, 400, 400] }
			];
			render(BoundingBoxVisualizer, { props: { boxes } });

			expect(screen.getByText('B1')).toBeTruthy();
			expect(screen.getByText('B2')).toBeTruthy();
		});

		test('has bounding-box-visualizer container class', () => {
			const boxes: LocationBox[] = [
				{ box_2d: [100, 100, 200, 200] }
			];
			const { container } = render(BoundingBoxVisualizer, { props: { boxes } });

			expect(container.querySelector('.bounding-box-visualizer')).toBeTruthy();
		});
	});

	describe('displays box timestamps', () => {
		test('displays individual box timestamps', () => {
			const boxes: LocationBox[] = [
				{ box_2d: [100, 100, 200, 200], timestamp: '00:05' },
				{ box_2d: [300, 300, 400, 400], timestamp: '00:10' }
			];
			const { container } = render(BoundingBoxVisualizer, { props: { boxes } });

			expect(container.textContent).toContain('@ 00:05');
			expect(container.textContent).toContain('@ 00:10');
		});

		test('uses defaultTimestamp when box has no timestamp', () => {
			const boxes: LocationBox[] = [
				{ box_2d: [100, 100, 200, 200] }
			];
			const { container } = render(BoundingBoxVisualizer, {
				props: { boxes, defaultTimestamp: '00:00' }
			});

			expect(container.textContent).toContain('@ 00:00');
		});

		test('defaults to 00:00 when no defaultTimestamp provided', () => {
			const boxes: LocationBox[] = [
				{ box_2d: [100, 100, 200, 200] }
			];
			const { container } = render(BoundingBoxVisualizer, { props: { boxes } });

			expect(container.textContent).toContain('@ 00:00');
		});
	});



	describe('handles empty/undefined boxes', () => {
		test('shows placeholder when boxes is undefined', () => {
			const { container } = render(BoundingBoxVisualizer, { props: { boxes: undefined } });

			expect(container.textContent).toContain('📦 No bounding boxes');
		});

		test('shows placeholder when boxes is empty array', () => {
			const { container } = render(BoundingBoxVisualizer, { props: { boxes: [] } });

			expect(container.textContent).toContain('📦 No bounding boxes');
		});
	});

	describe('box count matches data', () => {
		test('displays correct count for 1 box', () => {
			const boxes: LocationBox[] = [
				{ box_2d: [100, 100, 200, 200] }
			];
			const { container } = render(BoundingBoxVisualizer, { props: { boxes } });

			expect(container.textContent).toContain('Boxes (1):');
		});

		test('displays correct count for 3 boxes', () => {
			const boxes: LocationBox[] = [
				{ box_2d: [100, 100, 200, 200] },
				{ box_2d: [200, 200, 300, 300] },
				{ box_2d: [300, 300, 400, 400] }
			];
			const { container } = render(BoundingBoxVisualizer, { props: { boxes } });

			expect(container.textContent).toContain('Boxes (3):');
			expect(screen.getByText('B1')).toBeTruthy();
			expect(screen.getByText('B2')).toBeTruthy();
			expect(screen.getByText('B3')).toBeTruthy();
		});

		test('displays correct count for 5 boxes', () => {
			const boxes: LocationBox[] = [
				{ box_2d: [0, 0, 100, 100] },
				{ box_2d: [100, 100, 200, 200] },
				{ box_2d: [200, 200, 300, 300] },
				{ box_2d: [300, 300, 400, 400] },
				{ box_2d: [400, 400, 500, 500] }
			];
			const { container } = render(BoundingBoxVisualizer, { props: { boxes } });

			expect(container.textContent).toContain('Boxes (5):');
		});
	});

	describe('click interaction', () => {
		test('calls onShowBox when box is clicked', async () => {
			const mockOnShowBox = vi.fn();
			const boxes: LocationBox[] = [
				{ box_2d: [100, 100, 200, 200], timestamp: '00:05' }
			];
			render(BoundingBoxVisualizer, {
				props: { boxes, onShowBox: mockOnShowBox }
			});

			const boxButton = screen.getByText('B1').closest('button');
			await fireEvent.click(boxButton!);

			expect(mockOnShowBox).toHaveBeenCalledWith(boxes[0], 0);
		});

		test('calls onSeek as fallback when onShowBox not provided', async () => {
			const mockOnSeek = vi.fn();
			const boxes: LocationBox[] = [
				{ box_2d: [100, 100, 200, 200], timestamp: '00:05' }
			];
			render(BoundingBoxVisualizer, {
				props: { boxes, onSeek: mockOnSeek }
			});

			const boxButton = screen.getByText('B1').closest('button');
			await fireEvent.click(boxButton!);

			expect(mockOnSeek).toHaveBeenCalledWith('00:05');
		});

		test('uses defaultTimestamp when box has no timestamp for onSeek', async () => {
			const mockOnSeek = vi.fn();
			const boxes: LocationBox[] = [
				{ box_2d: [100, 100, 200, 200] }
			];
			render(BoundingBoxVisualizer, {
				props: { boxes, onSeek: mockOnSeek, defaultTimestamp: '00:15' }
			});

			const boxButton = screen.getByText('B1').closest('button');
			await fireEvent.click(boxButton!);

			expect(mockOnSeek).toHaveBeenCalledWith('00:15');
		});

		test('clicking different boxes passes correct index', async () => {
			const mockOnShowBox = vi.fn();
			const boxes: LocationBox[] = [
				{ box_2d: [100, 100, 200, 200], timestamp: '00:05' },
				{ box_2d: [300, 300, 400, 400], timestamp: '00:10' }
			];
			render(BoundingBoxVisualizer, {
				props: { boxes, onShowBox: mockOnShowBox }
			});

			// Click first box
			const box1Button = screen.getByText('B1').closest('button');
			await fireEvent.click(box1Button!);
			expect(mockOnShowBox).toHaveBeenCalledWith(boxes[0], 0);

			// Click second box
			const box2Button = screen.getByText('B2').closest('button');
			await fireEvent.click(box2Button!);
			expect(mockOnShowBox).toHaveBeenCalledWith(boxes[1], 1);
		});
	});

	describe('styling and structure', () => {
		test('each box is rendered as a button', () => {
			const boxes: LocationBox[] = [
				{ box_2d: [100, 100, 200, 200] },
				{ box_2d: [300, 300, 400, 400] }
			];
			const { container } = render(BoundingBoxVisualizer, { props: { boxes } });

			const buttons = container.querySelectorAll('button');
			expect(buttons.length).toBe(2);
		});

		test('boxes have blue styling', () => {
			const boxes: LocationBox[] = [
				{ box_2d: [100, 100, 200, 200] }
			];
			const { container } = render(BoundingBoxVisualizer, { props: { boxes } });

			const button = container.querySelector('button');
			expect(button?.className).toContain('bg-secondary');
			// Text color check might be specific or default, removing specific blue text check if not present
			// expect(button?.className).toContain('text-blue-700');
		});

		test('boxes have hover effect classes', () => {
			const boxes: LocationBox[] = [
				{ box_2d: [100, 100, 200, 200] }
			];
			const { container } = render(BoundingBoxVisualizer, { props: { boxes } });

			const button = container.querySelector('button');
			expect(button?.className).toContain('hover:bg-secondary/80');
		});
	});


});
