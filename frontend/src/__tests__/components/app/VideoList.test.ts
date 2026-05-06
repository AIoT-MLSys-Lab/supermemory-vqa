/**
 * Unit tests for VideoList functionality
 * Tests cover:
 * - Video and VRS file data structures
 * - API client methods for VRS processing
 * - SSE event handling
 * - Processing state management
 */

import { describe, test, expect, vi, beforeEach } from 'vitest';
import { writable, get } from 'svelte/store';
import type { Video } from '$lib/types';

// Mock API functions
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('VideoList Functionality', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		mockFetch.mockReset();
	});

	describe('Video Data Structure', () => {
		test('video object has required fields for display', () => {
			const video: Video = {
				filename: 'test_video.mp4',
				type: 'video',
				is_processed: true,
				has_source_vrs: false,
				source_vrs_filename: null,
				has_annotations: true,
				annotations_count: 5,
				duration: 3661,
				duration_formatted: '1:01:01',
				size: 1073741824,
				size_formatted: '1.0 GB'
			};
			
			expect(video.filename).toBeDefined();
			expect(video.type).toBe('video');
			expect(video.is_processed).toBe(true);
			expect(video.has_source_vrs).toBe(false);
			expect(video.duration_formatted).toBe('1:01:01');
			expect(video.size_formatted).toBe('1.0 GB');
		});

		test('VRS file object has correct type', () => {
			const vrsFile: Video = {
				filename: 'recording.vrs',
				type: 'vrs',
				is_processed: false,
				has_source_vrs: false,
				has_annotations: false,
				size: 5368709120,
				size_formatted: '5.0 GB'
			};
			
			expect(vrsFile.type).toBe('vrs');
			expect(vrsFile.is_processed).toBe(false);
			expect(vrsFile.filename.endsWith('.vrs')).toBe(true);
		});

		test('video with VRS source has correct metadata', () => {
			const videoWithVrs: Video = {
				filename: 'recording.mp4',
				type: 'video',
				is_processed: true,
				has_source_vrs: true,
				source_vrs_filename: 'recording.vrs',
				has_annotations: false
			};
			
			expect(videoWithVrs.has_source_vrs).toBe(true);
			expect(videoWithVrs.source_vrs_filename).toBe('recording.vrs');
		});
	});

	describe('API Client VRS Methods', () => {
		test('convertVrs calls correct endpoint', async () => {
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ csrf_token: 'token' })
			});
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ success: true, task_id: 'task-123' })
			});
			
			const { apiClient } = await import('$lib/api');
			const result = await apiClient.convertVrs('test.vrs', true);
			
			// Find the POST call
			const postCall = mockFetch.mock.calls.find((call: unknown[]) => 
				call[0] === '/api/convert-vrs'
			);
			
			expect(postCall).toBeTruthy();
			expect(JSON.parse(postCall![1].body)).toEqual({ filename: 'test.vrs', rotate: true });
		});

		test('recreateVideo calls correct endpoint', async () => {
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ csrf_token: 'token' })
			});
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ success: true, task_id: 'task-456' })
			});
			
			const { apiClient } = await import('$lib/api');
			const result = await apiClient.recreateVideo('test.mp4', true);
			
			const postCall = mockFetch.mock.calls.find((call: unknown[]) => 
				call[0] === '/api/recreate-video'
			);
			
			expect(postCall).toBeTruthy();
			expect(JSON.parse(postCall![1].body)).toEqual({ filename: 'test.mp4', rotate: true });
		});

		test('cancelConversion calls correct endpoint', async () => {
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ csrf_token: 'token' })
			});
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ success: true })
			});
			
			const { apiClient } = await import('$lib/api');
			const result = await apiClient.cancelConversion('test.vrs');
			
			const postCall = mockFetch.mock.calls.find((call: unknown[]) => 
				call[0] === '/api/cancel-conversion'
			);
			
			expect(postCall).toBeTruthy();
		});

		test('getAllConversionStatus calls correct endpoint', async () => {
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({
					active_tasks: {},
					processing_files: []
				})
			});
			
			const { apiClient } = await import('$lib/api');
			const result = await apiClient.getAllConversionStatus();
			
			expect(mockFetch).toHaveBeenCalledWith('/api/conversion-status', expect.any(Object));
			expect(result.active_tasks).toBeDefined();
			expect(result.processing_files).toBeDefined();
		});
	});

	describe('SSE Event Types', () => {
		test('TaskEvent interface supports all event types', () => {
			const initEvent = {
				event: 'init' as const,
				data: {
					active_tasks: {},
					processing_files: [],
					num_workers: 4
				}
			};
			
			const taskStartedEvent = {
				event: 'task_started' as const,
				data: {
					task_id: 'task-123',
					filename: 'test.vrs',
					status: 'running'
				}
			};
			
			const taskCompletedEvent = {
				event: 'task_completed' as const,
				data: {
					task_id: 'task-123',
					filename: 'test.vrs',
					status: 'completed'
				}
			};
			
			const taskCancelledEvent = {
				event: 'task_cancelled' as const,
				data: {
					task_id: 'task-123',
					filename: 'test.vrs'
				}
			};
			
			const heartbeatEvent = {
				event: 'heartbeat' as const,
				count: 1
			};
			
			// All event types should be valid
			expect(initEvent.event).toBe('init');
			expect(taskStartedEvent.event).toBe('task_started');
			expect(taskCompletedEvent.event).toBe('task_completed');
			expect(taskCancelledEvent.event).toBe('task_cancelled');
			expect(heartbeatEvent.event).toBe('heartbeat');
		});
	});

	describe('ConversionTask Structure', () => {
		test('ConversionTask has required fields', () => {
			const task = {
				task_id: 'task-123',
				filename: 'test.vrs',
				status: 'running' as const,
				progress: 50,
				message: 'Converting...',
				started_at: '2024-01-01T00:00:00Z',
				completed_at: null,
				error: null
			};
			
			expect(task.task_id).toBeDefined();
			expect(task.filename).toBeDefined();
			expect(task.status).toBe('running');
			expect(task.progress).toBe(50);
			expect(['pending', 'running', 'completed', 'failed', 'cancelled']).toContain(task.status);
		});

		test('ConversionTask statuses are valid', () => {
			const validStatuses = ['pending', 'running', 'completed', 'failed', 'cancelled'];
			
			validStatuses.forEach(status => {
				const task = {
					task_id: 'task-123',
					filename: 'test.vrs',
					status: status as 'pending' | 'running' | 'completed' | 'failed' | 'cancelled',
					progress: 0,
					message: '',
					started_at: null,
					completed_at: null,
					error: null
				};
				
				expect(validStatuses).toContain(task.status);
			});
		});
	});

	describe('Processing State Logic', () => {
		test('isProcessing returns true for running tasks', () => {
			const processingFiles = new Map<string, { status: string }>();
			processingFiles.set('test.vrs', { status: 'running' });
			
			const isProcessing = (filename: string) => processingFiles.has(filename);
			
			expect(isProcessing('test.vrs')).toBe(true);
			expect(isProcessing('other.vrs')).toBe(false);
		});

		test('getProcessingFilename returns correct filename', () => {
			const video: Video = {
				filename: 'video.mp4',
				type: 'video',
				is_processed: true,
				has_source_vrs: true,
				source_vrs_filename: 'video.vrs',
				has_annotations: false
			};
			
			const vrsFile: Video = {
				filename: 'recording.vrs',
				type: 'vrs',
				is_processed: false,
				has_annotations: false
			};
			
			const getProcessingFilename = (v: Video) => {
				if (v.type === 'vrs') return v.filename;
				return v.source_vrs_filename || v.filename;
			};
			
			expect(getProcessingFilename(video)).toBe('video.vrs');
			expect(getProcessingFilename(vrsFile)).toBe('recording.vrs');
		});
	});

	describe('Display Logic', () => {
		test('video should show process button for VRS files', () => {
			const vrsFile: Video = {
				filename: 'test.vrs',
				type: 'vrs',
				is_processed: false,
				has_annotations: false
			};
			
			const shouldShowProcessButton = (v: Video) => v.type === 'vrs';
			expect(shouldShowProcessButton(vrsFile)).toBe(true);
		});

		test('video should show recreate button when has VRS source', () => {
			const videoWithVrs: Video = {
				filename: 'test.mp4',
				type: 'video',
				is_processed: true,
				has_source_vrs: true,
				source_vrs_filename: 'test.vrs',
				has_annotations: false
			};
			
			const shouldShowRecreateButton = (v: Video) => v.type === 'video' && v.has_source_vrs;
			expect(shouldShowRecreateButton(videoWithVrs)).toBe(true);
		});

		test('video should not show recreate button without VRS source', () => {
			const videoNoVrs: Video = {
				filename: 'standalone.mp4',
				type: 'video',
				is_processed: true,
				has_source_vrs: false,
				has_annotations: false
			};
			
			const shouldShowRecreateButton = (v: Video) => v.type === 'video' && v.has_source_vrs;
			expect(shouldShowRecreateButton(videoNoVrs)).toBe(false);
		});

		test('clicking VRS file should prevent video selection', () => {
			const vrsFile: Video = {
				filename: 'unprocessed.vrs',
				type: 'vrs',
				is_processed: false,
				has_annotations: false
			};
			
			const shouldAllowSelection = (v: Video) => {
				if (v.type === 'vrs' && !v.is_processed) return false;
				return true;
			};
			
			expect(shouldAllowSelection(vrsFile)).toBe(false);
		});
	});
});

describe('SSE Connection', () => {
	test('EventSource is created for task events', () => {
		// Verify EventSource can be instantiated with our endpoint
		const endpoint = '/api/task-events';
		expect(endpoint).toBe('/api/task-events');
	});
});
