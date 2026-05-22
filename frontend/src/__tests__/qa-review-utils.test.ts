import { describe, expect, test } from 'vitest';
import type { Annotation } from '$lib/types';
import { computeQAClips, updateAnnotationClipSpan } from '$lib/utils/qa-review';

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
});
