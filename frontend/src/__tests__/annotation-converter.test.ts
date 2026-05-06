/**
 * @vitest-environment jsdom
 */

import { describe, it, expect } from 'vitest';
import {
	annotationFieldToData,
	updateAnnotationFromData,
	boundingBoxToData,
	timestampToData,
	timeSpanToData,
	getEditableFields,
	getVisualizableFields,
} from '$lib/utils/annotation-converter';
import { AnnotationDataType } from '$lib/types/annotation-data-types';
import type { Annotation } from '$lib/types';

describe('Annotation Converter', () => {
	const mockAnnotation: Annotation = {
		question: 'What is the location of the keys?',
		answer: 'On the kitchen counter',
		skill: 'object_location_memory',
		question_time_span: { start: '00:30', end: '00:45' },
		room: 'Kitchen',
		modalities: ['Gaze', 'Video'],
		human_review: { status: 'pending', reviewed: false },
		answer_evidence: [
			{
				time_spans: [{ start: '01:00', end: '01:30' }],
				video_path: '/path/to/video.mp4',
			},
		],
		location: {
			boxes: [
				{
					box_2d: [100, 200, 300, 400],
					timestamp: '01:00',
				},
			],
		},
	};

	describe('annotationFieldToData', () => {
		it('converts question field to TextData', () => {
			const data = annotationFieldToData(mockAnnotation, 'question');
			expect(data?.type).toBe(AnnotationDataType.TEXT);
			expect((data as any).value).toBe('What is the location of the keys?');
		});

		it('converts answer field to TextData', () => {
			const data = annotationFieldToData(mockAnnotation, 'answer');
			expect(data?.type).toBe(AnnotationDataType.TEXT);
			expect((data as any).value).toBe('On the kitchen counter');
		});

		it('converts room field to TextData', () => {
			const data = annotationFieldToData(mockAnnotation, 'room');
			expect(data?.type).toBe(AnnotationDataType.TEXT);
			expect((data as any).value).toBe('Kitchen');
		});

		it('converts skill field to SkillTypeData', () => {
			const data = annotationFieldToData(mockAnnotation, 'skill');
			expect(data?.type).toBe(AnnotationDataType.SKILL_TYPE);
			expect((data as any).value).toBe('object_location_memory');
		});

		it('converts question_time_span field to TimeSpanData', () => {
			const data = annotationFieldToData(mockAnnotation, 'question_time_span');
			expect(data?.type).toBe(AnnotationDataType.TIMESPAN);
			expect((data as any).value).toEqual({ start: '00:30', end: '00:45' });
			expect((data as any).editable).toBe(true);
		});

		it('converts modalities field to ModalityListData', () => {
			const data = annotationFieldToData(mockAnnotation, 'modalities');
			expect(data?.type).toBe(AnnotationDataType.MODALITY_LIST);
			expect((data as any).value).toEqual(['Gaze', 'Video']);
			expect((data as any).availableModalities).toBeDefined();
		});

		it('converts human_review field to HumanReviewData', () => {
			const data = annotationFieldToData(mockAnnotation, 'human_review');
			expect(data?.type).toBe(AnnotationDataType.HUMAN_REVIEW);
			expect((data as any).value).toEqual({ status: 'pending', reviewed: false });
		});

		it('converts answer_evidence field to EvidenceListData', () => {
			const data = annotationFieldToData(mockAnnotation, 'answer_evidence');
			expect(data?.type).toBe(AnnotationDataType.EVIDENCE_LIST);
			expect((data as any).value).toBeDefined();
		});

		it('returns null for unknown field', () => {
			const data = annotationFieldToData(mockAnnotation, 'unknown_field');
			expect(data).toBeNull();
		});
	});

	describe('updateAnnotationFromData', () => {
		it('updates question field from TextData', () => {
			const data: import('$lib/types/annotation-data-types').TextData = {
				type: AnnotationDataType.TEXT,
				value: 'Updated question',
			};
			const updated = updateAnnotationFromData(mockAnnotation, 'question', data);
			expect(updated.question).toBe('Updated question');
			expect(updated.answer).toBe(mockAnnotation.answer); // Others unchanged
		});

		it('updates skill field from SkillTypeData', () => {
			const data: import('$lib/types/annotation-data-types').SkillTypeData = {
				type: AnnotationDataType.SKILL_TYPE,
				value: 'conversational_memory' as const,
			};
			const updated = updateAnnotationFromData(mockAnnotation, 'skill', data);
			expect(updated.skill).toBe('conversational_memory');
		});

		it('updates modalities field from ModalityListData', () => {
			const data: import('$lib/types/annotation-data-types').ModalityListData = {
				type: AnnotationDataType.MODALITY_LIST,
				value: ['Audio', 'OCR'],
				availableModalities: ['Gaze', 'Audio', 'Trajectory', 'Depth', 'Video', 'OCR'],
			};
			const updated = updateAnnotationFromData(mockAnnotation, 'modalities', data);
			expect(updated.modalities).toEqual(['Audio', 'OCR']);
		});

		it('updates question_time_span field from TimeSpanData', () => {
			const data: import('$lib/types/annotation-data-types').TimeSpanData = {
				type: AnnotationDataType.TIMESPAN,
				value: { start: '01:00', end: '02:00' },
				editable: true,
			};
			const updated = updateAnnotationFromData(mockAnnotation, 'question_time_span', data);
			expect(updated.question_time_span).toEqual({ start: '01:00', end: '02:00' });
		});

		it('does not modify other fields', () => {
			const data: import('$lib/types/annotation-data-types').TextData = {
				type: AnnotationDataType.TEXT,
				value: 'New room',
			};
			const updated = updateAnnotationFromData(mockAnnotation, 'room', data);
			expect(updated.room).toBe('New room');
			expect(updated.question).toBe(mockAnnotation.question);
			expect(updated.answer).toBe(mockAnnotation.answer);
		});
	});

	describe('boundingBoxToData', () => {
		it('converts bounding box to BoundingBoxData', () => {
			const box = {
				box_2d: [100, 200, 300, 400],
				timestamp: '01:00',
			};
			const data = boundingBoxToData(box);
			expect(data.type).toBe(AnnotationDataType.BOUNDING_BOX);
			expect(data.value).toEqual(box);
			expect(data.editable).toBe(true);
		});

		it('respects editable parameter', () => {
			const box = { box_2d: [0, 0, 100, 100] };
			const data = boundingBoxToData(box, false);
			expect(data.editable).toBe(false);
		});
	});

	describe('getEditableFields', () => {
		it('returns all editable field names', () => {
			const fields = getEditableFields(mockAnnotation);
			expect(fields).toContain('question');
			expect(fields).toContain('answer');
			expect(fields).toContain('skill');
			expect(fields).toContain('question_time_span');
			expect(fields).toContain('room');
			expect(fields).toContain('modalities');
			expect(fields).toContain('human_review');
			expect(fields).toContain('answer_evidence');
		});

		it('returns same fields regardless of annotation content', () => {
			const emptyAnnotation: Annotation = {};
			const fields = getEditableFields(emptyAnnotation);
			expect(fields.length).toBeGreaterThan(0);
		});
	});

	describe('getVisualizableFields', () => {
		it('returns only fields with values', () => {
			const fields = getVisualizableFields(mockAnnotation);
			expect(fields).toContain('question');
			expect(fields).toContain('answer');
			expect(fields).toContain('skill');
			expect(fields).toContain('room');
			expect(fields).toContain('modalities');
			expect(fields).toContain('location');
		});

		it('excludes empty fields', () => {
			const partialAnnotation: Annotation = {
				question: 'Test question',
				answer: undefined,
			};
			const fields = getVisualizableFields(partialAnnotation);
			expect(fields).toContain('question');
			expect(fields).not.toContain('answer');
		});

		it('excludes modalities when empty array', () => {
			const annotation: Annotation = {
				modalities: [],
			};
			const fields = getVisualizableFields(annotation);
			expect(fields).not.toContain('modalities');
		});

		it('excludes location when no boxes', () => {
			const annotation: Annotation = {
				location: { boxes: [] },
			};
			const fields = getVisualizableFields(annotation);
			expect(fields).not.toContain('location');
		});
	});

	describe('timestampToData', () => {
		it('converts timestamp string to TimestampData', () => {
			const data = timestampToData('01:23');
			expect(data.type).toBe(AnnotationDataType.TIMESTAMP);
			expect(data.value).toBe('01:23');
			expect(data.editable).toBe(true);
		});

		it('includes video path when provided', () => {
			const data = timestampToData('01:23', '/path/to/video.mp4');
			expect(data.videoPath).toBe('/path/to/video.mp4');
		});

		it('handles undefined timestamp', () => {
			const data = timestampToData(undefined);
			expect(data.value).toBeUndefined();
			expect(data.type).toBe(AnnotationDataType.TIMESTAMP);
		});

		it('respects editable flag', () => {
			const data = timestampToData('01:23', undefined, false);
			expect(data.editable).toBe(false);
		});
	});

	describe('timeSpanToData', () => {
		it('converts timespan to TimeSpanData', () => {
			const data = timeSpanToData({ start: '00:30', end: '00:45' });
			expect(data.type).toBe(AnnotationDataType.TIMESPAN);
			expect(data.value).toEqual({ start: '00:30', end: '00:45' });
			expect(data.editable).toBe(true);
		});

		it('includes video path when provided', () => {
			const data = timeSpanToData({ start: '00:30', end: '00:45' }, '/path/to/video.mp4');
			expect(data.videoPath).toBe('/path/to/video.mp4');
		});

		it('handles undefined timespan', () => {
			const data = timeSpanToData(undefined);
			expect(data.value).toBeUndefined();
			expect(data.type).toBe(AnnotationDataType.TIMESPAN);
		});

		it('respects editable flag', () => {
			const data = timeSpanToData({ start: '00:30', end: '00:45' }, undefined, false);
			expect(data.editable).toBe(false);
		});
	});
});
