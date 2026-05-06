/**
 * @vitest-environment jsdom
 */

import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/svelte';
import TimeSpanEditor from '$lib/components/editors/TimeSpanEditor.svelte';
import { AnnotationDataType } from '$lib/types/annotation-data-types';
import type { TimeSpanData } from '$lib/types/annotation-data-types';

describe('TimeSpanEditor', () => {
	it('renders with empty timespan', () => {
		const data: TimeSpanData = {
			type: AnnotationDataType.TIMESPAN,
			value: undefined,
			editable: true,
		};
		const { container } = render(TimeSpanEditor, {
			props: {
				data,
				onChange: vi.fn(),
			},
		});

		const inputs = container.querySelectorAll('input');
		expect(inputs.length).toBe(2); // start and end
	});

	it('renders with initial timespan value', () => {
		const data: TimeSpanData = {
			type: AnnotationDataType.TIMESPAN,
			value: { start: '01:30', end: '02:45' },
			editable: true,
		};
		const { container } = render(TimeSpanEditor, {
			props: {
				data,
				onChange: vi.fn(),
			},
		});

		const inputs = container.querySelectorAll('input') as NodeListOf<HTMLInputElement>;
		expect(inputs[0].value).toBe('01:30');
		expect(inputs[1].value).toBe('02:45');
	});

	it('calls onChange when start time changes', async () => {
		const data: TimeSpanData = {
			type: AnnotationDataType.TIMESPAN,
			value: { start: '00:00', end: '01:00' },
			editable: true,
		};
		const onChange = vi.fn();
		const { container } = render(TimeSpanEditor, {
			props: {
				data,
				onChange,
			},
		});

		const inputs = container.querySelectorAll('input') as NodeListOf<HTMLInputElement>;
		await fireEvent.input(inputs[0], { target: { value: '00:30' } });

		expect(onChange).toHaveBeenCalledWith({
			type: AnnotationDataType.TIMESPAN,
			value: { start: '00:30', end: '01:00' },
			editable: true,
		});
	});

	it('calls onChange when end time changes', async () => {
		const data: TimeSpanData = {
			type: AnnotationDataType.TIMESPAN,
			value: { start: '00:00', end: '01:00' },
			editable: true,
		};
		const onChange = vi.fn();
		const { container } = render(TimeSpanEditor, {
			props: {
				data,
				onChange,
			},
		});

		const inputs = container.querySelectorAll('input') as NodeListOf<HTMLInputElement>;
		await fireEvent.input(inputs[1], { target: { value: '02:00' } });

		expect(onChange).toHaveBeenCalledWith({
			type: AnnotationDataType.TIMESPAN,
			value: { start: '00:00', end: '02:00' },
			editable: true,
		});
	});

	it('displays progress bar edit button when editable and callback provided', () => {
		const data: TimeSpanData = {
			type: AnnotationDataType.TIMESPAN,
			value: { start: '00:00', end: '01:00' },
			editable: true,
		};
		const onRequestProgressBarEdit = vi.fn();
		const { container } = render(TimeSpanEditor, {
			props: {
				data,
				onChange: vi.fn(),
				onRequestProgressBarEdit,
			},
		});

		const button = container.querySelector('button');
		expect(button).toBeTruthy();
		expect(button?.textContent).toContain('Drag on timeline');
	});

	it('calls onRequestProgressBarEdit when button clicked', async () => {
		const data: TimeSpanData = {
			type: AnnotationDataType.TIMESPAN,
			value: { start: '00:00', end: '01:00' },
			editable: true,
		};
		const onRequestProgressBarEdit = vi.fn();
		const { container } = render(TimeSpanEditor, {
			props: {
				data,
				onChange: vi.fn(),
				onRequestProgressBarEdit,
			},
		});

		const button = container.querySelector('button') as HTMLButtonElement;
		await fireEvent.click(button);

		expect(onRequestProgressBarEdit).toHaveBeenCalled();
	});

	it('does not show progress bar button when not editable', () => {
		const data: TimeSpanData = {
			type: AnnotationDataType.TIMESPAN,
			value: { start: '00:00', end: '01:00' },
			editable: false,
		};
		const onRequestProgressBarEdit = vi.fn();
		const { container } = render(TimeSpanEditor, {
			props: {
				data,
				onChange: vi.fn(),
				onRequestProgressBarEdit,
			},
		});

		const button = container.querySelector('button');
		expect(button).toBeNull();
	});

	it('renders with custom label', () => {
		const data: TimeSpanData = {
			type: AnnotationDataType.TIMESPAN,
			value: undefined,
			editable: true,
		};
		const { getByText } = render(TimeSpanEditor, {
			props: {
				data,
				label: 'Custom Timespan',
				onChange: vi.fn(),
			},
		});

		expect(getByText('Custom Timespan')).toBeTruthy();
	});
});
