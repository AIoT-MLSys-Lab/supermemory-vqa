import { describe, expect, test } from 'vitest';
import type { Annotation } from '$lib/types';
import {
	computeQAClips,
	parseQATimestamp,
	syncAnnotationForSave,
	updateAnnotationClipSpan,
	validateQAAnnotation
} from '$lib/utils/qa-review';

describe('qa-review utils', () => {
	test('computes clips from question and evidence timespans', () => {
		const annotation: Annotation = {
			question: 'Where is it?',
			answer: 'On the desk.',
			video_filename: 'question.mp4',
			question_time_spans: [{ start: '00:10', end: '00:12' }],
			answer_evidence: [
				{
					video_path: 'answer',
					time_spans: [
						{ start: '00:01', end: '00:03' },
						{ start: '00:04', end: '00:06' }
					]
				}
			]
		};

		const clips = computeQAClips(annotation, 'question.mp4');

		expect(clips).toHaveLength(3);
		expect(clips[0].key).toBe('question-0');
		expect(clips[1].key).toBe('evidence-0-0');
		expect(clips[1].videoFilename).toBe('answer.mp4');
	});

	test('updates the selected evidence timespan', () => {
		const annotation: Annotation = {
			question: 'Where is it?',
			answer: 'On the desk.',
			question_time_span: { start: '00:10', end: '00:12' },
			answer_evidence: [
				{
					video_path: 'answer.mp4',
					time_spans: [{ start: '00:01', end: '00:03' }]
				}
			]
		};
		const clip = computeQAClips(annotation, 'question.mp4')[1];

		const updated = updateAnnotationClipSpan(
			annotation,
			clip,
			{ start: '00:20', end: '00:25' },
			'new-answer.mp4'
		);

		expect(updated.answer_evidence?.[0].video_path).toBe('new-answer.mp4');
		expect(updated.answer_evidence?.[0].time_spans?.[0].start).toBe('00:20');
		expect(updated.time_span?.end).toBe('00:25');
	});

	test('syncAnnotationForSave preserves multiple canonical evidence spans', () => {
		const annotation: Annotation = {
			question: 'Where is it?',
			answer: 'On the desk.',
			time_span: { start: '99:00', end: '99:01' },
			answer_video_path: 'legacy.mp4',
			answer_evidence: [
				{
					video_path: 'answer.mp4',
					time_spans: [
						{ start: '00:01', end: '00:03' },
						{ start: '00:04', end: '00:06' }
					]
				}
			],
			answer_details: {
				evidence_list: [
					{
						time_span: { start_time: '99:00', end_time: '99:01' },
						time_spans: [{ start_time: '00:01', end_time: '00:03' }],
						video_id: 'answer'
					}
				]
			}
		};

		const updated = syncAnnotationForSave(annotation);

		expect(updated.answer_evidence?.[0].time_spans).toHaveLength(2);
		expect(updated.answer_details?.evidence_list?.[0].time_spans).toHaveLength(2);
		expect(updated.answer_details?.evidence_list?.[0].time_span).toBeUndefined();
		expect(updated.time_span).toBeUndefined();
		expect(updated.answer_video_path).toBeUndefined();
	});

	test('syncAnnotationForSave uses legacy evidence only when canonical evidence is absent', () => {
		const annotation: Annotation = {
			question: 'Where is it?',
			answer: 'On the desk.',
			time_span: { start: '00:01', end: '00:03' },
			answer_video_path: 'legacy-answer.mp4'
		};

		const updated = syncAnnotationForSave(annotation);

		expect(updated.answer_evidence).toEqual([
			{
				video_path: 'legacy-answer.mp4',
				time_spans: [{ start: '00:01', end: '00:03' }]
			}
		]);
		expect(updated.time_span).toEqual({ start: '00:01', end: '00:03' });
		expect(updated.answer_video_path).toBe('legacy-answer.mp4');
	});

	test('validates timestamp ranges before save', () => {
		const result = validateQAAnnotation({
			question: 'Where is it?',
			answer: 'On the desk.',
			skill: 'visual_recall',
			question_time_spans: [{ start: '00:20', end: '00:10' }],
			answer_evidence: [{ time_spans: [{ start: '00:01', end: '00:03' }] }],
			answer_choices: [
				{ text: 'On the desk.', choice_type: 'correct', explanation: '' },
				{ text: 'Near the desk.', choice_type: 'vague', explanation: '' },
				{ text: 'In a drawer.', choice_type: 'incorrect', explanation: '' }
			],
			is_answerable: true
		});

		expect(result.valid).toBe(false);
		expect(result.errors).toContain('Question span 1 start must be before or equal to end');
	});

	test('parses hour-format timestamps', () => {
		expect(parseQATimestamp('1:02:45')).toBe(3765);
		expect(parseQATimestamp('00:10')).toBe(10);
		expect(parseQATimestamp('62:45')).toBe(3765);
		expect(parseQATimestamp('1:62:45')).toBeNull();
		expect(parseQATimestamp('1:02:99')).toBeNull();
		expect(parseQATimestamp('1:2:03')).toBeNull();
	});

	test('validates answer choice composition', () => {
		const invalidAnswerable = validateQAAnnotation({
			question: 'Where is it?',
			answer: 'On the desk.',
			skill: 'visual_recall',
			question_time_spans: [{ start: '00:01', end: '00:03' }],
			answer_choices: [
				{ text: 'On the desk.', choice_type: 'correct', explanation: '' },
				{ text: 'Also on the desk.', choice_type: 'correct', explanation: '' },
				{ text: 'In a drawer.', choice_type: 'incorrect', explanation: '' }
			],
			is_answerable: true
		});
		const invalidUnanswerable = validateQAAnnotation({
			question: 'Where is it?',
			answer: 'Not answerable',
			skill: 'visual_recall',
			question_time_spans: [{ start: '00:01', end: '00:03' }],
			answer_choices: [
				{ text: 'Not answerable', choice_type: 'correct', explanation: '' },
				{ text: 'In a drawer.', choice_type: 'incorrect', explanation: '' }
			],
			is_answerable: false
		});

		expect(invalidAnswerable.valid).toBe(false);
		expect(invalidAnswerable.errors).toContain('Answerable QAs need exactly one correct, one vague, and one incorrect choice');
		expect(invalidUnanswerable.valid).toBe(false);
		expect(invalidUnanswerable.errors).toContain('Unanswerable QAs must mark every answer choice as incorrect');
	});
});
