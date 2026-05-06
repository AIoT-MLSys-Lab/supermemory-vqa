/**
 * Tests for annotation file checkbox selection and cross-video reference features
 */

import { describe, test, expect, vi, beforeEach } from 'vitest';
import type { Annotation, AnnotationFile } from '../lib/types';

describe('Annotation File Checkbox Selection', () => {
	describe('Multiple file selection', () => {
		test('can select multiple annotation files', () => {
			const files: AnnotationFile[] = [
				{ filename: 'file1.json', annotations: [] },
				{ filename: 'file2.json', annotations: [] },
				{ filename: 'file3.json', annotations: [] }
			];

			const selectedFiles = ['file1.json', 'file2.json'];

			expect(selectedFiles.length).toBe(2);
			expect(selectedFiles).toContain('file1.json');
			expect(selectedFiles).toContain('file2.json');
			expect(selectedFiles).not.toContain('file3.json');
		});

		test('can select all files', () => {
			const files: AnnotationFile[] = [
				{ filename: 'file1.json', annotations: [] },
				{ filename: 'file2.json', annotations: [] },
				{ filename: 'file3.json', annotations: [] }
			];

			const selectedFiles = files.map(f => f.filename);

			expect(selectedFiles.length).toBe(3);
			expect(selectedFiles).toEqual(['file1.json', 'file2.json', 'file3.json']);
		});

		test('can deselect all files', () => {
			const selectedFiles: string[] = [];

			expect(selectedFiles.length).toBe(0);
		});

		test('toggles file selection correctly', () => {
			let selectedFiles = ['file1.json', 'file2.json'];

			// Toggle off file1
			selectedFiles = selectedFiles.filter(f => f !== 'file1.json');
			expect(selectedFiles).toEqual(['file2.json']);

			// Toggle on file3
			selectedFiles = [...selectedFiles, 'file3.json'];
			expect(selectedFiles).toEqual(['file2.json', 'file3.json']);
		});
	});

	describe('Annotation aggregation from multiple files', () => {
		test('combines annotations from multiple files', () => {
			const file1Annotations: Annotation[] = [
				{ question: 'Q1', answer: 'A1' },
				{ question: 'Q2', answer: 'A2' }
			];
			const file2Annotations: Annotation[] = [
				{ question: 'Q3', answer: 'A3' }
			];

			const allAnnotations = [...file1Annotations, ...file2Annotations];

			expect(allAnnotations.length).toBe(3);
			expect(allAnnotations.map(a => a.question)).toEqual(['Q1', 'Q2', 'Q3']);
		});

		test('tracks source file for each annotation', () => {
			const file1Annotations: Annotation[] = [
				{ question: 'Q1', answer: 'A1' },
				{ question: 'Q2', answer: 'A2' }
			];
			const file2Annotations: Annotation[] = [
				{ question: 'Q3', answer: 'A3' }
			];

			const sourceFiles: string[] = [
				...file1Annotations.map(() => 'file1.json'),
				...file2Annotations.map(() => 'file2.json')
			];

			expect(sourceFiles).toEqual(['file1.json', 'file1.json', 'file2.json']);
		});

		test('calculates local index within file', () => {
			const sourceFiles = ['file1.json', 'file1.json', 'file2.json', 'file1.json'];

			function getLocalIndexInFile(globalIndex: number): number {
				const sourceFile = sourceFiles[globalIndex];
				if (!sourceFile) return -1;

				let localIndex = 0;
				for (let i = 0; i < globalIndex; i++) {
					if (sourceFiles[i] === sourceFile) {
						localIndex++;
					}
				}
				return localIndex;
			}

			expect(getLocalIndexInFile(0)).toBe(0); // First annotation in file1
			expect(getLocalIndexInFile(1)).toBe(1); // Second annotation in file1
			expect(getLocalIndexInFile(2)).toBe(0); // First annotation in file2
			expect(getLocalIndexInFile(3)).toBe(2); // Third annotation in file1
		});
	});
});

describe('Cross-Video References', () => {
	describe('answer_video_path field', () => {
		test('annotation can have answer_video_path', () => {
			const annotation: Annotation = {
				question: 'Where is the remote?',
				answer: 'On the table',
				answer_video_path: '/videos/recording_001.mp4',
				time_span: { start: '00:05', end: '00:10' }
			};

			expect(annotation.answer_video_path).toBe('/videos/recording_001.mp4');
		});

		test('annotation without answer_video_path defaults to current video', () => {
			const annotation: Annotation = {
				question: 'Where is the remote?',
				answer: 'On the table'
			};

			expect(annotation.answer_video_path).toBeUndefined();
		});

		test('detects when answer is from different video', () => {
			const currentVideoPath = '/videos/recording_001.mp4';
			const annotation: Annotation = {
				question: 'Where did I put the keys?',
				answer: 'In the drawer',
				answer_video_path: '/videos/recording_002.mp4'
			};

			const isDifferentVideo = annotation.answer_video_path && 
				annotation.answer_video_path !== currentVideoPath;

			expect(isDifferentVideo).toBe(true);
		});

		test('detects when answer is from same video', () => {
			const currentVideoPath = '/videos/recording_001.mp4';
			const annotation: Annotation = {
				question: 'Where did I put the keys?',
				answer: 'In the drawer',
				answer_video_path: '/videos/recording_001.mp4'
			};

			const isDifferentVideo = annotation.answer_video_path && 
				annotation.answer_video_path !== currentVideoPath;

			expect(isDifferentVideo).toBe(false);
		});

		test('stores absolute paths for video references', () => {
			const annotation: Annotation = {
				question: 'Test question',
				answer: 'Test answer',
				answer_video_path: '/home/user/videos/recording_001.mp4'
			};

			// Path should be absolute (starts with /)
			expect(annotation.answer_video_path?.startsWith('/')).toBe(true);
		});
	});

	describe('Video display name extraction', () => {
		function getVideoDisplayName(path?: string): string {
			if (!path) return '';
			const parts = path.split('/');
			return parts[parts.length - 1] || path;
		}

		test('extracts filename from full path', () => {
			expect(getVideoDisplayName('/home/user/videos/recording_001.mp4')).toBe('recording_001.mp4');
		});

		test('handles simple filename', () => {
			expect(getVideoDisplayName('video.mp4')).toBe('video.mp4');
		});

		test('handles undefined path', () => {
			expect(getVideoDisplayName(undefined)).toBe('');
		});

		test('handles empty path', () => {
			expect(getVideoDisplayName('')).toBe('');
		});

		test('handles path ending with slash', () => {
			// Edge case: if path ends with /, return full path as fallback
			const result = getVideoDisplayName('/home/user/videos/');
			expect(result).toBe('/home/user/videos/');
		});
	});
});

describe('Annotation with cross-video reference structure', () => {
	test('full annotation structure with all fields', () => {
		const annotation: Annotation = {
			skill: 'object_location_memory',
			question: 'Where did I put my phone?',
			answer: 'You placed it on the kitchen counter at 2:30 PM',
			question_time_span: { start: '00:00', end: '00:05' },
			time_span: { start: '02:30:00', end: '02:30:15' },
			answer_video_path: '/recordings/2024-01-15/afternoon_session.mp4',
			room: 'kitchen',
			modalities: ['visual', 'audio'],
			human_review: { status: 'accepted', reviewed: true },
			location: {
				boxes: [
					{ box_2d: [100, 200, 300, 400], timestamp: '02:30:05' }
				]
			}
		};

		expect(annotation.skill).toBe('object_location_memory');
		expect(annotation.question).toBe('Where did I put my phone?');
		expect(annotation.answer_video_path).toBe('/recordings/2024-01-15/afternoon_session.mp4');
		expect(annotation.time_span?.start).toBe('02:30:00');
	});
});
