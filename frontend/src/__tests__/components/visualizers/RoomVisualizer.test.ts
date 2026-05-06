/**
 * Unit tests for RoomVisualizer component
 * Tests that the room visualizer renders correctly for different room values
 */

import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import RoomVisualizer from '$lib/components/visualizers/RoomVisualizer.svelte';

describe('RoomVisualizer', () => {
	describe('renders correctly with valid room', () => {
		test('displays room name when provided', () => {
			const { container } = render(RoomVisualizer, { props: { value: 'kitchen' } });
			
			expect(container.textContent).toContain('kitchen');
		});

		test('displays location pin emoji', () => {
			const { container } = render(RoomVisualizer, { props: { value: 'living room' } });
			
			expect(container.textContent).toContain('📍');
		});

		test('has room-visualizer container class', () => {
			const { container } = render(RoomVisualizer, { props: { value: 'bedroom' } });
			
			expect(container.querySelector('.room-visualizer')).toBeTruthy();
		});
	});

	describe('handles various room names', () => {
		const roomNames = [
			'kitchen',
			'living room',
			'bedroom',
			'bathroom',
			'office',
			'garage',
			'basement',
			'hallway',
			'dining room',
			'unknown room'
		];

		test.each(roomNames)('displays room "%s" correctly', (room) => {
			const { container } = render(RoomVisualizer, { props: { value: room } });
			
			expect(container.textContent).toContain(room);
		});
	});

	describe('handles empty/undefined values', () => {
		test('shows placeholder when value is undefined', () => {
			const { container } = render(RoomVisualizer, { props: { value: undefined } });
			
			expect(container.textContent).toContain('No room specified');
		});

		test('shows placeholder when value is empty string', () => {
			const { container } = render(RoomVisualizer, { props: { value: '' } });
			
			expect(container.textContent).toContain('No room specified');
		});

		test('shows placeholder when value is whitespace only', () => {
			const { container } = render(RoomVisualizer, { props: { value: '   ' } });
			
			expect(container.textContent).toContain('No room specified');
		});
	});

	describe('styling and structure', () => {
		test('room with value renders with background styling', () => {
			const { container } = render(RoomVisualizer, { props: { value: 'kitchen' } });

			const span = container.querySelector('span');
			expect(span?.className).toContain('bg-secondary');
		});

		test('placeholder uses italic styling', () => {
			const { container } = render(RoomVisualizer, { props: { value: undefined } });
			
			const span = container.querySelector('span');
			expect(span?.className).toContain('italic');
		});

		test('room is rendered in a span element', () => {
			const { container } = render(RoomVisualizer, { props: { value: 'kitchen' } });
			
			const span = container.querySelector('span');
			expect(span).toBeTruthy();
			expect(span?.textContent).toContain('kitchen');
		});
	});
});
