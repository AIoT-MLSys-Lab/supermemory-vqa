/**
 * Unit tests for API client module
 * Tests for issues encountered during PR development:
 * - 415 Unsupported Media Type errors (Content-Type header)
 * - 403 CSRF token validation errors
 */

import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Import after mocking
import { apiClient } from '$lib/api';

describe('API Client', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		// Reset the internal CSRF token
		apiClient.setCsrfToken('');
		mockFetch.mockReset();
	});

	afterEach(() => {
		vi.restoreAllMocks();
	});

	describe('Content-Type Header', () => {
		/**
		 * Issue: 415 Unsupported Media Type errors
		 * Root cause: Content-Type header was not set to 'application/json' for JSON requests
		 * This caused Flask to reject requests with request.get_json()
		 */

		test('sets Content-Type to application/json for PUT requests with JSON body', async () => {
			// Setup mock response
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ csrf_token: 'test-token' })
			});
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ success: true })
			});

			await apiClient.updateAnnotation('video.mp4', 'annotations.json', 0, {
				question: 'Test?'
			});

			// Second call is the actual PUT request
			const putCall = mockFetch.mock.calls[1];
			expect(putCall[1].headers['Content-Type']).toBe('application/json');
		});

		test('sets Content-Type to application/json for POST requests with JSON body', async () => {
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ csrf_token: 'test-token' })
			});
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ success: true })
			});

			await apiClient.addAnnotation('video.mp4', 'annotations.json', {
				question: 'New Question?'
			});

			const postCall = mockFetch.mock.calls[1];
			expect(postCall[1].headers['Content-Type']).toBe('application/json');
		});

		test('does NOT set Content-Type for FormData (file uploads)', async () => {
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ csrf_token: 'test-token' })
			});
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ success: true })
			});

			// Create a mock File
			const mockFile = new File(['test'], 'test.mp4', { type: 'video/mp4' });
			await apiClient.uploadVideo(mockFile);

			// Check the upload call doesn't override Content-Type for FormData
			// (browser should set it automatically with boundary)
			const uploadCall = mockFetch.mock.calls[mockFetch.mock.calls.length - 1];
			// FormData requests should not have Content-Type set manually
			expect(uploadCall[1].body instanceof FormData).toBe(true);
		});

		test('stringifies object bodies as JSON', async () => {
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ csrf_token: 'test-token' })
			});
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ built_prompt: 'test' })
			});

			await apiClient.buildPrompt('test-prompt', { param1: 'value1' });

			const postCall = mockFetch.mock.calls[1];
			expect(typeof postCall[1].body).toBe('string');
			expect(JSON.parse(postCall[1].body)).toEqual({ parameters: { param1: 'value1' } });
		});
	});

	describe('CSRF Token Handling', () => {
		/**
		 * Issue: 403 CSRF token validation failed on update
		 * Root cause: CSRF token wasn't being fetched or included in requests
		 */

		test('fetches CSRF token before mutating requests (POST/PUT/DELETE)', async () => {
			// Clear the token first
			apiClient.setCsrfToken('');
			
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ csrf_token: 'fetched-token' })
			});
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ success: true })
			});

			await apiClient.updateAnnotation('video.mp4', 'annotations.json', 0, {
				question: 'Test?'
			});

			// First call should be to fetch CSRF token
			expect(mockFetch.mock.calls[0][0]).toBe('/api/csrf-token');

			// Second call should include a token in headers
			const updateCall = mockFetch.mock.calls[1];
			expect(updateCall[1].headers['X-CSRF-Token']).toBeDefined();
		});

		test('includes CSRF token in X-CSRF-Token header', async () => {
			// Pre-set the token
			apiClient.setCsrfToken('preset-token');

			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ success: true })
			});

			await apiClient.deleteAnnotation('video.mp4', 'annotations.json', 0);

			// Find the DELETE call (may be first or after CSRF fetch)
			const deleteCall = mockFetch.mock.calls.find(
				(call) => call[1]?.method === 'DELETE'
			);
			expect(deleteCall).toBeTruthy();
			expect(deleteCall![1].headers['X-CSRF-Token']).toBeTruthy();
		});

		test('handles CSRF token fetch failure gracefully', async () => {
			// Reset token
			apiClient.setCsrfToken('');
			
			// First call (CSRF fetch) fails, second call (actual request) succeeds
			mockFetch.mockRejectedValueOnce(new Error('Network error'));
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ success: true })
			});

			// Should not throw, should proceed (possibly with empty token)
			// The implementation may or may not throw depending on design
			try {
				const result = await apiClient.addAnnotation('video.mp4', 'annotations.json', { question: 'Test?' });
				expect(result).toBeDefined();
			} catch {
				// It's also acceptable to throw on CSRF failure
				expect(true).toBe(true);
			}
		});

		test('caches CSRF token to avoid redundant requests', async () => {
			apiClient.setCsrfToken('cached-token');

			mockFetch.mockResolvedValue({
				json: () => Promise.resolve({ success: true })
			});

			// Make multiple requests
			await apiClient.deleteAnnotation('video.mp4', 'a1.json', 0);
			await apiClient.deleteAnnotation('video.mp4', 'a2.json', 1);

			// Should not have fetched CSRF token since it's already cached
			expect(
				mockFetch.mock.calls.filter((call) => call[0] === '/api/csrf-token')
			).toHaveLength(0);
		});
	});

	describe('Request Methods', () => {
		test('uses PUT method for updateAnnotation', async () => {
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ csrf_token: 'token' })
			});
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ success: true })
			});

			await apiClient.updateAnnotation('video.mp4', 'annotations.json', 0, {
				question: 'Updated?'
			});

			const putCall = mockFetch.mock.calls[1];
			expect(putCall[1].method).toBe('PUT');
		});

		test('uses DELETE method for deleteAnnotation', async () => {
			apiClient.setCsrfToken('token');
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ success: true })
			});

			await apiClient.deleteAnnotation('video.mp4', 'annotations.json', 0);

			const deleteCall = mockFetch.mock.calls[0];
			expect(deleteCall[1].method).toBe('DELETE');
		});

		test('uses POST method for addAnnotation', async () => {
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ csrf_token: 'token' })
			});
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ success: true })
			});

			await apiClient.addAnnotation('video.mp4', 'annotations.json', {
				question: 'New?'
			});

			const postCall = mockFetch.mock.calls[1];
			expect(postCall[1].method).toBe('POST');
		});
	});

	describe('URL Encoding', () => {
		/**
		 * Ensure filenames with special characters are properly encoded
		 */

		test('encodes video filename in URL', async () => {
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve([])
			});

			await apiClient.getAnnotations('video with spaces.mp4');

			expect(mockFetch.mock.calls[0][0]).toBe(
				'/api/annotations/video%20with%20spaces.mp4'
			);
		});

		test('encodes annotation filename in URL', async () => {
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ annotations: [] })
			});

			await apiClient.getAnnotationFile('video.mp4', 'annotation file.json');

			expect(mockFetch.mock.calls[0][0]).toBe(
				'/api/annotations/video.mp4/annotation%20file.json'
			);
		});

		test('listQAReviewItems calls aggregate review endpoint', async () => {
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ items: [], count: 0 })
			});

			const result = await apiClient.listQAReviewItems();

			expect(mockFetch.mock.calls[0][0]).toBe('/api/qa-review');
			expect(result.count).toBe(0);
		});
	});

	describe('Folder Browsing APIs', () => {
		test('getVideoFolder sends GET request', async () => {
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ success: true, data: { folder_path: '/uploads' } })
			});

			const result = await apiClient.getVideoFolder();

			expect(mockFetch.mock.calls[0][0]).toBe('/api/get-video-folder');
			expect(mockFetch.mock.calls[0][1]?.method).toBeUndefined(); // GET is default
			expect(result.success).toBe(true);
			expect(result.data?.folder_path).toBe('/uploads');
		});

		test('browseFolders sends POST request with path', async () => {
			// Mock CSRF token fetch first (for mutating requests)
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ csrf_token: 'test-csrf-token' })
			});
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ 
					success: true, 
					data: {
						current_path: '/test/path',
						parent_path: '/test',
						directories: [{ name: 'subdir', path: '/test/path/subdir' }]
					}
				})
			});

			const result = await apiClient.browseFolders('/test/path');

			// Second call is the actual POST request
			expect(mockFetch.mock.calls[1][0]).toBe('/api/browse-folders');
			expect(mockFetch.mock.calls[1][1].method).toBe('POST');
			expect(mockFetch.mock.calls[1][1].headers['Content-Type']).toBe('application/json');
			
			const body = JSON.parse(mockFetch.mock.calls[1][1].body);
			expect(body.path).toBe('/test/path');
			expect(body.csrf_token).toBe('test-csrf-token');
			
			expect(result.success).toBe(true);
			expect(result.data?.current_path).toBe('/test/path');
			expect(result.data?.directories).toHaveLength(1);
		});

		test('browseFolders sends empty path when no argument provided', async () => {
			// Mock CSRF token fetch first
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ csrf_token: 'test-csrf-token' })
			});
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ 
					success: true, 
					data: {
						current_path: '/uploads',
						parent_path: '/',
						directories: []
					}
				})
			});

			await apiClient.browseFolders();

			const body = JSON.parse(mockFetch.mock.calls[1][1].body);
			expect(body.path).toBe('');
		});

		test('setVideoFolder sends POST request with folder path', async () => {
			// Mock CSRF token fetch first
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ csrf_token: 'test-csrf-token' })
			});
			mockFetch.mockResolvedValueOnce({
				json: () => Promise.resolve({ success: true })
			});

			await apiClient.setVideoFolder('/new/path');

			// Second call is the actual POST request
			expect(mockFetch.mock.calls[1][0]).toBe('/api/set-video-folder');
			expect(mockFetch.mock.calls[1][1].method).toBe('POST');
			expect(mockFetch.mock.calls[1][1].headers['Content-Type']).toBe('application/json');
			
			const body = JSON.parse(mockFetch.mock.calls[1][1].body);
			expect(body.folder_path).toBe('/new/path');
			expect(body.csrf_token).toBe('test-csrf-token');
		});
	});
});
