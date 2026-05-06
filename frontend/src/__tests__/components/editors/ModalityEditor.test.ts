/**
 * @vitest-environment jsdom
 */

import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/svelte';
import ModalityEditor from '$lib/components/editors/ModalityEditor.svelte';
import { AnnotationDataType } from '$lib/types/annotation-data-types';
import type { ModalityListData } from '$lib/types/annotation-data-types';

describe('ModalityEditor', () => {
	const availableModalities = ['Gaze', 'Audio', 'Trajectory', 'Depth', 'Video', 'OCR'];

	it('renders all available modalities as checkboxes', () => {
		const data: ModalityListData = {
			type: AnnotationDataType.MODALITY_LIST,
			value: [],
			availableModalities,
		};
		const { container } = render(ModalityEditor, {
			props: {
				data,
				onChange: vi.fn(),
			},
		});

		const checkboxes = container.querySelectorAll('input[type="checkbox"]');
		expect(checkboxes.length).toBe(6);
	});

	it('checks selected modalities', () => {
		const data: ModalityListData = {
			type: AnnotationDataType.MODALITY_LIST,
			value: ['Gaze', 'Video'],
			availableModalities,
		};
		const { container } = render(ModalityEditor, {
			props: {
				data,
				onChange: vi.fn(),
			},
		});

		const checkboxes = container.querySelectorAll('input[type="checkbox"]') as NodeListOf<HTMLInputElement>;

		// Gaze should be checked
		const gazeCheckbox = Array.from(checkboxes).find(cb => cb.id === 'modality-Gaze');
		expect(gazeCheckbox?.checked).toBe(true);

		// Video should be checked
		const videoCheckbox = Array.from(checkboxes).find(cb => cb.id === 'modality-Video');
		expect(videoCheckbox?.checked).toBe(true);

		// Audio should not be checked
		const audioCheckbox = Array.from(checkboxes).find(cb => cb.id === 'modality-Audio');
		expect(audioCheckbox?.checked).toBe(false);
	});

	it('calls onChange when modality is selected', async () => {
		const data: ModalityListData = {
			type: AnnotationDataType.MODALITY_LIST,
			value: [],
			availableModalities,
		};
		const onChange = vi.fn();
		const { container } = render(ModalityEditor, {
			props: {
				data,
				onChange,
			},
		});

		const checkboxes = container.querySelectorAll('input[type="checkbox"]') as NodeListOf<HTMLInputElement>;
		const gazeCheckbox = Array.from(checkboxes).find(cb => cb.id === 'modality-Gaze') as HTMLInputElement;

		await fireEvent.click(gazeCheckbox);

		expect(onChange).toHaveBeenCalledWith({
			type: AnnotationDataType.MODALITY_LIST,
			value: ['Gaze'],
			availableModalities,
		});
	});

	it('calls onChange when modality is deselected', async () => {
		const data: ModalityListData = {
			type: AnnotationDataType.MODALITY_LIST,
			value: ['Gaze', 'Video'],
			availableModalities,
		};
		const onChange = vi.fn();
		const { container } = render(ModalityEditor, {
			props: {
				data,
				onChange,
			},
		});

		const checkboxes = container.querySelectorAll('input[type="checkbox"]') as NodeListOf<HTMLInputElement>;
		const gazeCheckbox = Array.from(checkboxes).find(cb => cb.id === 'modality-Gaze') as HTMLInputElement;

		await fireEvent.click(gazeCheckbox);

		expect(onChange).toHaveBeenCalledWith({
			type: AnnotationDataType.MODALITY_LIST,
			value: ['Video'],
			availableModalities,
		});
	});

	it('renders with custom label', () => {
		const data: ModalityListData = {
			type: AnnotationDataType.MODALITY_LIST,
			value: [],
			availableModalities,
		};
		const { getByText } = render(ModalityEditor, {
			props: {
				data,
				label: 'Custom Modalities',
				onChange: vi.fn(),
			},
		});

		expect(getByText('Custom Modalities')).toBeTruthy();
	});

	it('handles undefined value', () => {
		const data: ModalityListData = {
			type: AnnotationDataType.MODALITY_LIST,
			value: undefined,
			availableModalities,
		};
		const { container } = render(ModalityEditor, {
			props: {
				data,
				onChange: vi.fn(),
			},
		});

		const checkboxes = container.querySelectorAll('input[type="checkbox"]') as NodeListOf<HTMLInputElement>;
		checkboxes.forEach(checkbox => {
			expect(checkbox.checked).toBe(false);
		});
	});
});
