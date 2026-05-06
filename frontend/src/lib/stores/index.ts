/**
 * Svelte stores for application state management
 */

import { writable, derived, get } from 'svelte/store';
import type { Video, Annotation, Model, Prompt, HumanReview, CaptionFile } from '$lib/types';
import { deepClone } from '$lib/utils';

// Video state
export const videos = writable<Video[]>([]);
export const currentVideo = writable<Video | null>(null);
export const videoLoading = writable<boolean>(false);

// Video folder state - persisted in sessionStorage
function createFolderPathStore() {
	const key = 'videoFolderPath';

	// Get initial value from sessionStorage if available
	let initialValue = '';
	if (typeof window !== 'undefined' && window.sessionStorage) {
		const stored = sessionStorage.getItem(key);
		if (stored) {
			initialValue = stored;
		}
	}

	const { subscribe, set, update } = writable<string>(initialValue);

	return {
		subscribe,
		set: (value: string) => {
			// Save to sessionStorage whenever the value changes
			if (typeof window !== 'undefined' && window.sessionStorage) {
				if (value) {
					sessionStorage.setItem(key, value);
				} else {
					sessionStorage.removeItem(key);
				}
			}
			set(value);
		},
		update,
		clear: () => {
			if (typeof window !== 'undefined' && window.sessionStorage) {
				sessionStorage.removeItem(key);
			}
			set('');
		}
	};
}

export const folderPath = createFolderPathStore();

// Annotation state
export const annotations = writable<Annotation[]>([]);
export const originalAnnotations = writable<Annotation[]>([]);
export const currentAnnotationFile = writable<string | null>(null);
export const annotationsLoading = writable<boolean>(false);

// Model and prompt state
export const models = writable<Model[]>([]);
export const prompts = writable<Prompt[]>([]);
export const selectedModel = writable<string>('');
export const selectedPrompt = writable<string>('');
export const promptParameters = writable<Record<string, unknown>>({});

// UI state
export const playerSectionActive = writable<boolean>(false);
export const editingAnnotationIndex = writable<number | null>(null);
export const modalOpen = writable<string | null>(null);
export const alertMessage = writable<{ type: 'success' | 'error' | 'info'; message: string } | null>(null);

// Generate annotations status
export const generateStatus = writable<{ loading: boolean; message: string }>({
	loading: false,
	message: ''
});

// Derived stores
export const hasAnnotations = derived(annotations, ($annotations) => $annotations.length > 0);

export const pendingReviewCount = derived(annotations, ($annotations) => {
	return $annotations.filter(
		(ann) => !ann.human_review || ann.human_review.status === 'pending' || !ann.human_review.reviewed
	).length;
});

export const acceptedCount = derived(annotations, ($annotations) => {
	return $annotations.filter(
		(ann) => ann.human_review?.status === 'accepted' || ann.human_review?.reviewed
	).length;
});

export const rejectedCount = derived(annotations, ($annotations) => {
	return $annotations.filter((ann) => ann.human_review?.status === 'rejected').length;
});

// Actions
export function setAnnotations(newAnnotations: Annotation[]): void {
	const cloned = deepClone(newAnnotations);
	annotations.set(cloned);
	originalAnnotations.set(deepClone(cloned));
}

export function updateAnnotation(index: number, annotation: Annotation): void {
	annotations.update((anns) => {
		if (index >= 0 && index < anns.length) {
			const newAnns = [...anns];
			newAnns[index] = annotation;
			return newAnns;
		}
		return anns;
	});
	originalAnnotations.update((anns) => {
		if (index >= 0 && index < anns.length) {
			const newAnns = [...anns];
			newAnns[index] = deepClone(annotation);
			return newAnns;
		}
		return anns;
	});
}

export function restoreAnnotation(index: number): void {
	const originals = get(originalAnnotations);
	if (index >= 0 && index < originals.length) {
		annotations.update((anns) => {
			const newAnns = [...anns];
			newAnns[index] = deepClone(originals[index]);
			return newAnns;
		});
	}
}

export function deleteAnnotation(index: number): void {
	annotations.update((anns) => {
		const newAnns = [...anns];
		newAnns.splice(index, 1);
		return newAnns;
	});
	originalAnnotations.update((anns) => {
		const newAnns = [...anns];
		newAnns.splice(index, 1);
		return newAnns;
	});
}

export function addAnnotation(annotation: Annotation): void {
	annotations.update((anns) => [...anns, annotation]);
	originalAnnotations.update((anns) => [...anns, deepClone(annotation)]);
}

export function clearAnnotationState(): void {
	currentAnnotationFile.set(null);
	annotations.set([]);
	originalAnnotations.set([]);
}

export function showAlert(type: 'success' | 'error' | 'info', message: string, duration = 5000): void {
	alertMessage.set({ type, message });
	if (duration > 0) {
		setTimeout(() => {
			alertMessage.set(null);
		}, duration);
	}
}

export function getReviewStatus(humanReview: HumanReview | undefined): 'accepted' | 'rejected' | 'pending' {
	if (!humanReview) return 'pending';
	if (humanReview.status) return humanReview.status;
	return humanReview.reviewed ? 'accepted' : 'pending';
}

// Caption state
export const captionFiles = writable<CaptionFile[]>([]);
export const captionFilesLoading = writable<boolean>(false);

export function setCaptionFiles(files: CaptionFile[]): void {
	captionFiles.set(deepClone(files));
}

export function updateCaptionFile(index: number, file: CaptionFile): void {
	captionFiles.update((files) => {
		if (index >= 0 && index < files.length) {
			const newFiles = [...files];
			newFiles[index] = deepClone(file);
			return newFiles;
		}
		return files;
	});
}

export function clearCaptionState(): void {
	captionFiles.set([]);
}
