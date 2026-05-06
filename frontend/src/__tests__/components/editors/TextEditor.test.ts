/**
 * @vitest-environment jsdom
 */

import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/svelte';
import TextEditor from '$lib/components/editors/TextEditor.svelte';
import { AnnotationDataType } from '$lib/types/annotation-data-types';
import type { TextData } from '$lib/types/annotation-data-types';

describe('TextEditor', () => {
	it('renders with empty value', () => {
		const data: TextData = {
			type: AnnotationDataType.TEXT,
			value: undefined,
		};
		const { container } = render(TextEditor, {
			props: {
				data,
				onChange: vi.fn(),
			},
		});

		const input = container.querySelector('input');
		expect(input).toBeTruthy();
		expect(input?.value).toBe('');
	});

	it('renders with initial value', () => {
		const data: TextData = {
			type: AnnotationDataType.TEXT,
			value: 'Test value',
		};
		const { container } = render(TextEditor, {
			props: {
				data,
				onChange: vi.fn(),
			},
		});

		const input = container.querySelector('input') as HTMLInputElement;
		expect(input.value).toBe('Test value');
	});

	it('calls onChange when value changes', async () => {
		const data: TextData = {
			type: AnnotationDataType.TEXT,
			value: 'Initial',
		};
		const onChange = vi.fn();
		const { container } = render(TextEditor, {
			props: {
				data,
				onChange,
			},
		});

		const input = container.querySelector('input') as HTMLInputElement;
		await fireEvent.input(input, { target: { value: 'Updated' } });

		expect(onChange).toHaveBeenCalledWith({
			type: AnnotationDataType.TEXT,
			value: 'Updated',
		});
	});

	it('renders with label', () => {
		const data: TextData = {
			type: AnnotationDataType.TEXT,
			value: undefined,
		};
		const { getByText } = render(TextEditor, {
			props: {
				data,
				label: 'Custom Label',
				onChange: vi.fn(),
			},
		});

		expect(getByText('Custom Label')).toBeTruthy();
	});

	it('renders multiline textarea when multiline prop is true', () => {
		const data: TextData = {
			type: AnnotationDataType.TEXT,
			value: 'Multi\nline\ntext',
		};
		const { container } = render(TextEditor, {
			props: {
				data,
				multiline: true,
				onChange: vi.fn(),
			},
		});

		const textarea = container.querySelector('textarea');
		expect(textarea).toBeTruthy();
		expect(textarea?.value).toBe('Multi\nline\ntext');
	});

	it('applies custom placeholder', () => {
		const data: TextData = {
			type: AnnotationDataType.TEXT,
			value: undefined,
		};
		const { container } = render(TextEditor, {
			props: {
				data,
				placeholder: 'Custom placeholder',
				onChange: vi.fn(),
			},
		});

		const input = container.querySelector('input') as HTMLInputElement;
		expect(input.placeholder).toBe('Custom placeholder');
	});
});
