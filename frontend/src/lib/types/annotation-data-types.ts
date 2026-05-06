/**
 * Annotation Data Type System
 *
 * This file defines the core data types used in annotations and maps
 * each annotation entity to its corresponding data type. Each data type
 * has a specific visualizer and editor component.
 */

import type { TimeSpan, BoundingBox, SkillType, HumanReview, AnswerChoice } from './index';

/**
 * Enum of all annotation data types
 */
export enum AnnotationDataType {
	TEXT = 'TEXT',
	TIMESPAN = 'TIMESPAN',
	TIMESTAMP = 'TIMESTAMP',
	BOUNDING_BOX = 'BOUNDING_BOX',
	SKILL_TYPE = 'SKILL_TYPE',
	MODALITY_LIST = 'MODALITY_LIST',
	HUMAN_REVIEW = 'HUMAN_REVIEW',
	EVIDENCE_LIST = 'EVIDENCE_LIST',
	ANSWER_CHOICES = 'ANSWER_CHOICES',
}

/**
 * Base interface for all annotation data type values
 */
export interface AnnotationDataValue {
	type: AnnotationDataType;
}

/**
 * Text data type (for question, answer, room, etc.)
 */
export interface TextData extends AnnotationDataValue {
	type: AnnotationDataType.TEXT;
	value: string | undefined;
}

/**
 * TimeSpan data type (for time ranges)
 */
export interface TimeSpanData extends AnnotationDataValue {
	type: AnnotationDataType.TIMESPAN;
	value: TimeSpan | undefined;
	videoPath?: string;
	editable: boolean; // Can be edited via progress bar drag
}

/**
 * Timestamp data type (for single time points)
 */
export interface TimestampData extends AnnotationDataValue {
	type: AnnotationDataType.TIMESTAMP;
	value: string | undefined; // MM:SS format
	videoPath?: string;
	editable: boolean;
}

/**
 * BoundingBox data type
 */
export interface BoundingBoxData extends AnnotationDataValue {
	type: AnnotationDataType.BOUNDING_BOX;
	value: BoundingBox | undefined;
	editable: boolean; // Can be edited via drag-drop
}

/**
 * SkillType data type
 */
export interface SkillTypeData extends AnnotationDataValue {
	type: AnnotationDataType.SKILL_TYPE;
	value: SkillType | undefined;
}

/**
 * ModalityList data type
 */
export interface ModalityListData extends AnnotationDataValue {
	type: AnnotationDataType.MODALITY_LIST;
	value: string[] | undefined;
	availableModalities: string[];
}

/**
 * HumanReview data type
 */
export interface HumanReviewData extends AnnotationDataValue {
	type: AnnotationDataType.HUMAN_REVIEW;
	value: HumanReview | undefined;
}

/**
 * Evidence list data type (collection of timespans with video paths)
 */
export interface EvidenceListData extends AnnotationDataValue {
	type: AnnotationDataType.EVIDENCE_LIST;
	value: Array<{
		time_spans?: TimeSpan[];
		video_path?: string;
	}> | undefined;
}

/**
 * Answer choices data type (multiple choice answer options)
 */
export interface AnswerChoicesData extends AnnotationDataValue {
	type: AnnotationDataType.ANSWER_CHOICES;
	value: AnswerChoice[] | undefined;
	isAnswerable?: boolean;
}

/**
 * Union type of all data types
 */
export type AnnotationData =
	| TextData
	| TimeSpanData
	| TimestampData
	| BoundingBoxData
	| SkillTypeData
	| ModalityListData
	| HumanReviewData
	| EvidenceListData
	| AnswerChoicesData;

/**
 * Annotation entity to data type mapping
 */
export interface AnnotationEntityMapping {
	question: TextData;
	answer: TextData;
	room: TextData;
	skill: SkillTypeData;
	question_time_span: TimeSpanData;
	modalities: ModalityListData;
	human_review: HumanReviewData;
	answer_evidence: EvidenceListData;
	// Legacy fields
	time_span: TimeSpanData;
	answer_video_path: TextData;
}

/**
 * Configuration for edit modes per data type
 */
export interface EditModeConfig {
	// Can be edited by dragging on video canvas
	canDragOnCanvas: boolean;
	// Can be edited by dragging on progress bar
	canDragOnProgressBar: boolean;
	// Can be edited manually in edit panel
	canEditInPanel: boolean;
	// Requires direct input only (no visual editing)
	requiresDirectInput: boolean;
}

/**
 * Edit mode configuration for each data type
 */
export const EDIT_MODE_CONFIG: Record<AnnotationDataType, EditModeConfig> = {
	[AnnotationDataType.TEXT]: {
		canDragOnCanvas: false,
		canDragOnProgressBar: false,
		canEditInPanel: true,
		requiresDirectInput: true,
	},
	[AnnotationDataType.TIMESPAN]: {
		canDragOnCanvas: false,
		canDragOnProgressBar: true, // Drag bars on timeline
		canEditInPanel: true,
		requiresDirectInput: false,
	},
	[AnnotationDataType.TIMESTAMP]: {
		canDragOnCanvas: false,
		canDragOnProgressBar: true, // Drag marker on timeline
		canEditInPanel: true,
		requiresDirectInput: false,
	},
	[AnnotationDataType.BOUNDING_BOX]: {
		canDragOnCanvas: true, // Drag and resize on video
		canDragOnProgressBar: false,
		canEditInPanel: true, // Can also edit coordinates manually
		requiresDirectInput: false,
	},
	[AnnotationDataType.SKILL_TYPE]: {
		canDragOnCanvas: false,
		canDragOnProgressBar: false,
		canEditInPanel: true,
		requiresDirectInput: true, // Dropdown only
	},
	[AnnotationDataType.MODALITY_LIST]: {
		canDragOnCanvas: false,
		canDragOnProgressBar: false,
		canEditInPanel: true,
		requiresDirectInput: true, // Checkboxes only
	},
	[AnnotationDataType.HUMAN_REVIEW]: {
		canDragOnCanvas: false,
		canDragOnProgressBar: false,
		canEditInPanel: true,
		requiresDirectInput: true, // Dropdown and text input
	},
	[AnnotationDataType.EVIDENCE_LIST]: {
		canDragOnCanvas: false,
		canDragOnProgressBar: true, // Each timespan can be dragged
		canEditInPanel: true,
		requiresDirectInput: false,
	},
	[AnnotationDataType.ANSWER_CHOICES]: {
		canDragOnCanvas: false,
		canDragOnProgressBar: false,
		canEditInPanel: true,
		requiresDirectInput: true, // Multiple choice editor
	},
};
