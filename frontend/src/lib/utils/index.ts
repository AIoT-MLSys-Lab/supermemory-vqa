/**
 * Utility functions for the SuperMemory UI
 * @module utils
 */

import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

// Constants
export const MIN_BOX_SIZE = 10;
export const DEFAULT_VIDEO_WIDTH = 1408;
export const DEFAULT_VIDEO_HEIGHT = 1408;
export const GEMINI_NORM_MAX = 1000;

/**
 * Utility function for combining Tailwind CSS classes
 */
export function cn(...inputs: ClassValue[]): string {
	return twMerge(clsx(inputs));
}

/**
 * Escape HTML to prevent XSS attacks
 * @param text - Text to escape
 * @returns Escaped HTML string
 */
export function escapeHtml(text: string | null | undefined): string {
	if (!text) return '';
	if (typeof document !== 'undefined') {
		const div = document.createElement('div');
		div.textContent = text;
		return div.innerHTML;
	}
	// Server-side fallback
	return String(text)
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;')
		.replace(/"/g, '&quot;')
		.replace(/'/g, '&#39;');
}

/**
 * Unescape HTML entities to plain text
 * @param html - HTML string to unescape
 * @returns Unescaped text
 */
export function unescapeHtml(html: string | null | undefined): string {
	if (!html) return '';
	if (typeof document !== 'undefined') {
		const txt = document.createElement('textarea');
		txt.innerHTML = html;
		return txt.value;
	}
	// Server-side fallback
	return String(html)
		.replace(/&amp;/g, '&')
		.replace(/&lt;/g, '<')
		.replace(/&gt;/g, '>')
		.replace(/&quot;/g, '"')
		.replace(/&#39;/g, "'")
		.replace(/&#x27;/g, "'")
		.replace(/&#x2F;/g, '/');
}

/**
 * Parse a timestamp string (MM:SS) to total seconds
 * @param timestamp - Timestamp in MM:SS format
 * @returns Total seconds
 */
export function parseTimestamp(timestamp: string | null | undefined): number {
	if (!timestamp || typeof timestamp !== 'string') return 0;
	const parts = timestamp.split(':');
	if (parts.length !== 2) return 0;
	const [minutes, seconds] = parts.map(Number);
	if (isNaN(minutes) || isNaN(seconds)) return 0;
	return minutes * 60 + seconds;
}

/**
 * Format seconds to MM:SS timestamp
 * @param totalSeconds - Total seconds
 * @returns Formatted timestamp
 */
export function formatTimestamp(totalSeconds: number): string {
	if (typeof totalSeconds !== 'number' || isNaN(totalSeconds)) return '00:00';
	const minutes = Math.floor(totalSeconds / 60);
	const seconds = Math.floor(totalSeconds % 60);
	return `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

/**
 * Validate timestamp format (MM:SS)
 * @param timestamp - Timestamp to validate
 * @returns True if valid
 */
export function isValidTimestamp(timestamp: string | null | undefined): boolean {
	if (!timestamp || typeof timestamp !== 'string') return false;
	return /^\d{1,2}:\d{2}$/.test(timestamp);
}

/**
 * Deep clone an object
 * @param obj - Object to clone
 * @returns Cloned object
 */
export function deepClone<T>(obj: T): T {
	if (obj === null || typeof obj !== 'object') return obj;
	return JSON.parse(JSON.stringify(obj));
}

/**
 * Safely get a nested property from an object
 * @param obj - Object to search
 * @param path - Dot-separated path (e.g., 'location.boxes')
 * @param defaultValue - Default value if property not found
 * @returns Property value or default
 */
export function getNestedProperty<T>(
	obj: Record<string, unknown> | null | undefined,
	path: string,
	defaultValue: T | undefined = undefined
): T | undefined {
	if (!obj || typeof path !== 'string') return defaultValue;
	const keys = path.split('.');
	let current: unknown = obj;
	for (const key of keys) {
		if (
			current === null ||
			current === undefined ||
			!Object.prototype.hasOwnProperty.call(current, key)
		) {
			return defaultValue;
		}
		current = (current as Record<string, unknown>)[key];
	}
	return current as T;
}

/**
 * Check if a value is defined (not null or undefined)
 * @param value - Value to check
 * @returns True if defined
 */
export function isDefined<T>(value: T | null | undefined): value is T {
	return value !== null && value !== undefined;
}

/**
 * Check if value is a non-empty string
 * @param value - Value to check
 * @returns True if non-empty string
 */
export function isNonEmptyString(value: unknown): value is string {
	return typeof value === 'string' && value.trim().length > 0;
}

/**
 * Check if value is a non-empty array
 * @param value - Value to check
 * @returns True if non-empty array
 */
export function isNonEmptyArray<T>(value: unknown): value is T[] {
	return Array.isArray(value) && value.length > 0;
}

/**
 * Type helper to remove children from props
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type WithoutChildrenOrChild<T> = T extends { children?: any } ? Omit<T, 'children'> : T;

/**
 * Debounce a function call
 * @param func - Function to debounce
 * @param wait - Milliseconds to wait
 * @returns Debounced function
 */
export function debounce<T extends (...args: unknown[]) => unknown>(
	func: T,
	wait: number
): (...args: Parameters<T>) => void {
	let timeout: ReturnType<typeof setTimeout> | null = null;
	return function (...args: Parameters<T>) {
		if (timeout) clearTimeout(timeout);
		timeout = setTimeout(() => func(...args), wait);
	};
}

/**
 * Throttle a function call
 * @param func - Function to throttle
 * @param limit - Milliseconds to limit
 * @returns Throttled function
 */
export function throttle<T extends (...args: unknown[]) => unknown>(
	func: T,
	limit: number
): (...args: Parameters<T>) => void {
	let inThrottle = false;
	return function (...args: Parameters<T>) {
		if (!inThrottle) {
			func(...args);
			inThrottle = true;
			setTimeout(() => (inThrottle = false), limit);
		}
	};
}
