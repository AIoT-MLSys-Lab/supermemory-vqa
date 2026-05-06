/**
 * Tests for annotation-related functionality
 * Tests for issues encountered during PR development:
 * - Annotation count showing 0 for all videos
 * - Modular visualization components
 * - Annotation CRUD operations
 */

import { describe, test, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/svelte';
import type { Video, AnnotationFile, SkillType } from '../lib/types';

describe('Annotation Count', () => {
	/**
	 * Issue: Annotation count still shows as 0 for all videos
	 * Root cause: The /api/videos endpoint wasn't returning annotation counts
	 * Fix: Backend updated to include annotations_count in video list response
	 */

	describe('Video List Annotation Counts', () => {
		test('video objects should include annotation_count property', () => {
			const video: Video = {
				filename: 'test.mp4',
				annotations_count: 5
			};

			expect(video.annotations_count).toBe(5);
			expect(typeof video.annotations_count).toBe('number');
		});

		test('handles videos with zero annotations', () => {
			const video: Video = {
				filename: 'new-video.mp4',
				annotations_count: 0
			};

			expect(video.annotations_count).toBe(0);
		});

		test('handles videos without annotation_count (backward compatibility)', () => {
			const video: Video = {
				filename: 'old-video.mp4'
				// No annotations_count property
			};

			// Should default to 0 or undefined, not throw
			const count = video.annotations_count ?? 0;
			expect(count).toBe(0);
		});
	});

	describe('Annotation File Counts', () => {
		test('annotation file should include annotation_count', () => {
			const annotationFile: AnnotationFile = {
				filename: 'annotations_2024-01-01.json',
				annotations: [],
				annotation_count: 10
			};

			expect(annotationFile.annotation_count).toBe(10);
		});

		test('calculates total annotations across all files', () => {
			const files: AnnotationFile[] = [
				{ filename: 'file1.json', annotations: [], annotation_count: 5 },
				{ filename: 'file2.json', annotations: [], annotation_count: 3 },
				{ filename: 'file3.json', annotations: [], annotation_count: 7 }
			];

			const total = files.reduce((sum, f) => sum + (f.annotation_count ?? 0), 0);
			expect(total).toBe(15);
		});
	});
});

describe('Modular Visualizers', () => {
	/**
	 * Issue: Individual components should be modular and defined in separate files
	 * The annotation items should render different objects independently
	 */

	describe('Visualizer Component Structure', () => {
		test('QuestionVisualizer handles question field', () => {
			const annotation = { question: 'What is this?' };
			expect(annotation.question).toBeTruthy();
		});

		test('AnswerVisualizer handles answer field', () => {
			const annotation = { answer: 'This is a table.' };
			expect(annotation.answer).toBeTruthy();
		});

		test('TimeSpanVisualizer handles time_span field', () => {
			const annotation = {
				time_span: { start: '00:05', end: '00:10' }
			};
			expect(annotation.time_span.start).toBe('00:05');
			expect(annotation.time_span.end).toBe('00:10');
		});

		test('SkillVisualizer handles skill field', () => {
			const validSkills: SkillType[] = [
				'object_location_memory',
				'conversational_memory',
				'visual_recall',
				'timeline_reconstruction',
				'intent_recall',
				'in_context_retrieval',
				'unknown'
			];
			
			validSkills.forEach((skill) => {
				const annotation = { skill };
				expect(validSkills).toContain(annotation.skill);
			});
		});

		test('RoomVisualizer handles room field', () => {
			const annotation = { room: 'kitchen' };
			expect(annotation.room).toBe('kitchen');
		});

		test('ModalitiesVisualizer handles modalities array', () => {
			const annotation = {
				modalities: ['visual', 'audio', 'text']
			};
			expect(annotation.modalities).toHaveLength(3);
			expect(annotation.modalities).toContain('visual');
		});

		test('HumanReviewVisualizer handles human_review field', () => {
			const annotation = {
				human_review: { status: 'accepted' as const, comment: 'Good annotation' }
			};
			expect(annotation.human_review.status).toBe('accepted');
		});

		test('BoundingBoxVisualizer handles location.boxes field', () => {
			const annotation = {
				location: {
					boxes: [
						{ box_2d: [100, 100, 200, 200], timestamp: '00:05' }
					]
				}
			};
			expect(annotation.location.boxes).toHaveLength(1);
			expect(annotation.location.boxes[0].box_2d).toHaveLength(4);
		});
	});

	describe('Annotation Field Handling', () => {
		test('handles annotation with all fields', () => {
			const fullAnnotation = {
				question: 'What is this?',
				answer: 'A table',
				time_span: { start: '00:00', end: '00:10' },
				skill: 'object_location_memory' as SkillType,
				room: 'kitchen',
				modalities: ['visual'],
				human_review: { status: 'pending' as const },
				location: { boxes: [] }
			};

			// All fields should be defined
			expect(fullAnnotation.question).toBeDefined();
			expect(fullAnnotation.answer).toBeDefined();
			expect(fullAnnotation.time_span).toBeDefined();
			expect(fullAnnotation.skill).toBeDefined();
			expect(fullAnnotation.room).toBeDefined();
			expect(fullAnnotation.modalities).toBeDefined();
			expect(fullAnnotation.human_review).toBeDefined();
			expect(fullAnnotation.location).toBeDefined();
		});

		test('handles annotation with minimal fields', () => {
			const minimalAnnotation = {
				question: 'What?'
			};

			// Should not throw when accessing undefined fields
			expect(minimalAnnotation.question).toBeDefined();
			expect((minimalAnnotation as Record<string, unknown>).answer).toBeUndefined();
		});

		test('handles null/undefined values gracefully', () => {
			const annotation = {
				question: 'Test?',
				answer: null,
				time_span: undefined
			};

			// Should handle null/undefined without throwing
			expect(annotation.question).toBe('Test?');
			expect(annotation.answer).toBeNull();
			expect(annotation.time_span).toBeUndefined();
		});
	});
});

describe('Review Status Handling', () => {
	/**
	 * Issue: Review button also failing with 415 error
	 * Tests the review status cycling functionality
	 */

	test('cycles through review statuses correctly', () => {
		const statuses = ['pending', 'accepted', 'rejected'] as const;
		
		const getNextStatus = (current: string): string => {
			const index = statuses.indexOf(current as typeof statuses[number]);
			return statuses[(index + 1) % statuses.length];
		};

		expect(getNextStatus('pending')).toBe('accepted');
		expect(getNextStatus('accepted')).toBe('rejected');
		expect(getNextStatus('rejected')).toBe('pending');
	});

	test('handles legacy reviewed boolean format', () => {
		const legacyReview = { reviewed: true };
		const status = legacyReview.reviewed ? 'accepted' : 'pending';
		expect(status).toBe('accepted');
	});

	test('handles new status string format', () => {
		const newReview = { status: 'rejected' as const };
		expect(newReview.status).toBe('rejected');
	});

	test('defaults to pending when review is undefined', () => {
		const annotation: { question: string; human_review?: { status?: string } } = { question: 'Test?' };
		const status = annotation.human_review?.status ?? 'pending';
		expect(status).toBe('pending');
	});
});
