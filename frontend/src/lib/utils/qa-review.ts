import type { Annotation, Evidence, TimeSpan } from '$lib/types';
import { deepClone } from '$lib/utils';

export interface QAReviewClip {
	key: string;
	type: 'question' | 'evidence';
	label: string;
	videoFilename: string;
	videoPath?: string;
	timeSpan: TimeSpan;
	questionSpanIndex?: number;
	evidenceIndex?: number;
	spanIndex?: number;
	reason?: string;
}

function hasExtension(value: string): boolean {
	return /\.[a-z0-9]+$/i.test(value.split(/[\\/]/).pop() || value);
}

export function normalizeVideoFilename(value?: string, fallback = ''): string {
	const raw = (value || fallback || '').trim();
	if (!raw) return '';
	if (raw.startsWith('/api/serve-video')) {
		try {
			const url = new URL(raw, 'http://local');
			const path = url.searchParams.get('path') || raw;
			const name = path.split(/[\\/]/).pop() || path;
			return hasExtension(name) ? name : `${name}.mp4`;
		} catch {
			return fallback;
		}
	}
	const name = raw.split(/[\\/]/).pop() || raw;
	return hasExtension(name) ? name : `${name}.mp4`;
}

export function videoSourceForFilename(videoFilename: string, videoPath?: string): string {
	if (videoPath && (videoPath.startsWith('/api/') || videoPath.startsWith('/uploads/') || /^[a-z]+:\/\//i.test(videoPath))) {
		return videoPath;
	}
	return `/uploads/${normalizeVideoFilename(videoPath || videoFilename)}`;
}

export function questionTimeSpans(annotation: Annotation): TimeSpan[] {
	if (annotation.question_time_spans?.length) return annotation.question_time_spans;
	const q = annotation.question_details || (annotation.question as any);
	if (q?.time_spans?.length) {
		return q.time_spans.map((span: any) => ({
			start: span.start || span.start_time || '',
			end: span.end || span.end_time || '',
			video_id: span.video_id,
		}));
	}
	if (annotation.question_time_span) return [annotation.question_time_span];
	return [];
}

export function answerEvidence(annotation: Annotation): Evidence[] {
	if (annotation.answer_evidence?.length) return annotation.answer_evidence;
	const evidenceList = annotation.answer_details?.evidence_list || (annotation.answer as any)?.evidence_list;
	if (Array.isArray(evidenceList)) {
		return evidenceList.map((ev: any) => {
			const spans = ev.time_spans?.length
				? ev.time_spans
				: ev.time_span
					? [ev.time_span]
					: [];
			return {
				reason: ev.reason,
				room: ev.room,
				modalities: ev.modalities,
				video_path: normalizeVideoFilename(ev.video_path || ev.video_id),
				time_spans: spans.map((span: any) => ({
					start: span.start || span.start_time || '',
					end: span.end || span.end_time || '',
					video_id: span.video_id || ev.video_id,
				})),
				bounding_boxes: ev.bounding_boxes,
			};
		});
	}
	if (annotation.time_span || annotation.answer_video_path) {
		return [{
			video_path: annotation.answer_video_path,
			time_spans: annotation.time_span ? [annotation.time_span] : [],
		}];
	}
	return [];
}

export function computeQAClips(annotation: Annotation, fallbackVideoFilename: string): QAReviewClip[] {
	const clips: QAReviewClip[] = [];
	const qVideo = normalizeVideoFilename(
		annotation.video_filename || annotation.question_details?.video_id || (annotation.question as any)?.video_id,
		fallbackVideoFilename,
	);
	questionTimeSpans(annotation).forEach((span, index) => {
		if (!span.start && !span.end) return;
		const videoFilename = normalizeVideoFilename(span.video_id, qVideo);
		clips.push({
			key: `question-${index}`,
			type: 'question',
			label: questionTimeSpans(annotation).length > 1 ? `Question ${index + 1}` : 'Question',
			videoFilename,
			videoPath: span.video_id,
			timeSpan: span,
			questionSpanIndex: index,
		});
	});

	answerEvidence(annotation).forEach((evidence, evidenceIndex) => {
		const videoFilename = normalizeVideoFilename(evidence.video_path, qVideo);
		(evidence.time_spans || []).forEach((span, spanIndex) => {
			if (!span.start && !span.end) return;
			const spanVideoFilename = normalizeVideoFilename(span.video_id, videoFilename);
			clips.push({
				key: `evidence-${evidenceIndex}-${spanIndex}`,
				type: 'evidence',
				label: `Evidence ${evidenceIndex + 1}${(evidence.time_spans?.length || 0) > 1 ? `.${spanIndex + 1}` : ''}`,
				videoFilename: spanVideoFilename,
				videoPath: span.video_id || evidence.video_path,
				timeSpan: span,
				evidenceIndex,
				spanIndex,
				reason: evidence.reason,
			});
		});
	});

	return clips;
}

export function updateAnnotationClipSpan(
	annotation: Annotation,
	clip: QAReviewClip,
	timeSpan: TimeSpan,
	videoPath?: string,
): Annotation {
	const updated = deepClone(annotation);
	if (clip.type === 'question') {
		const spans = questionTimeSpans(updated);
		const index = clip.questionSpanIndex ?? 0;
		spans[index] = { ...timeSpan, ...(videoPath ? { video_id: videoPath } : {}) };
		updated.question_time_spans = spans;
		updated.question_time_span = spans[0];
	} else {
		const evidence = answerEvidence(updated);
		const evidenceIndex = clip.evidenceIndex ?? 0;
		const spanIndex = clip.spanIndex ?? 0;
		if (!evidence[evidenceIndex]) {
			evidence[evidenceIndex] = { time_spans: [] };
		}
		if (videoPath) evidence[evidenceIndex].video_path = videoPath;
		const spans = [...(evidence[evidenceIndex].time_spans || [])];
		spans[spanIndex] = timeSpan;
		evidence[evidenceIndex].time_spans = spans;
		updated.answer_evidence = evidence;
		if (evidenceIndex === 0 && spanIndex === 0) {
			updated.time_span = timeSpan;
			updated.answer_video_path = evidence[0].video_path;
		}
	}
	return syncAnnotationForSave(updated);
}

export function syncAnnotationForSave(annotation: Annotation): Annotation {
	const updated = deepClone(annotation);
	const qSpans = questionTimeSpans(updated);
	if (qSpans.length > 0) {
		updated.question_time_spans = qSpans;
		updated.question_time_span = qSpans[0];
		if (updated.question_details) {
			updated.question_details.time_spans = qSpans.map((span) => ({
				start_time: span.start,
				end_time: span.end,
				video_id: span.video_id,
			}));
			updated.question_details.time_span = updated.question_details.time_spans[0];
		}
	}

	const evidence = answerEvidence(updated);
	updated.answer_evidence = evidence;
	if (evidence[0]?.time_spans?.[0]) {
		updated.time_span = evidence[0].time_spans[0];
		updated.answer_video_path = evidence[0].video_path;
	}
	if (updated.answer_details) {
		const existing = updated.answer_details.evidence_list || [];
		updated.answer_details.evidence_list = evidence.map((ev, index) => {
			const prior = existing[index] || {};
			return {
				...prior,
				reason: ev.reason || '',
				room: ev.room || '',
				modalities: ev.modalities || [],
				video_id: normalizeVideoFilename(ev.video_path).replace(/\.[^.]+$/, ''),
				time_span: ev.time_spans?.[0]
					? { start_time: ev.time_spans[0].start, end_time: ev.time_spans[0].end }
					: prior.time_span,
				time_spans: (ev.time_spans || []).map((span) => ({
					start_time: span.start,
					end_time: span.end,
					video_id: span.video_id || normalizeVideoFilename(ev.video_path).replace(/\.[^.]+$/, ''),
				})),
				bounding_boxes: (prior.bounding_boxes || []) as any,
			};
		});
	}
	return updated;
}
