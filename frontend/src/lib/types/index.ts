/**
 * TypeScript type definitions for the SuperMemory UI
 */

export interface TimeSpan {
	start?: string;
	end?: string;
	video_id?: string;
}

export interface BoundingBox {
	box_2d: number[];
	timestamp?: string;
	description?: string;
	stream?: string; // Deprecated in favor of inferred status
	video_path?: string; // Absolute path to video file
}

// Alias for clarity
export type LocationBox = BoundingBox;

export interface Location {
	boxes?: LocationBox[];
	box_2d?: number[];
}

export interface HumanReview {
	reviewed?: boolean;
	status?: 'accepted' | 'rejected' | 'pending';
	comment?: string;
	reviewer?: string;
	timestamp?: string;
}

export type SkillType =
	| 'object_location_memory'
	| 'conversational_memory'
	| 'visual_recall'
	| 'timeline_reconstruction'
	| 'intent_recall'
	| 'in_context_retrieval'
	| 'unknown';

export interface Evidence {
	time_spans?: TimeSpan[];
	video_path?: string; // If undefined, implies current video
	reason?: string;
	room?: string;
	modalities?: string[];
	bounding_boxes?: BoundingBox[];
}

// Verification score from pipeline_v2 agentic verifier
export interface VerificationScore {
	factual_correctness_reasoning?: string;
	causal_answerability_reasoning?: string;
	question_naturalness_reasoning?: string;
	temporal_grounding_reasoning?: string;
	privacy_violation?: boolean;
	suggestions?: string[];
	suggested_chunks?: SuggestedChunk[];
	factual_correctness_score?: number;
	causal_answerability_score?: number;
	question_naturalness_score?: number;
	temporal_grounding_score?: number;
	is_correct?: boolean;
	/** @deprecated replaced by naturalness and temporal scores */
	objective_correctness_reasoning?: string;
	/** @deprecated replaced by naturalness and temporal scores */
	objective_correctness_score?: number;
}

export interface SuggestedChunk {
	relevance_reason?: string;
	video_id?: string;
	chunk_index?: number;
	start_time?: number;
	end_time?: number;
	relevance_score?: number;
}

// Full question/answer detail objects from pipeline_v2
export interface QuestionDetails {
	text?: string;
	question_reasoning?: string;
	room?: string;
	time_spans?: Array<{ start_time?: string; end_time?: string; video_id?: string }>;
	/** @deprecated Use time_spans instead */
	time_span?: { start_time?: string; end_time?: string };
	video_id?: string;
	modalities?: string[];
	is_answerable?: boolean;
	bounding_boxes?: Array<{
		label?: string;
		ymin?: number;
		xmin?: number;
		ymax?: number;
		xmax?: number;
		time_offset?: string;
	}>;
}

export interface AnswerChoice {
	choice_type: 'correct' | 'vague' | 'incorrect';
	text: string;
	explanation: string;
}

export interface AnswerDetails {
	text?: string;
	is_answerable?: boolean;
	answer_choices?: AnswerChoice[];
	evidence_list?: Array<{
		reason?: string;
		room?: string;
		time_span?: { start_time?: string; end_time?: string };
		time_spans?: Array<{ start_time?: string; end_time?: string; video_id?: string }>;
		video_id?: string;
		modalities?: string[];
		bounding_boxes?: Array<{
			label?: string;
			ymin?: number;
			xmin?: number;
			ymax?: number;
			xmax?: number;
			time_offset?: string;
		}>;
	}>;
}

export interface Annotation {
	skill?: SkillType;
	question?: string;
	answer?: string;
	question_time_spans?: TimeSpan[];
	/** @deprecated Use question_time_spans instead */
	question_time_span?: TimeSpan;
	// Deprecated: use answer_evidence instead
	time_span?: TimeSpan;
	// Deprecated: use answer_evidence instead
	answer_video_path?: string;
	room?: string;
	modalities?: string[];
	human_review?: HumanReview;
	location?: Location;
	video_filename?: string;
	answer_evidence?: Evidence[];
	// --- pipeline_v2 fields ---
	annotation_type?: 'verified' | 'rejected';
	verification_score?: VerificationScore;
	metadata_details?: Record<string, unknown>;
	question_details?: QuestionDetails;
	answer_details?: AnswerDetails;
	confidence?: number;
	confidence_reasoning?: string;
	balance_reasoning?: string;
	rejection_reason?: string;
	// --- new answer choice fields ---
	answer_choices?: AnswerChoice[];
	is_answerable?: boolean;
}

export interface Video {
	filename: string;
	path?: string;
	has_annotations?: boolean;
	annotations_count?: number;
	duration?: number;
	duration_formatted?: string;
	uploaded_at?: string;
	// VRS-related fields
	type?: 'video' | 'vrs';
	has_source_vrs?: boolean;
	source_vrs_filename?: string | null;
	is_processed?: boolean;
	size?: number;
	size_formatted?: string;
}

export interface AnnotationFile {
	filename: string;
	annotations: Annotation[];
	annotation_count?: number;
	video_filename?: string;
	metadata?: Record<string, unknown>;
	thinking?: string;
	raw_response?: string;
	full_raw_response?: string;
	created_at?: string;
	updated_at?: string;
}

export interface QAReviewItem {
	id: string;
	video_filename: string;
	annotation_filename: string;
	annotation_index: number;
	annotation: Annotation;
	source?: {
		annotation_type?: 'verified' | 'rejected' | 'legacy';
		video_id?: string;
		file_path?: string;
	};
}

export interface Model {
	id: string;
	name: string;
	description?: string;
}

export interface Prompt {
	id: string;
	name: string;
	description?: string;
	parameters?: PromptParameter[];
	input_parameters?: Record<string, PromptInputParameter>;
}

export interface PromptInputParameter {
	type: 'string' | 'integer' | 'float' | 'boolean' | 'select';
	description?: string;
	default?: string | number | boolean;
	options?: string[];
}

export interface PromptParameter {
	name: string;
	type: 'string' | 'number' | 'boolean' | 'select';
	label: string;
	default?: string | number | boolean;
	options?: string[];
	required?: boolean;
}

export interface ApiResponse<T> {
	success: boolean;
	data?: T;
	error?: string;
	message?: string;
}

export interface ModelsResponse {
	models: Model[];
	source: string;
	reason?: string;
}

export interface GenerateAnnotationsParams {
	video_filename: string;
	model_id: string;
	prompt_id: string;
	prompt_params?: Record<string, unknown>;
}

export interface BuiltPrompt {
	success: boolean;
	rendered_prompt?: string;
	prompt?: string;
	parameters?: Record<string, unknown>;
	error?: string;
}

// Caption types for Caption Review
export interface TranscriptLine {
	speaker: string | null;
	transcript: string;
}

export interface PersonDetail {
	person: string;
	description: string;
}

export interface CaptionDescription {
	activities: string;
	objects: string;
	environment: string;
	visible_text: string;
	audio_transcript: TranscriptLine[] | string;
	people: PersonDetail[] | string;
}

export interface Caption {
	text: string;
	start: string; // "MM:SS" format
	end: string;   // "MM:SS" format
	importance?: string; // "high", "medium", "low"
	importance_reasoning?: string;
	confidence?: string; // "very low", "low", "medium", "high", "very high"
	confidence_reasoning?: string;
	description?: CaptionDescription;
	optimal_sampling_rate?: string;
	optimal_sampling_rate_reasoning?: string;
	optimal_resolution?: string;
	optimal_resolution_reasoning?: string;
}

export interface CaptionFile {
	filename: string;
	caption_type: string; // e.g. "narration", "narrations", "description", "activity", etc.
	captions: Caption[];
	human_review?: HumanReview;
	metadata?: Record<string, unknown>;
	chunk_summaries?: string[];
	chunks?: any[];
}

export interface CaptionSearchMatch {
	key: string;
	mode: 'regex' | 'semantic';
	snippet_html?: string;
	semantic_preview?: string;
	full_text: string;
	score?: number;
}

export interface CaptionSearchResult {
	segment_uid: string;
	video_id: string;
	video_path?: string;
	start_time: string;
	end_time: string;
	score: number;
	matches: CaptionSearchMatch[];
}

export interface CaptionSearchData {
	results: CaptionSearchResult[];
	total: number;
	page: number;
	per_page: number;
	available_keys: string[];
}

export interface CaptionSearchResponse extends ApiResponse<CaptionSearchData> {}

// Export annotation data type system
export * from './annotation-data-types';
export * from './visualizer-registry';
