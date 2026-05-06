/**
 * Unit tests for SkillVisualizer component
 * Tests that the skill visualizer renders correctly with different skill types
 */

import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import SkillVisualizer from '$lib/components/visualizers/SkillVisualizer.svelte';
import type { SkillType } from '$lib/types';

describe('SkillVisualizer', () => {
	const skillTypes: SkillType[] = [
		'object_location_memory',
		'conversational_memory',
		'visual_recall',
		'timeline_reconstruction',
		'intent_recall',
		'in_context_retrieval',
		'unknown'
	];

	const skillLabels: Record<SkillType | 'unknown', string> = {
		object_location_memory: 'Object Location',
		conversational_memory: 'Conversational',
		visual_recall: 'Visual Recall',
		timeline_reconstruction: 'Timeline',
		intent_recall: 'Intent Recall',
		in_context_retrieval: 'In-Context',
		unknown: 'unknown'
	};

	describe('renders all skill types correctly', () => {
		test.each(skillTypes)('displays "%s" skill type with correct label', (skill) => {
			render(SkillVisualizer, { props: { value: skill } });

			const expectedLabel = skillLabels[skill as SkillType];
			expect(screen.getByText(expectedLabel)).toBeTruthy();
		});
	});

	describe('skill-specific styling', () => {
		test('object_location_memory has blue styling', () => {
			const { container } = render(SkillVisualizer, { props: { value: 'object_location_memory' } });

			const span = container.querySelector('span');
			expect(span?.className).toContain('bg-blue-50');
			expect(span?.className).toContain('text-blue-700');
			expect(span?.className).toContain('border-blue-200');
		});

		test('conversational_memory has purple styling', () => {
			const { container } = render(SkillVisualizer, { props: { value: 'conversational_memory' } });

			const span = container.querySelector('span');
			expect(span?.className).toContain('bg-purple-50');
			expect(span?.className).toContain('text-purple-700');
			expect(span?.className).toContain('border-purple-200');
		});

		test('visual_recall has emerald styling', () => {
			const { container } = render(SkillVisualizer, { props: { value: 'visual_recall' } });

			const span = container.querySelector('span');
			expect(span?.className).toContain('bg-emerald-50');
			expect(span?.className).toContain('text-emerald-700');
			expect(span?.className).toContain('border-emerald-200');
		});

		test('timeline_reconstruction has amber styling', () => {
			const { container } = render(SkillVisualizer, { props: { value: 'timeline_reconstruction' } });

			const span = container.querySelector('span');
			expect(span?.className).toContain('bg-amber-50');
			expect(span?.className).toContain('text-amber-700');
			expect(span?.className).toContain('border-amber-200');
		});

		test('intent_recall has rose styling', () => {
			const { container } = render(SkillVisualizer, { props: { value: 'intent_recall' } });

			const span = container.querySelector('span');
			expect(span?.className).toContain('bg-rose-50');
			expect(span?.className).toContain('text-rose-700');
			expect(span?.className).toContain('border-rose-200');
		});

		test('in_context_retrieval has cyan styling', () => {
			const { container } = render(SkillVisualizer, { props: { value: 'in_context_retrieval' } });

			const span = container.querySelector('span');
			expect(span?.className).toContain('bg-cyan-50');
			expect(span?.className).toContain('text-cyan-700');
			expect(span?.className).toContain('border-cyan-200');
		});

		test('unknown/undefined has zinc styling', () => {
			const { container } = render(SkillVisualizer, { props: { value: undefined } });

			const span = container.querySelector('span');
			expect(span?.className).toContain('bg-zinc-50');
			expect(span?.className).toContain('text-zinc-600');
			expect(span?.className).toContain('border-zinc-200');
		});
	});

	describe('handles undefined/invalid values', () => {
		test('shows "unknown" when value is undefined', () => {
			render(SkillVisualizer, { props: { value: undefined } });
			
			expect(screen.getByText('unknown')).toBeTruthy();
		});

		test('shows custom string when value is not a known skill', () => {
			render(SkillVisualizer, { props: { value: 'custom_skill' } });
			
			expect(screen.getByText('custom_skill')).toBeTruthy();
		});
	});

	describe('styling and structure', () => {
		test('skill is rendered in a span element', () => {
			const { container } = render(SkillVisualizer, { props: { value: 'visual_recall' } });

			const span = container.querySelector('span');
			expect(span).toBeTruthy();
		});

		test('has base styling classes', () => {
			const { container } = render(SkillVisualizer, { props: { value: 'visual_recall' } });

			const span = container.querySelector('span');
			expect(span?.className).toContain('text-sm');
			expect(span?.className).toContain('font-semibold');
			expect(span?.className).toContain('rounded-full');
		});
	});
});
