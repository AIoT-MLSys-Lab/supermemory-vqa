/**
 * API client for communicating with the backend
 * @module api
 */

import type {
	Video,
	Annotation,
	AnnotationFile,
	ModelsResponse,
	Prompt,
	BuiltPrompt,
	GenerateAnnotationsParams,
	ApiResponse,
	CaptionFile
	, CaptionSearchResponse
} from '$lib/types';

class ApiClient {
	private csrfToken: string = '';
	private csrfTokenPromise: Promise<string> | null = null;

	/**
	 * Fetch CSRF token from server
	 */
	async fetchCsrfToken(): Promise<string> {
		if (this.csrfToken) {
			return this.csrfToken;
		}

		// Avoid concurrent requests
		if (this.csrfTokenPromise) {
			return this.csrfTokenPromise;
		}

		this.csrfTokenPromise = (async (): Promise<string> => {
			try {
				const response = await fetch('/api/csrf-token');
				const data = await response.json();
				this.csrfToken = data.csrf_token || '';
				return this.csrfToken;
			} catch (error) {
				console.error('Failed to fetch CSRF token:', error);
				return '';
			} finally {
				this.csrfTokenPromise = null;
			}
		})();

		return this.csrfTokenPromise;
	}

	/**
	 * Get CSRF token from cache or window
	 */
	getCsrfToken(): string {
		if (typeof window !== 'undefined') {
			return (window as unknown as { CSRF_TOKEN?: string }).CSRF_TOKEN || this.csrfToken || '';
		}
		return this.csrfToken || '';
	}

	/**
	 * Set CSRF token
	 */
	setCsrfToken(token: string): void {
		this.csrfToken = token;
	}

	/**
	 * Make a fetch request with common options
	 */
	private async request<T>(url: string, options: RequestInit = {}): Promise<T> {
		// Ensure CSRF token is loaded for mutating requests
		if (options.method && ['POST', 'PUT', 'DELETE', 'PATCH'].includes(options.method)) {
			if (!this.csrfToken) {
				await this.fetchCsrfToken();
			}
		}

		const defaultHeaders: Record<string, string> = {
			'X-CSRF-Token': this.getCsrfToken()
		};

		// Handle body - if it's an object (not FormData), stringify and set Content-Type
		if (options.body && !(options.body instanceof FormData)) {
			// If body is already a string, assume it's JSON and set Content-Type
			if (typeof options.body === 'string') {
				defaultHeaders['Content-Type'] = 'application/json';
			} else if (typeof options.body === 'object') {
				options.body = JSON.stringify(options.body);
				defaultHeaders['Content-Type'] = 'application/json';
			}
		}

		const mergedOptions: RequestInit = {
			...options,
			headers: {
				...defaultHeaders,
				...(options.headers as Record<string, string>)
			}
		};

		const response = await fetch(url, mergedOptions);
		return response.json();
	}

	/**
	 * Load available models from API
	 */
	async loadModels(): Promise<ModelsResponse> {
		const data = await this.request<ModelsResponse | { models?: unknown[]; source?: string; reason?: string }>('/api/models');
		return {
			models: (data.models as ModelsResponse['models']) || [],
			source: data.source || 'unknown',
			reason: data.reason || ''
		};
	}

	/**
	 * Load available prompts from API
	 */
	async loadPrompts(): Promise<Prompt[]> {
		return this.request<Prompt[]>('/api/prompts');
	}

	/**
	 * Get prompt details by ID
	 */
	async getPromptDetails(promptId: string): Promise<Prompt> {
		return this.request<Prompt>(`/api/prompts/${promptId}`);
	}

	/**
	 * Build and preview a prompt
	 */
	async buildPrompt(promptId: string, parameters: Record<string, unknown>): Promise<BuiltPrompt> {
		return this.request<BuiltPrompt>(`/api/prompts/${promptId}/build`, {
			method: 'POST',
			body: JSON.stringify({ parameters })
		});
	}

	/**
	 * Get current video folder
	 */
	async getVideoFolder(): Promise<{ success: boolean; data?: { folder_path: string }; error?: string }> {
		return this.request<{ success: boolean; data?: { folder_path: string }; error?: string }>('/api/get-video-folder');
	}

	/**
	 * Browse folders on server
	 */
	async browseFolders(path?: string): Promise<{
		success: boolean;
		data?: {
			current_path: string;
			parent_path: string | null;
			directories: { name: string; path: string }[];
		};
		error?: string;
	}> {
		return this.request<{
			success: boolean;
			data?: {
				current_path: string;
				parent_path: string | null;
				directories: { name: string; path: string }[];
			};
			error?: string;
		}>('/api/browse-folders', {
			method: 'POST',
			body: JSON.stringify({ path: path || '', csrf_token: this.getCsrfToken() })
		});
	}

	/**
	 * Set video folder
	 */
	async setVideoFolder(folderPath: string): Promise<ApiResponse<void>> {
		return this.request<ApiResponse<void>>('/api/set-video-folder', {
			method: 'POST',
			body: JSON.stringify({ folder_path: folderPath, csrf_token: this.getCsrfToken() })
		});
	}

	/**
	 * Browse files and folders on server
	 * Returns both directories and video files at the given path
	 */
	async browseFiles(path?: string): Promise<{
		success: boolean;
		data?: {
			current_path: string;
			parent_path: string | null;
			directories: { name: string; path: string }[];
			video_files: { name: string; path: string }[];
		};
		error?: string;
	}> {
		return this.request<{
			success: boolean;
			data?: {
				current_path: string;
				parent_path: string | null;
				directories: { name: string; path: string }[];
				video_files: { name: string; path: string }[];
			};
			error?: string;
		}>('/api/browse-files', {
			method: 'POST',
			body: JSON.stringify({ path: path || '', csrf_token: this.getCsrfToken() })
		});
	}

	/**
	 * Upload a video file
	 */
	async uploadVideo(file: File): Promise<ApiResponse<Video>> {
		const formData = new FormData();
		formData.append('video', file);
		formData.append('csrf_token', this.getCsrfToken());

		return this.request<ApiResponse<Video>>('/api/upload', {
			method: 'POST',
			body: formData
		});
	}

	/**
	 * List all videos
	 */
	async listVideos(): Promise<Video[]> {
		return this.request<Video[]>('/api/videos');
	}

	/**
	 * Get annotations for a video
	 */
	async getAnnotations(filename: string): Promise<AnnotationFile[]> {
		return this.request<AnnotationFile[]>(`/api/annotations/${encodeURIComponent(filename)}`);
	}

	/**
	 * Get annotation file contents
	 */
	async getAnnotationFile(videoFilename: string, annotationFilename: string): Promise<AnnotationFile> {
		return this.request<AnnotationFile>(
			`/api/annotations/${encodeURIComponent(videoFilename)}/${encodeURIComponent(annotationFilename)}`
		);
	}

	/**
	 * Update an annotation
	 */
	async updateAnnotation(
		videoFilename: string,
		annotationFilename: string,
		index: number,
		annotation: Annotation
	): Promise<ApiResponse<Annotation>> {
		// Ensure CSRF token is loaded
		await this.fetchCsrfToken();
		return this.request<ApiResponse<Annotation>>(
			`/api/annotations/${encodeURIComponent(videoFilename)}/${encodeURIComponent(annotationFilename)}/${index}`,
			{
				method: 'PUT',
				body: JSON.stringify(annotation)
			}
		);
	}

	/**
	 * Delete an annotation
	 */
	async deleteAnnotation(
		videoFilename: string,
		annotationFilename: string,
		index: number
	): Promise<ApiResponse<void>> {
		// Ensure CSRF token is loaded
		await this.fetchCsrfToken();
		return this.request<ApiResponse<void>>(
			`/api/annotations/${encodeURIComponent(videoFilename)}/${encodeURIComponent(annotationFilename)}/${index}`,
			{ method: 'DELETE' }
		);
	}

	/**
	 * Add an annotation to a file
	 */
	async addAnnotation(
		videoFilename: string,
		annotationFilename: string,
		annotation: Annotation
	): Promise<ApiResponse<Annotation>> {
		// Ensure CSRF token is loaded
		await this.fetchCsrfToken();
		return this.request<ApiResponse<Annotation>>(
			`/api/annotations/${encodeURIComponent(videoFilename)}/${encodeURIComponent(annotationFilename)}/add`,
			{
				method: 'POST',
				body: JSON.stringify(annotation)
			}
		);
	}

	/**
	 * Create a new annotation file
	 */
	async createAnnotationFile(videoFilename: string): Promise<ApiResponse<AnnotationFile>> {
		// Ensure CSRF token is loaded
		await this.fetchCsrfToken();
		return this.request<ApiResponse<AnnotationFile>>(
			`/api/annotation-files/${encodeURIComponent(videoFilename)}`,
			{
				method: 'POST'
			}
		);
	}

	/**
	 * Delete an annotation file
	 */
	async deleteAnnotationFile(
		videoFilename: string,
		annotationFilename: string
	): Promise<ApiResponse<void>> {
		// Ensure CSRF token is loaded
		await this.fetchCsrfToken();
		return this.request<ApiResponse<void>>(
			`/api/annotation-files/${encodeURIComponent(videoFilename)}/${encodeURIComponent(annotationFilename)}`,
			{ method: 'DELETE' }
		);
	}

	/**
	 * Get annotation summary for a video
	 */
	async getSummary(videoFilename: string): Promise<Record<string, unknown>> {
		return this.request<Record<string, unknown>>(`/api/summary/${encodeURIComponent(videoFilename)}`);
	}

	/**
	 * Generate annotations for a video
	 */
	async generateAnnotations(params: GenerateAnnotationsParams): Promise<ApiResponse<AnnotationFile>> {
		return this.request<ApiResponse<AnnotationFile>>('/api/annotate', {
			method: 'POST',
			body: JSON.stringify({
				video_filename: params.video_filename,
				model_id: params.model_id,
				prompt_id: params.prompt_id,
				prompt_params: params.prompt_params
			})
		});
	}

	/**
	 * Convert a VRS file to MP4 (starts background processing)
	 */
	async convertVrs(filename: string, rotate: boolean = true): Promise<ApiResponse<{ task_id: string; filename: string; status: string; message: string }>> {
		return this.request<ApiResponse<{ task_id: string; filename: string; status: string; message: string }>>('/api/convert-vrs', {
			method: 'POST',
			body: JSON.stringify({ filename, rotate })
		});
	}

	/**
	 * Recreate a video from its source VRS file (starts background processing)
	 */
	async recreateVideo(filename: string, rotate: boolean = true): Promise<ApiResponse<{ task_id: string; filename: string; status: string; message: string }>> {
		return this.request<ApiResponse<{ task_id: string; filename: string; status: string; message: string }>>('/api/recreate-video', {
			method: 'POST',
			body: JSON.stringify({ filename, rotate })
		});
	}

	/**
	 * Get conversion status for a specific file
	 */
	async getConversionStatus(filename: string): Promise<{ filename: string; is_processing: boolean; task: ConversionTask | null }> {
		return this.request<{ filename: string; is_processing: boolean; task: ConversionTask | null }>(`/api/conversion-status/${encodeURIComponent(filename)}`);
	}

	/**
	 * Get all active conversion statuses
	 */
	async getAllConversionStatus(): Promise<{ active_tasks: Record<string, ConversionTask>; processing_files: string[] }> {
		return this.request<{ active_tasks: Record<string, ConversionTask>; processing_files: string[] }>('/api/conversion-status');
	}

	/**
	 * Cancel a VRS conversion
	 */
	async cancelConversion(filename?: string, taskId?: string): Promise<ApiResponse<void>> {
		return this.request<ApiResponse<void>>('/api/cancel-conversion', {
			method: 'POST',
			body: JSON.stringify({ filename, task_id: taskId })
		});
	}

	/**
	 * Get file metadata (duration, size) for a video or VRS file
	 */
	async getFileMetadata(filename: string): Promise<{ filename: string; duration?: number; duration_formatted?: string; size?: number; size_formatted?: string }> {
		return this.request<{ filename: string; duration?: number; duration_formatted?: string; size?: number; size_formatted?: string }>(`/api/file-metadata/${encodeURIComponent(filename)}`);
	}

	// --- Caption API methods ---

	/**
	 * List caption files for a video
	 */
	async listCaptionFiles(videoFilename: string): Promise<CaptionFile[]> {
		return this.request<CaptionFile[]>(`/api/captions/${encodeURIComponent(videoFilename)}`);
	}

	/**
	 * Get full caption file detail
	 */
	async getCaptionFile(videoFilename: string, captionFilename: string): Promise<CaptionFile> {
		return this.request<CaptionFile>(
			`/api/captions/${encodeURIComponent(videoFilename)}/${encodeURIComponent(captionFilename)}`
		);
	}

	/**
	 * Update a caption file (captions, human_review, etc.)
	 */
	async updateCaptionFile(
		videoFilename: string,
		captionFilename: string,
		data: Partial<CaptionFile>
	): Promise<ApiResponse<CaptionFile>> {
		await this.fetchCsrfToken();
		return this.request<ApiResponse<CaptionFile>>(
			`/api/captions/${encodeURIComponent(videoFilename)}/${encodeURIComponent(captionFilename)}`,
			{ method: 'PUT', body: JSON.stringify(data) }
		);
	}

	/**
	 * Create a new caption file
	 */
	async createCaptionFile(
		videoFilename: string,
		captionType: string,
		captions: CaptionFile['captions']
	): Promise<ApiResponse<CaptionFile>> {
		await this.fetchCsrfToken();
		return this.request<ApiResponse<CaptionFile>>(
			`/api/caption-files/${encodeURIComponent(videoFilename)}`,
			{ method: 'POST', body: JSON.stringify({ caption_type: captionType, captions }) }
		);
	}

	/**
	 * Delete a caption file
	 */
	async deleteCaptionFile(
		videoFilename: string,
		captionFilename: string
	): Promise<ApiResponse<void>> {
		await this.fetchCsrfToken();
		return this.request<ApiResponse<void>>(
			`/api/caption-files/${encodeURIComponent(videoFilename)}/${encodeURIComponent(captionFilename)}`,
			{ method: 'DELETE' }
		);
	}

	/**
	 * Search indexed caption descriptions.
	 */
	async searchCaptions(params: {
		query: string;
		regex?: boolean;
		semantic?: boolean;
		keys?: string[];
		page?: number;
		per_page?: number;
	}): Promise<CaptionSearchResponse> {
		const searchParams = new URLSearchParams();
		searchParams.set('q', params.query);
		searchParams.set('regex', String(params.regex ?? true));
		searchParams.set('semantic', String(params.semantic ?? true));
		if (params.keys && params.keys.length > 0) {
			searchParams.set('keys', params.keys.join(','));
		}
		searchParams.set('page', String(params.page ?? 1));
		searchParams.set('per_page', String(params.per_page ?? 20));
		return this.request<CaptionSearchResponse>(`/api/search/captions?${searchParams.toString()}`);
	}

	/**
	 * Create an EventSource for real-time task events via SSE
	 * This replaces polling for more efficient status updates
	 */
	createTaskEventSource(
		onEvent: (event: TaskEvent) => void,
		onError?: (error: Event) => void,
		onOpen?: () => void
	): EventSource {
		const eventSource = new EventSource('/api/task-events');

		eventSource.onopen = () => {
			console.log('SSE connection opened successfully');
			if (onOpen) {
				onOpen();
			}
		};

		eventSource.onmessage = (event) => {
			try {
				const data = JSON.parse(event.data) as TaskEvent;
				onEvent(data);
			} catch (err) {
				console.error('Failed to parse SSE event:', err);
			}
		};

		eventSource.onerror = (error) => {
			console.error('SSE connection error:', error);
			if (onError) {
				onError(error);
			}
		};

		return eventSource;
	}
}

// Task event type for SSE
export interface TaskEvent {
	event: 'init' | 'task_started' | 'task_progress' | 'task_completed' | 'task_cancelled' | 'heartbeat';
	data?: {
		active_tasks?: Record<string, ConversionTask>;
		processing_files?: string[];
		num_workers?: number;
		task_id?: string;
		filename?: string;
		status?: string;
		progress?: number;
		message?: string;
		error?: string | null;
	};
	count?: number;  // For heartbeat events
}

// Conversion task type
export interface ConversionTask {
	task_id: string;
	filename: string;
	status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
	progress: number;
	message: string;
	started_at: string | null;
	completed_at: string | null;
	error: string | null;
}

export const apiClient = new ApiClient();
export default apiClient;
