/**
 * Unit tests for AnnotationItem component
 * Tests that AnnotationItem renders correctly based on different annotation data structures
 * and ensures all required sub-components are present
 */

import { describe, test, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import AnnotationItem from '$lib/components/app/AnnotationItem.svelte';
import type { Annotation, LocationBox } from '$lib/types';

// Mock the getReviewStatus function from stores
vi.mock('$lib/stores', () => ({
	getReviewStatus: (review: { status?: string; reviewed?: boolean } | undefined) => {
		if (!review) return 'pending';
		if (review.status) return review.status;
		return review.reviewed ? 'accepted' : 'pending';
	}
}));

describe('AnnotationItem', () => {
	const baseAnnotation: Annotation = {
		question: 'What is on the table?',
		answer: 'A red apple',
		skill: 'object_location_memory',
		time_span: { start: '00:05', end: '00:15' },
		room: 'kitchen',
		modalities: ['visual'],
		human_review: { status: 'pending' }
	};

	describe('renders required sub-components', () => {
		test('renders question text with Q: prefix (via TextVisualizer)', () => {
			render(AnnotationItem, {
				props: { annotation: baseAnnotation, index: 0 }
			});

			expect(screen.getByText('What is on the table?')).toBeTruthy();
			expect(screen.getByText('Q:')).toBeTruthy();
		});

		test('renders answer text with A: prefix (via TextVisualizer)', () => {
			render(AnnotationItem, {
				props: { annotation: baseAnnotation, index: 0 }
			});

			expect(screen.getByText('A red apple')).toBeTruthy();
			expect(screen.getByText('A:')).toBeTruthy();
		});

		test('renders SkillVisualizer with skill type', () => {
			render(AnnotationItem, {
				props: { annotation: baseAnnotation, index: 0 }
			});

			expect(screen.getByText('Object Location')).toBeTruthy();
		});

		test('renders TimeSpanVisualizer with time span', () => {
			render(AnnotationItem, {
				props: { annotation: baseAnnotation, index: 0 }
			});

			expect(screen.getByText('⏱️')).toBeTruthy();
			expect(screen.getByText('00:05')).toBeTruthy();
			expect(screen.getByText('00:15')).toBeTruthy();
		});

		test('renders RoomVisualizer with room name', () => {
			const { container } = render(AnnotationItem, {
				props: { annotation: baseAnnotation, index: 0 }
			});

			expect(container.textContent).toContain('📍');
			expect(container.textContent).toContain('kitchen');
		});

		test('renders ModalitiesVisualizer with modalities', () => {
			const { container } = render(AnnotationItem, {
				props: { annotation: baseAnnotation, index: 0 }
			});

			expect(container.textContent).toContain('visual');
		});

		test('renders HumanReviewVisualizer with review status', () => {
			render(AnnotationItem, {
				props: { annotation: baseAnnotation, index: 0 }
			});

			expect(screen.getByText('⏳ Pending')).toBeTruthy();
		});

		test('renders annotation index number', () => {
			render(AnnotationItem, {
				props: { annotation: baseAnnotation, index: 0 }
			});

			expect(screen.getByText('#1')).toBeTruthy();
		});

		test('renders action buttons', () => {
			render(AnnotationItem, {
				props: { annotation: baseAnnotation, index: 0 }
			});

			expect(screen.getByRole('button', { name: 'Play' })).toBeTruthy();
			expect(screen.getByRole('button', { name: 'Edit' })).toBeTruthy();
			expect(screen.getByRole('button', { name: 'Review' })).toBeTruthy();
			expect(screen.getByRole('button', { name: 'Add New Box' })).toBeTruthy();
			expect(screen.getByRole('button', { name: 'Delete' })).toBeTruthy();
		});
	});

	describe('QuestionTimeSpan conditional rendering', () => {
		test('renders QuestionTimeSpanVisualizer when question_time_span is present', () => {
			const annotationWithQuestionTimeSpan: Annotation = {
				...baseAnnotation,
				question_time_span: { start: '00:02', end: '00:08' }
			};
			render(AnnotationItem, {
				props: { annotation: annotationWithQuestionTimeSpan, index: 0 }
			});

			// Question time span has ❓ emoji
			expect(screen.getByText('❓')).toBeTruthy();
			expect(screen.getByText('00:02')).toBeTruthy();
			expect(screen.getByText('00:08')).toBeTruthy();
		});

		test('does NOT render QuestionTimeSpanVisualizer when question_time_span is absent', () => {
			const annotationWithoutQuestionTimeSpan: Annotation = {
				...baseAnnotation,
				question_time_span: undefined
			};
			render(AnnotationItem, {
				props: { annotation: annotationWithoutQuestionTimeSpan, index: 0 }
			});

			// Should not have the ❓ emoji for question time span
			expect(screen.queryByText('❓')).toBeFalsy();
		});
	});

	describe('BoundingBoxVisualizer rendering', () => {
		test('renders BoundingBoxVisualizer when boxes are present', () => {
			const annotationWithBoxes: Annotation = {
				...baseAnnotation,
				location: {
					boxes: [
						{ box_2d: [100, 100, 200, 200], timestamp: '00:05' }
					]
				}
			};
			const { container } = render(AnnotationItem, {
				props: { annotation: annotationWithBoxes, index: 0 }
			});

			expect(container.textContent).toContain('💡');
			expect(container.textContent).toContain('Boxes (1):');
			expect(screen.getByText('B1')).toBeTruthy();
		});

		test('does NOT render BoundingBoxVisualizer when no boxes', () => {
			const annotationWithoutBoxes: Annotation = {
				...baseAnnotation,
				location: undefined
			};
			const { container } = render(AnnotationItem, {
				props: { annotation: annotationWithoutBoxes, index: 0 }
			});

			expect(container.textContent).not.toContain('Boxes');
		});

		test('box count matches data - 1 box', () => {
			const annotationWithOneBox: Annotation = {
				...baseAnnotation,
				location: {
					boxes: [
						{ box_2d: [100, 100, 200, 200], timestamp: '00:05' }
					]
				}
			};
			const { container } = render(AnnotationItem, {
				props: { annotation: annotationWithOneBox, index: 0 }
			});

			expect(container.textContent).toContain('Boxes (1):');
			expect(screen.getByText('B1')).toBeTruthy();
			expect(screen.queryByText('B2')).toBeFalsy();
		});

		test('box count matches data - 3 boxes', () => {
			const annotationWithThreeBoxes: Annotation = {
				...baseAnnotation,
				location: {
					boxes: [
						{ box_2d: [100, 100, 200, 200], timestamp: '00:05' },
						{ box_2d: [200, 200, 300, 300], timestamp: '00:07' },
						{ box_2d: [300, 300, 400, 400], timestamp: '00:09' }
					]
				}
			};
			const { container } = render(AnnotationItem, {
				props: { annotation: annotationWithThreeBoxes, index: 0 }
			});

			expect(container.textContent).toContain('Boxes (3):');
			expect(screen.getByText('B1')).toBeTruthy();
			expect(screen.getByText('B2')).toBeTruthy();
			expect(screen.getByText('B3')).toBeTruthy();
		});

		test('box count matches data - 5 boxes', () => {
			const boxes: LocationBox[] = [
				{ box_2d: [0, 0, 100, 100], timestamp: '00:01' },
				{ box_2d: [100, 100, 200, 200], timestamp: '00:02' },
				{ box_2d: [200, 200, 300, 300], timestamp: '00:03' },
				{ box_2d: [300, 300, 400, 400], timestamp: '00:04' },
				{ box_2d: [400, 400, 500, 500], timestamp: '00:05' }
			];
			const annotationWithFiveBoxes: Annotation = {
				...baseAnnotation,
				location: { boxes }
			};
			const { container } = render(AnnotationItem, {
				props: { annotation: annotationWithFiveBoxes, index: 0 }
			});

			expect(container.textContent).toContain('Boxes (5):');
		});
	});

	describe('selected state', () => {
		test('shows selected indicator when isSelected is true', () => {
			render(AnnotationItem, {
				props: { annotation: baseAnnotation, index: 0, isSelected: true }
			});

			expect(screen.getByText('Selected for drawing')).toBeTruthy();
		});

		test('does not show selected indicator when isSelected is false', () => {
			render(AnnotationItem, {
				props: { annotation: baseAnnotation, index: 0, isSelected: false }
			});

			expect(screen.queryByText('Selected for drawing')).toBeFalsy();
		});

		test('button text changes when selected', () => {
			render(AnnotationItem, {
				props: { annotation: baseAnnotation, index: 0, isSelected: true }
			});

			expect(screen.getByRole('button', { name: 'Selected' })).toBeTruthy();
			expect(screen.queryByRole('button', { name: 'Add New Box' })).toBeFalsy();
		});

		test('container has selected styling when isSelected', () => {
			const { container } = render(AnnotationItem, {
				props: { annotation: baseAnnotation, index: 0, isSelected: true }
			});

			const itemDiv = container.querySelector('div');
			expect(itemDiv?.className).toContain('ring-2');
			expect(itemDiv?.className).toContain('ring-primary');
			expect(itemDiv?.className).toContain('bg-primary/5');
		});
	});

	describe('review status variations', () => {
		test('shows Change Review button when already reviewed (accepted)', () => {
			const acceptedAnnotation: Annotation = {
				...baseAnnotation,
				human_review: { status: 'accepted' }
			};
			render(AnnotationItem, {
				props: { annotation: acceptedAnnotation, index: 0 }
			});

			expect(screen.getByRole('button', { name: 'Change Review' })).toBeTruthy();
		});

		test('shows Review button when pending', () => {
			const pendingAnnotation: Annotation = {
				...baseAnnotation,
				human_review: { status: 'pending' }
			};
			render(AnnotationItem, {
				props: { annotation: pendingAnnotation, index: 0 }
			});

			expect(screen.getByRole('button', { name: 'Review' })).toBeTruthy();
		});

		test('shows Change Review when rejected', () => {
			const rejectedAnnotation: Annotation = {
				...baseAnnotation,
				human_review: { status: 'rejected' }
			};
			render(AnnotationItem, {
				props: { annotation: rejectedAnnotation, index: 0 }
			});

			expect(screen.getByRole('button', { name: 'Change Review' })).toBeTruthy();
		});
	});

	describe('callback handlers', () => {
		test('calls onSeek when Play button is clicked', async () => {
			const mockOnSeek = vi.fn();
			render(AnnotationItem, {
				props: { annotation: baseAnnotation, index: 0, onSeek: mockOnSeek }
			});

			const playButton = screen.getByRole('button', { name: 'Play' });
			await fireEvent.click(playButton);

			expect(mockOnSeek).toHaveBeenCalledWith('00:05');
		});

		test('calls onEdit when Edit button is clicked', async () => {
			const mockOnEdit = vi.fn();
			render(AnnotationItem, {
				props: { annotation: baseAnnotation, index: 0, onEdit: mockOnEdit }
			});

			const editButton = screen.getByRole('button', { name: 'Edit' });
			await fireEvent.click(editButton);

			expect(mockOnEdit).toHaveBeenCalledWith(0);
		});

		test('calls onReview when Review button is clicked', async () => {
			const mockOnReview = vi.fn();
			render(AnnotationItem, {
				props: { annotation: baseAnnotation, index: 0, onReview: mockOnReview }
			});

			const reviewButton = screen.getByRole('button', { name: 'Review' });
			await fireEvent.click(reviewButton);

			expect(mockOnReview).toHaveBeenCalledWith(0);
		});

		test('calls onDelete when Delete button is clicked', async () => {
			const mockOnDelete = vi.fn();
			render(AnnotationItem, {
				props: { annotation: baseAnnotation, index: 0, onDelete: mockOnDelete }
			});

			const deleteButton = screen.getByRole('button', { name: 'Delete' });
			await fireEvent.click(deleteButton);

			expect(mockOnDelete).toHaveBeenCalledWith(0);
		});

		test('calls onSelect when Add New Box button is clicked', async () => {
			const mockOnSelect = vi.fn();
			render(AnnotationItem, {
				props: { annotation: baseAnnotation, index: 0, onSelect: mockOnSelect }
			});

			const selectButton = screen.getByRole('button', { name: 'Add New Box' });
			await fireEvent.click(selectButton);

			expect(mockOnSelect).toHaveBeenCalledWith(0);
		});

		test('calls onShowBox when box is clicked', async () => {
			const mockOnShowBox = vi.fn();
			const annotationWithBox: Annotation = {
				...baseAnnotation,
				location: {
					boxes: [
						{ box_2d: [100, 100, 200, 200], timestamp: '00:05' }
					]
				}
			};
			render(AnnotationItem, {
				props: { annotation: annotationWithBox, index: 0, onShowBox: mockOnShowBox }
			});

			const boxButton = screen.getByText('B1').closest('button');
			await fireEvent.click(boxButton!);

			expect(mockOnShowBox).toHaveBeenCalled();
		});
	});

	describe('handles minimal annotation data', () => {
		test('renders with only question field', () => {
			const minimalAnnotation: Annotation = {
				question: 'A simple question?'
			};
			render(AnnotationItem, {
				props: { annotation: minimalAnnotation, index: 0 }
			});

			expect(screen.getByText('A simple question?')).toBeTruthy();
			expect(screen.getByText('A:')).toBeTruthy(); // Answer placeholder
		});

		test('renders with empty annotation object', () => {
			const emptyAnnotation: Annotation = {};
			const { container } = render(AnnotationItem, {
				props: { annotation: emptyAnnotation, index: 0 }
			});

			// Should render without crashing
			expect(container.querySelector('div')).toBeTruthy();
		});
	});

	describe('different annotation scenarios', () => {
		test('renders annotation with all optional fields', () => {
			const fullAnnotation: Annotation = {
				question: 'Complete question?',
				answer: 'Complete answer',
				skill: 'visual_recall',
				question_time_span: { start: '00:01', end: '00:03' },
				time_span: { start: '00:05', end: '00:20' },
				room: 'living room',
				modalities: ['visual', 'audio', 'text'],
				human_review: {
					status: 'accepted',
					comment: 'Good annotation'
				},
				location: {
					boxes: [
						{ box_2d: [100, 100, 200, 200], timestamp: '00:05' },
						{ box_2d: [300, 300, 400, 400], timestamp: '00:10' }
					]
				}
			};
			const { container } = render(AnnotationItem, {
				props: { annotation: fullAnnotation, index: 0 }
			});

			// Verify all components render
			expect(screen.getByText('Complete question?')).toBeTruthy();
			expect(screen.getByText('Complete answer')).toBeTruthy();
			expect(screen.getByText('Visual Recall')).toBeTruthy();
			expect(container.textContent).toContain('❓'); // question time span
			expect(container.textContent).toContain('⏱️'); // time span
			expect(container.textContent).toContain('living room');
			expect(container.textContent).toContain('visual');
			expect(container.textContent).toContain('audio');
			expect(container.textContent).toContain('text');
			expect(screen.getByText('✓ Accepted')).toBeTruthy();
			expect(container.textContent).toContain('Boxes (2):');
		});

		test('renders annotation without location at all', () => {
			const noLocationAnnotation: Annotation = {
				question: 'Where is the cat?',
				answer: 'On the couch',
				skill: 'object_location_memory'
			};
			const { container } = render(AnnotationItem, {
				props: { annotation: noLocationAnnotation, index: 0 }
			});

			expect(screen.getByText('Where is the cat?')).toBeTruthy();
			expect(container.textContent).not.toContain('Boxes');
		});
	});
});
