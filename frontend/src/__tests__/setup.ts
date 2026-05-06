/// <reference types="vitest" />
/**
 * Test setup file for Vitest
 */

// Mock DOM for testing
if (typeof window !== 'undefined') {
	// Mock window.CSRF_TOKEN
	(window as unknown as Record<string, unknown>).CSRF_TOKEN = 'test-csrf-token';
	(window as unknown as Record<string, unknown>).GEMINI_NORM_MAX = 1000;
}
