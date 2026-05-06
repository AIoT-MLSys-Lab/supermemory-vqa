/**
 * Unit tests for HumanReviewVisualizer component
 * Tests that the human review visualizer renders correctly for different review states
 */

import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import HumanReviewVisualizer from '$lib/components/visualizers/HumanReviewVisualizer.svelte';
import type { HumanReview } from '$lib/types';

describe('HumanReviewVisualizer', () => {
	describe('renders correctly for accepted status', () => {
		test('displays accepted badge text', () => {
			const review: HumanReview = { status: 'accepted' };
			render(HumanReviewVisualizer, { props: { value: review } });

			expect(screen.getByText('✓ Accepted')).toBeTruthy();
		});

		test('displays accepted with reviewed boolean (legacy format)', () => {
			const review: HumanReview = { reviewed: true };
			render(HumanReviewVisualizer, { props: { value: review } });

			expect(screen.getByText('✓ Accepted')).toBeTruthy();
		});
	});

	describe('renders correctly for rejected status', () => {
		test('displays rejected badge text', () => {
			const review: HumanReview = { status: 'rejected' };
			render(HumanReviewVisualizer, { props: { value: review } });

			expect(screen.getByText('✗ Rejected')).toBeTruthy();
		});
	});

	describe('renders correctly for pending status', () => {
		test('displays pending badge text for explicit pending status', () => {
			const review: HumanReview = { status: 'pending' };
			render(HumanReviewVisualizer, { props: { value: review } });

			expect(screen.getByText('⏳ Pending')).toBeTruthy();
		});

		test('displays pending badge when value is undefined', () => {
			render(HumanReviewVisualizer, { props: { value: undefined } });

			expect(screen.getByText('⏳ Pending')).toBeTruthy();
		});

		test('displays pending badge when value is empty object', () => {
			render(HumanReviewVisualizer, { props: { value: {} } });

			expect(screen.getByText('⏳ Pending')).toBeTruthy();
		});
	});

	describe('displays review comments', () => {
		test('displays comment when provided', () => {
			const review: HumanReview = {
				status: 'accepted',
				comment: 'This annotation is accurate.'
			};
			render(HumanReviewVisualizer, { props: { value: review } });

			expect(screen.getByText('Review Comment:')).toBeTruthy();
			expect(screen.getByText('This annotation is accurate.')).toBeTruthy();
		});

		test('does not display comment section when no comment', () => {
			const review: HumanReview = { status: 'accepted' };
			const { container } = render(HumanReviewVisualizer, { props: { value: review } });

			expect(container.querySelector('.bg-gray-50')).toBeFalsy();
		});

		test('displays comment with rejected status', () => {
			const review: HumanReview = {
				status: 'rejected',
				comment: 'Incorrect bounding box location.'
			};
			render(HumanReviewVisualizer, { props: { value: review } });

			expect(screen.getByText('✗ Rejected')).toBeTruthy();
			expect(screen.getByText('Incorrect bounding box location.')).toBeTruthy();
		});
	});

	describe('has proper container structure', () => {
		test('has human-review-visualizer container class', () => {
			const { container } = render(HumanReviewVisualizer, {
				props: { value: { status: 'pending' } }
			});

			expect(container.querySelector('.human-review-visualizer')).toBeTruthy();
		});
	});

	describe('status determination priority', () => {
		test('status field takes precedence over reviewed field', () => {
			// If status is 'rejected' but reviewed is true, status should win
			const review: HumanReview = {
				status: 'rejected',
				reviewed: true
			};
			render(HumanReviewVisualizer, { props: { value: review } });

			expect(screen.getByText('✗ Rejected')).toBeTruthy();
		});

		test('reviewed true maps to accepted when no status', () => {
			const review: HumanReview = { reviewed: true };
			render(HumanReviewVisualizer, { props: { value: review } });

			expect(screen.getByText('✓ Accepted')).toBeTruthy();
		});

		test('reviewed false maps to pending when no status', () => {
			const review: HumanReview = { reviewed: false };
			render(HumanReviewVisualizer, { props: { value: review } });

			expect(screen.getByText('⏳ Pending')).toBeTruthy();
		});
	});

	describe('additional review metadata', () => {
		test('handles review with reviewer info', () => {
			const review: HumanReview = {
				status: 'accepted',
				reviewer: 'John Doe',
				timestamp: '2024-01-15T10:30:00Z'
			};
			// Component should render without error even with extra fields
			const { container } = render(HumanReviewVisualizer, { props: { value: review } });

			expect(container.querySelector('.human-review-visualizer')).toBeTruthy();
			expect(screen.getByText('✓ Accepted')).toBeTruthy();
		});
	});
});
