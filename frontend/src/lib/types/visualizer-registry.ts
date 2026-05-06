/**
 * Visualizer Registry System
 *
 * This system manages the mapping between annotation data types and their
 * corresponding visualizer and editor components. It provides a centralized
 * way to render and edit different annotation entities.
 */

import type { Component } from 'svelte';
import { AnnotationDataType } from './annotation-data-types';
import type { AnnotationData } from './annotation-data-types';

// Import visualizer components
import QuestionVisualizer from '$lib/components/visualizers/QuestionVisualizer.svelte';
import AnswerVisualizer from '$lib/components/visualizers/AnswerVisualizer.svelte';
import TextVisualizer from '$lib/components/visualizers/TextVisualizer.svelte';
import TimeSpanVisualizer from '$lib/components/visualizers/TimeSpanVisualizer.svelte';
import TimestampVisualizer from '$lib/components/visualizers/TimestampVisualizer.svelte';
import QuestionTimeSpanVisualizer from '$lib/components/visualizers/QuestionTimeSpanVisualizer.svelte';
import SkillVisualizer from '$lib/components/visualizers/SkillVisualizer.svelte';
import RoomVisualizer from '$lib/components/visualizers/RoomVisualizer.svelte';
import ModalitiesVisualizer from '$lib/components/visualizers/ModalitiesVisualizer.svelte';
import HumanReviewVisualizer from '$lib/components/visualizers/HumanReviewVisualizer.svelte';
import BoundingBoxVisualizer from '$lib/components/visualizers/BoundingBoxVisualizer.svelte';
import EvidenceListVisualizer from '$lib/components/visualizers/EvidenceListVisualizer.svelte';

// Import editor components
import TextEditor from '$lib/components/editors/TextEditor.svelte';
import TimeSpanEditor from '$lib/components/editors/TimeSpanEditor.svelte';
import TimestampEditor from '$lib/components/editors/TimestampEditor.svelte';
import BoundingBoxEditor from '$lib/components/editors/BoundingBoxEditor.svelte';
import ModalityEditor from '$lib/components/editors/ModalityEditor.svelte';
import SkillTypeEditor from '$lib/components/editors/SkillTypeEditor.svelte';
import HumanReviewEditor from '$lib/components/editors/HumanReviewEditor.svelte';
import EvidenceListEditor from '$lib/components/editors/EvidenceListEditor.svelte';

/**
 * Visualizer component props interface
 */
export interface VisualizerProps {
	data: AnnotationData;
	onSeek?: (timestamp: string, videoPath?: string) => void;
	onShowBox?: (box: any, index: number) => void;
	activeVideoSource?: string;
	currentVideoPath?: string;
	[key: string]: any;
}

/**
 * Editor component props interface
 */
export interface EditorProps {
	data: AnnotationData;
	onChange: (newData: AnnotationData) => void;
	currentVideoPath?: string;
	[key: string]: any;
}

/**
 * Visualizer registration entry
 */
export interface VisualizerEntry {
	component: Component<any>;
	name: string;
	description: string;
}

/**
 * Editor registration entry
 */
export interface EditorEntry {
	component: Component<any>;
	name: string;
	description: string;
}

/**
 * Visualizer Registry
 * Maps data types to their visualizer components
 */
class VisualizerRegistry {
	private visualizers = new Map<AnnotationDataType, VisualizerEntry>();
	private editors = new Map<AnnotationDataType, EditorEntry>();

	/**
	 * Register a visualizer for a data type
	 */
	registerVisualizer(
		dataType: AnnotationDataType,
		component: Component<any>,
		name: string,
		description: string = ''
	): void {
		this.visualizers.set(dataType, { component, name, description });
	}

	/**
	 * Register an editor for a data type
	 */
	registerEditor(
		dataType: AnnotationDataType,
		component: Component<any>,
		name: string,
		description: string = ''
	): void {
		this.editors.set(dataType, { component, name, description });
	}

	/**
	 * Get visualizer for a data type
	 */
	getVisualizer(dataType: AnnotationDataType): VisualizerEntry | undefined {
		return this.visualizers.get(dataType);
	}

	/**
	 * Get editor for a data type
	 */
	getEditor(dataType: AnnotationDataType): EditorEntry | undefined {
		return this.editors.get(dataType);
	}

	/**
	 * Check if a visualizer is registered for a data type
	 */
	hasVisualizer(dataType: AnnotationDataType): boolean {
		return this.visualizers.has(dataType);
	}

	/**
	 * Check if an editor is registered for a data type
	 */
	hasEditor(dataType: AnnotationDataType): boolean {
		return this.editors.has(dataType);
	}

	/**
	 * Get all registered visualizers
	 */
	getAllVisualizers(): Map<AnnotationDataType, VisualizerEntry> {
		return new Map(this.visualizers);
	}

	/**
	 * Get all registered editors
	 */
	getAllEditors(): Map<AnnotationDataType, EditorEntry> {
		return new Map(this.editors);
	}
}

// Create singleton instance
export const visualizerRegistry = new VisualizerRegistry();

// Register default visualizers
// Note: Some components serve dual purposes or are field-specific
// The registry uses the generic ones for now, but can be extended

// TEXT visualizers - using unified TextVisualizer component
visualizerRegistry.registerVisualizer(
	AnnotationDataType.TEXT,
	TextVisualizer,
	'TextVisualizer',
	'Displays text content with configurable prefix and styling'
);

// TIMESPAN visualizers - used for time ranges (start-end pairs)
visualizerRegistry.registerVisualizer(
	AnnotationDataType.TIMESPAN,
	TimeSpanVisualizer,
	'TimeSpanVisualizer',
	'Displays time ranges with seek functionality'
);

// TIMESTAMP visualizer - used for single time points (e.g., bounding box timestamps)
visualizerRegistry.registerVisualizer(
	AnnotationDataType.TIMESTAMP,
	TimestampVisualizer,
	'TimestampVisualizer',
	'Displays single timestamp with seek functionality'
);

// EVIDENCE_LIST visualizer - reuses TimeSpanVisualizer for each timespan
visualizerRegistry.registerVisualizer(
	AnnotationDataType.EVIDENCE_LIST,
	EvidenceListVisualizer,
	'EvidenceListVisualizer',
	'Displays list of evidence with timespans'
);

// SKILL_TYPE visualizer
visualizerRegistry.registerVisualizer(
	AnnotationDataType.SKILL_TYPE,
	SkillVisualizer,
	'SkillVisualizer',
	'Displays skill type with color-coded badge'
);

// MODALITY_LIST visualizer
visualizerRegistry.registerVisualizer(
	AnnotationDataType.MODALITY_LIST,
	ModalitiesVisualizer,
	'ModalitiesVisualizer',
	'Displays list of modalities'
);

// HUMAN_REVIEW visualizer
visualizerRegistry.registerVisualizer(
	AnnotationDataType.HUMAN_REVIEW,
	HumanReviewVisualizer,
	'HumanReviewVisualizer',
	'Displays review status and information'
);

// BOUNDING_BOX visualizer
visualizerRegistry.registerVisualizer(
	AnnotationDataType.BOUNDING_BOX,
	BoundingBoxVisualizer,
	'BoundingBoxVisualizer',
	'Displays bounding boxes with click-to-seek'
);

// Register editors
visualizerRegistry.registerEditor(
	AnnotationDataType.TEXT,
	TextEditor,
	'TextEditor',
	'Edits text content'
);

visualizerRegistry.registerEditor(
	AnnotationDataType.TIMESPAN,
	TimeSpanEditor,
	'TimeSpanEditor',
	'Edits time ranges with manual input and progress bar dragging'
);

visualizerRegistry.registerEditor(
	AnnotationDataType.TIMESTAMP,
	TimestampEditor,
	'TimestampEditor',
	'Edits single timestamp with manual input and progress bar dragging'
);

visualizerRegistry.registerEditor(
	AnnotationDataType.EVIDENCE_LIST,
	EvidenceListEditor,
	'EvidenceListEditor',
	'Edits list of evidence, reusing TimeSpanEditor for each timespan'
);

visualizerRegistry.registerEditor(
	AnnotationDataType.BOUNDING_BOX,
	BoundingBoxEditor,
	'BoundingBoxEditor',
	'Edits bounding boxes with manual input and canvas dragging'
);

visualizerRegistry.registerEditor(
	AnnotationDataType.MODALITY_LIST,
	ModalityEditor,
	'ModalityEditor',
	'Edits modalities with checkboxes'
);

visualizerRegistry.registerEditor(
	AnnotationDataType.SKILL_TYPE,
	SkillTypeEditor,
	'SkillTypeEditor',
	'Edits skill type with dropdown'
);

visualizerRegistry.registerEditor(
	AnnotationDataType.HUMAN_REVIEW,
	HumanReviewEditor,
	'HumanReviewEditor',
	'Edits review status and comments'
);

/**
 * Helper function to get visualizer component for a data type
 */
export function getVisualizerComponent(
	dataType: AnnotationDataType
): Component<any> | undefined {
	const entry = visualizerRegistry.getVisualizer(dataType);
	return entry?.component;
}

/**
 * Helper function to get editor component for a data type
 */
export function getEditorComponent(
	dataType: AnnotationDataType
): Component<any> | undefined {
	const entry = visualizerRegistry.getEditor(dataType);
	return entry?.component;
}

/**
 * Field-specific visualizer mapping
 * Maps annotation field names to their preferred visualizer data type
 */
export const FIELD_TO_VISUALIZER_TYPE: Record<string, AnnotationDataType> = {
	question: AnnotationDataType.TEXT,
	answer: AnnotationDataType.TEXT,
	room: AnnotationDataType.TEXT,
	skill: AnnotationDataType.SKILL_TYPE,
	question_time_span: AnnotationDataType.TIMESPAN,
	modalities: AnnotationDataType.MODALITY_LIST,
	human_review: AnnotationDataType.HUMAN_REVIEW,
	answer_evidence: AnnotationDataType.EVIDENCE_LIST,
	location: AnnotationDataType.BOUNDING_BOX,
	// Legacy fields
	time_span: AnnotationDataType.TIMESPAN,
	answer_video_path: AnnotationDataType.TEXT,
};

/**
 * Get the appropriate visualizer data type for a field
 */
export function getVisualizerTypeForField(fieldName: string): AnnotationDataType {
	return FIELD_TO_VISUALIZER_TYPE[fieldName] || AnnotationDataType.TEXT;
}
