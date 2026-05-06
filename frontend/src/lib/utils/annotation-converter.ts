/**
 * Annotation Data Converter Utilities
 *
 * Utilities to convert between Annotation objects and typed data structures
 * for use with the visualizer/editor registry system.
 */

import type { Annotation } from '$lib/types';
import {
	AnnotationDataType,
	type TextData,
	type TimeSpanData,
	type TimestampData,
	type BoundingBoxData,
	type SkillTypeData,
	type ModalityListData,
	type HumanReviewData,
	type EvidenceListData,
	type AnswerChoicesData,
	type AnnotationData,
} from '$lib/types/annotation-data-types';

/**
 * Convert annotation field to its corresponding data type object
 */
export function annotationFieldToData(
	annotation: Annotation,
	fieldName: string
): AnnotationData | null {
	switch (fieldName) {
		case 'question':
			return {
				type: AnnotationDataType.TEXT,
				value: annotation.question,
			} as TextData;

		case 'answer':
			return {
				type: AnnotationDataType.TEXT,
				value: annotation.answer,
			} as TextData;

		case 'room':
			return {
				type: AnnotationDataType.TEXT,
				value: annotation.room,
			} as TextData;

		case 'skill':
			return {
				type: AnnotationDataType.SKILL_TYPE,
				value: annotation.skill,
			} as SkillTypeData;

		case 'question_time_span':
			return {
				type: AnnotationDataType.TIMESPAN,
				value: annotation.question_time_span,
				editable: true,
			} as TimeSpanData;

		case 'modalities':
			return {
				type: AnnotationDataType.MODALITY_LIST,
				value: annotation.modalities,
				availableModalities: ['Gaze', 'Audio', 'Trajectory', 'Depth', 'Video', 'OCR'],
			} as ModalityListData;

		case 'human_review':
			return {
				type: AnnotationDataType.HUMAN_REVIEW,
				value: annotation.human_review,
			} as HumanReviewData;

		case 'answer_evidence':
			return {
				type: AnnotationDataType.EVIDENCE_LIST,
				value: annotation.answer_evidence,
			} as EvidenceListData;

		case 'answer_choices':
			return {
				type: AnnotationDataType.ANSWER_CHOICES,
				value: annotation.answer_choices,
				isAnswerable: annotation.is_answerable,
			} as AnswerChoicesData;

		// Legacy fields
		case 'time_span':
			return {
				type: AnnotationDataType.TIMESPAN,
				value: annotation.time_span,
				editable: true,
			} as TimeSpanData;

		case 'answer_video_path':
			return {
				type: AnnotationDataType.TEXT,
				value: annotation.answer_video_path,
			} as TextData;

		default:
			return null;
	}
}

/**
 * Update annotation object with data from a typed data object
 */
export function updateAnnotationFromData(
	annotation: Annotation,
	fieldName: string,
	data: AnnotationData
): Annotation {
	const updated = { ...annotation };

	switch (fieldName) {
		case 'question':
			updated.question = (data as TextData).value;
			if (updated.question_details) {
				updated.question_details.text = updated.question;
			}
			break;

		case 'answer':
			updated.answer = (data as TextData).value;
			if (updated.answer_details) {
				updated.answer_details.text = updated.answer;
			}
			break;

		case 'room':
			updated.room = (data as TextData).value;
			if (updated.question_details) {
				updated.question_details.room = updated.room;
			}
			break;

		case 'skill':
			updated.skill = (data as SkillTypeData).value;
			break;

		case 'question_time_span':
			updated.question_time_span = (data as TimeSpanData).value;
			if (updated.question_details && updated.question_time_span) {
				updated.question_details.time_span = {
					start_time: updated.question_time_span.start,
					end_time: updated.question_time_span.end,
				};
			}
			break;

		case 'modalities':
			updated.modalities = (data as ModalityListData).value;
			if (updated.question_details) {
				updated.question_details.modalities = updated.modalities;
			}
			break;

		case 'human_review':
			updated.human_review = (data as HumanReviewData).value;
			break;

		case 'answer_evidence':
			updated.answer_evidence = (data as EvidenceListData).value;
			// Note: syncing answer_details.evidence_list is more complex and typically
			// handled by the evidence list editor itself or the backend de-normalizer.
			break;

		case 'answer_choices':
			const choicesData = data as AnswerChoicesData;
			updated.answer_choices = choicesData.value;
			updated.is_answerable = choicesData.isAnswerable;
			if (updated.answer_details) {
				updated.answer_details.answer_choices = choicesData.value;
				updated.answer_details.is_answerable = choicesData.isAnswerable;
			}
			if (updated.question_details) {
				updated.question_details.is_answerable = choicesData.isAnswerable; // backward compat
			}
			break;

		// Legacy fields
		case 'time_span':
			updated.time_span = (data as TimeSpanData).value;
			break;

		case 'answer_video_path':
			updated.answer_video_path = (data as TextData).value;
			break;
	}

	return updated;
}

/**
 * Convert a bounding box to BoundingBoxData
 */
export function boundingBoxToData(
	box: any,
	editable: boolean = true
): BoundingBoxData {
	return {
		type: AnnotationDataType.BOUNDING_BOX,
		value: box,
		editable,
	};
}

/**
 * Convert a timestamp string to TimestampData
 * Used for bounding box timestamps and other single time points
 */
export function timestampToData(
	timestamp: string | undefined,
	videoPath?: string,
	editable: boolean = true
): TimestampData {
	return {
		type: AnnotationDataType.TIMESTAMP,
		value: timestamp,
		videoPath,
		editable,
	};
}

/**
 * Convert a timespan to TimeSpanData
 * Helper function for creating TimeSpan data objects
 */
export function timeSpanToData(
	timeSpan: { start?: string; end?: string } | undefined,
	videoPath?: string,
	editable: boolean = true
): TimeSpanData {
	return {
		type: AnnotationDataType.TIMESPAN,
		value: timeSpan,
		videoPath,
		editable,
	};
}

/**
 * Get all editable fields for an annotation
 */
export function getEditableFields(annotation: Annotation): string[] {
	return [
		'question',
		'answer',
		'skill',
		'question_time_span',
		'room',
		'modalities',
		'human_review',
		'answer_evidence',
		'answer_choices',
	];
}

/**
 * Get all visualizable fields for an annotation
 */
export function getVisualizableFields(annotation: Annotation): string[] {
	const fields: string[] = [];

	if (annotation.question) fields.push('question');
	if (annotation.answer) fields.push('answer');
	if (annotation.skill) fields.push('skill');
	if (annotation.question_time_span) fields.push('question_time_span');
	if (annotation.room) fields.push('room');
	if (annotation.modalities && annotation.modalities.length > 0) fields.push('modalities');
	if (annotation.human_review) fields.push('human_review');
	if (annotation.answer_evidence && annotation.answer_evidence.length > 0)
		fields.push('answer_evidence');
	if (annotation.answer_choices && annotation.answer_choices.length > 0)
		fields.push('answer_choices');
	if (annotation.location?.boxes && annotation.location.boxes.length > 0)
		fields.push('location');

	// Legacy fields
	if (annotation.time_span && !fields.includes('answer_evidence')) fields.push('time_span');

	return fields;
}
