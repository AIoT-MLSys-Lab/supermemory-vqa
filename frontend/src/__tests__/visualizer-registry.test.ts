/**
 * @vitest-environment jsdom
 */

import { describe, it, expect } from 'vitest';
import {
	visualizerRegistry,
	getVisualizerComponent,
	getEditorComponent,
	getVisualizerTypeForField,
} from '$lib/types/visualizer-registry';
import { AnnotationDataType } from '$lib/types/annotation-data-types';

describe('Visualizer Registry', () => {
	describe('Visualizer Registration', () => {
		it('has registered visualizers for all data types', () => {
			expect(visualizerRegistry.hasVisualizer(AnnotationDataType.TEXT)).toBe(true);
			expect(visualizerRegistry.hasVisualizer(AnnotationDataType.TIMESPAN)).toBe(true);
			expect(visualizerRegistry.hasVisualizer(AnnotationDataType.TIMESTAMP)).toBe(true);
			expect(visualizerRegistry.hasVisualizer(AnnotationDataType.SKILL_TYPE)).toBe(true);
			expect(visualizerRegistry.hasVisualizer(AnnotationDataType.MODALITY_LIST)).toBe(true);
			expect(visualizerRegistry.hasVisualizer(AnnotationDataType.HUMAN_REVIEW)).toBe(true);
			expect(visualizerRegistry.hasVisualizer(AnnotationDataType.BOUNDING_BOX)).toBe(true);
			expect(visualizerRegistry.hasVisualizer(AnnotationDataType.EVIDENCE_LIST)).toBe(true);
		});

		it('returns visualizer component for registered types', () => {
			const textVisualizer = getVisualizerComponent(AnnotationDataType.TEXT);
			expect(textVisualizer).toBeDefined();

			const timespanVisualizer = getVisualizerComponent(AnnotationDataType.TIMESPAN);
			expect(timespanVisualizer).toBeDefined();

			const timestampVisualizer = getVisualizerComponent(AnnotationDataType.TIMESTAMP);
			expect(timestampVisualizer).toBeDefined();

			const skillVisualizer = getVisualizerComponent(AnnotationDataType.SKILL_TYPE);
			expect(skillVisualizer).toBeDefined();

			const evidenceVisualizer = getVisualizerComponent(AnnotationDataType.EVIDENCE_LIST);
			expect(evidenceVisualizer).toBeDefined();
		});

		it('returns visualizer entry with metadata', () => {
			const entry = visualizerRegistry.getVisualizer(AnnotationDataType.TEXT);
			expect(entry).toBeDefined();
			expect(entry?.name).toBe('TextVisualizer');
			expect(entry?.description).toBeDefined();
			expect(entry?.component).toBeDefined();
		});
	});

	describe('Editor Registration', () => {
		it('has registered editors for all data types', () => {
			expect(visualizerRegistry.hasEditor(AnnotationDataType.TEXT)).toBe(true);
			expect(visualizerRegistry.hasEditor(AnnotationDataType.TIMESPAN)).toBe(true);
			expect(visualizerRegistry.hasEditor(AnnotationDataType.TIMESTAMP)).toBe(true);
			expect(visualizerRegistry.hasEditor(AnnotationDataType.BOUNDING_BOX)).toBe(true);
			expect(visualizerRegistry.hasEditor(AnnotationDataType.MODALITY_LIST)).toBe(true);
			expect(visualizerRegistry.hasEditor(AnnotationDataType.SKILL_TYPE)).toBe(true);
			expect(visualizerRegistry.hasEditor(AnnotationDataType.HUMAN_REVIEW)).toBe(true);
			expect(visualizerRegistry.hasEditor(AnnotationDataType.EVIDENCE_LIST)).toBe(true);
		});

		it('returns editor component for registered types', () => {
			const textEditor = getEditorComponent(AnnotationDataType.TEXT);
			expect(textEditor).toBeDefined();

			const timespanEditor = getEditorComponent(AnnotationDataType.TIMESPAN);
			expect(timespanEditor).toBeDefined();

			const timestampEditor = getEditorComponent(AnnotationDataType.TIMESTAMP);
			expect(timestampEditor).toBeDefined();

			const bboxEditor = getEditorComponent(AnnotationDataType.BOUNDING_BOX);
			expect(bboxEditor).toBeDefined();

			const evidenceEditor = getEditorComponent(AnnotationDataType.EVIDENCE_LIST);
			expect(evidenceEditor).toBeDefined();
		});

		it('returns editor entry with metadata', () => {
			const entry = visualizerRegistry.getEditor(AnnotationDataType.TEXT);
			expect(entry).toBeDefined();
			expect(entry?.name).toBe('TextEditor');
			expect(entry?.description).toBeDefined();
			expect(entry?.component).toBeDefined();
		});
	});

	describe('Field to Visualizer Type Mapping', () => {
		it('maps annotation fields to correct data types', () => {
			expect(getVisualizerTypeForField('question')).toBe(AnnotationDataType.TEXT);
			expect(getVisualizerTypeForField('answer')).toBe(AnnotationDataType.TEXT);
			expect(getVisualizerTypeForField('room')).toBe(AnnotationDataType.TEXT);
			expect(getVisualizerTypeForField('skill')).toBe(AnnotationDataType.SKILL_TYPE);
			expect(getVisualizerTypeForField('question_time_span')).toBe(AnnotationDataType.TIMESPAN);
			expect(getVisualizerTypeForField('modalities')).toBe(AnnotationDataType.MODALITY_LIST);
			expect(getVisualizerTypeForField('human_review')).toBe(AnnotationDataType.HUMAN_REVIEW);
			expect(getVisualizerTypeForField('location')).toBe(AnnotationDataType.BOUNDING_BOX);
		});

		it('maps legacy fields correctly', () => {
			expect(getVisualizerTypeForField('time_span')).toBe(AnnotationDataType.TIMESPAN);
			expect(getVisualizerTypeForField('answer_video_path')).toBe(AnnotationDataType.TEXT);
		});

		it('defaults to TEXT for unknown fields', () => {
			expect(getVisualizerTypeForField('unknown_field')).toBe(AnnotationDataType.TEXT);
		});
	});

	describe('Registry Methods', () => {
		it('getAllVisualizers returns all registered visualizers', () => {
			const allVisualizers = visualizerRegistry.getAllVisualizers();
			expect(allVisualizers.size).toBeGreaterThan(0);
			expect(allVisualizers.has(AnnotationDataType.TEXT)).toBe(true);
			expect(allVisualizers.has(AnnotationDataType.TIMESPAN)).toBe(true);
		});

		it('getAllEditors returns all registered editors', () => {
			const allEditors = visualizerRegistry.getAllEditors();
			expect(allEditors.size).toBeGreaterThan(0);
			expect(allEditors.has(AnnotationDataType.TEXT)).toBe(true);
			expect(allEditors.has(AnnotationDataType.TIMESPAN)).toBe(true);
		});
	});
});
