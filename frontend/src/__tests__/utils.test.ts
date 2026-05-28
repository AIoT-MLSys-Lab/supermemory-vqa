/**
 * Unit tests for utils module
 */

import { describe, test, expect } from 'vitest';
import {
	escapeHtml,
	parseTimestamp,
	formatTimestamp,
	isValidTimestamp,
	deepClone,
	getNestedProperty,
	isDefined,
	isNonEmptyString,
	isNonEmptyArray,
	MIN_BOX_SIZE,
	DEFAULT_VIDEO_WIDTH,
	DEFAULT_VIDEO_HEIGHT,
	GEMINI_NORM_MAX
} from '$lib/utils';

describe('utils', () => {
	describe('constants', () => {
		test('MIN_BOX_SIZE should be 10', () => {
			expect(MIN_BOX_SIZE).toBe(10);
		});

		test('DEFAULT_VIDEO_WIDTH should be 1408', () => {
			expect(DEFAULT_VIDEO_WIDTH).toBe(1408);
		});

		test('DEFAULT_VIDEO_HEIGHT should be 1408', () => {
			expect(DEFAULT_VIDEO_HEIGHT).toBe(1408);
		});

		test('GEMINI_NORM_MAX should be 1000', () => {
			expect(GEMINI_NORM_MAX).toBe(1000);
		});
	});

	describe('escapeHtml', () => {
		test('returns empty string for null', () => {
			expect(escapeHtml(null)).toBe('');
		});

		test('returns empty string for undefined', () => {
			expect(escapeHtml(undefined)).toBe('');
		});

		test('returns empty string for empty string', () => {
			expect(escapeHtml('')).toBe('');
		});

		test('escapes HTML special characters', () => {
			expect(escapeHtml('<script>alert("xss")</script>')).toBe(
				'&lt;script&gt;alert("xss")&lt;/script&gt;'
			);
		});

		test('escapes ampersand', () => {
			expect(escapeHtml('foo & bar')).toBe('foo &amp; bar');
		});

		test('preserves quotes in text content', () => {
			// Note: DOM-based escapeHtml doesn't escape quotes in text content
			// This is correct behavior - quotes only need escaping in attributes
			const result = escapeHtml('"test"');
			expect(result).toBe('"test"');
		});

		test('leaves safe text unchanged', () => {
			expect(escapeHtml('Hello World')).toBe('Hello World');
		});
	});

	describe('parseTimestamp', () => {
		test('parses valid MM:SS timestamp', () => {
			expect(parseTimestamp('01:30')).toBe(90);
		});

		test('parses single digit minutes', () => {
			expect(parseTimestamp('5:45')).toBe(345);
		});

		test('parses hour timestamps', () => {
			expect(parseTimestamp('1:02:45')).toBe(3765);
		});

		test('parses long minute timestamps', () => {
			expect(parseTimestamp('62:45')).toBe(3765);
		});

		test('returns 0 for null', () => {
			expect(parseTimestamp(null)).toBe(0);
		});

		test('returns 0 for undefined', () => {
			expect(parseTimestamp(undefined)).toBe(0);
		});

		test('returns 0 for invalid format', () => {
			expect(parseTimestamp('invalid')).toBe(0);
		});

		test('returns 0 for non-string', () => {
			expect(parseTimestamp(123 as unknown as string)).toBe(0);
		});

		test('handles 00:00', () => {
			expect(parseTimestamp('00:00')).toBe(0);
		});

		test('rejects loose hour formatting', () => {
			expect(parseTimestamp('1:2:03')).toBe(0);
		});
	});

	describe('formatTimestamp', () => {
		test('formats seconds to MM:SS', () => {
			expect(formatTimestamp(90)).toBe('1:30');
		});

		test('pads seconds with leading zero', () => {
			expect(formatTimestamp(65)).toBe('1:05');
		});

		test('handles zero', () => {
			expect(formatTimestamp(0)).toBe('0:00');
		});

		test('returns 00:00 for NaN', () => {
			expect(formatTimestamp(NaN)).toBe('00:00');
		});

		test('returns 00:00 for non-number', () => {
			expect(formatTimestamp('invalid' as unknown as number)).toBe('00:00');
		});

		test('formats hour timestamps', () => {
			expect(formatTimestamp(3765)).toBe('1:02:45');
		});
	});

	describe('isValidTimestamp', () => {
		test('returns true for valid MM:SS', () => {
			expect(isValidTimestamp('01:30')).toBe(true);
		});

		test('returns true for single digit minutes', () => {
			expect(isValidTimestamp('5:45')).toBe(true);
		});

		test('returns false for null', () => {
			expect(isValidTimestamp(null)).toBe(false);
		});

		test('returns false for invalid format', () => {
			expect(isValidTimestamp('invalid')).toBe(false);
		});

		test('returns true for H:MM:SS format', () => {
			expect(isValidTimestamp('01:30:00')).toBe(true);
		});

		test('returns false for loose H:M:SS format', () => {
			expect(isValidTimestamp('1:2:03')).toBe(false);
		});
	});

	describe('deepClone', () => {
		test('clones simple object', () => {
			const obj = { a: 1, b: 2 };
			const cloned = deepClone(obj);
			expect(cloned).toEqual(obj);
			expect(cloned).not.toBe(obj);
		});

		test('clones nested object', () => {
			const obj = { a: { b: { c: 1 } } };
			const cloned = deepClone(obj);
			expect(cloned).toEqual(obj);
			expect(cloned.a).not.toBe(obj.a);
		});

		test('clones array', () => {
			const arr = [1, 2, { a: 3 }];
			const cloned = deepClone(arr);
			expect(cloned).toEqual(arr);
			expect(cloned).not.toBe(arr);
		});

		test('returns null for null', () => {
			expect(deepClone(null)).toBe(null);
		});

		test('returns primitive for primitive', () => {
			expect(deepClone(5)).toBe(5);
			expect(deepClone('test')).toBe('test');
		});
	});

	describe('getNestedProperty', () => {
		test('gets shallow property', () => {
			expect(getNestedProperty({ a: 1 }, 'a')).toBe(1);
		});

		test('gets nested property', () => {
			expect(getNestedProperty({ a: { b: { c: 1 } } }, 'a.b.c')).toBe(1);
		});

		test('returns default for missing property', () => {
			expect(getNestedProperty({ a: 1 }, 'b', 'default')).toBe('default');
		});

		test('returns default for null object', () => {
			expect(getNestedProperty(null, 'a', 'default')).toBe('default');
		});

		test('returns undefined as default when not specified', () => {
			expect(getNestedProperty({ a: 1 }, 'b')).toBe(undefined);
		});
	});

	describe('isDefined', () => {
		test('returns false for null', () => {
			expect(isDefined(null)).toBe(false);
		});

		test('returns false for undefined', () => {
			expect(isDefined(undefined)).toBe(false);
		});

		test('returns true for 0', () => {
			expect(isDefined(0)).toBe(true);
		});

		test('returns true for empty string', () => {
			expect(isDefined('')).toBe(true);
		});

		test('returns true for false', () => {
			expect(isDefined(false)).toBe(true);
		});
	});

	describe('isNonEmptyString', () => {
		test('returns true for non-empty string', () => {
			expect(isNonEmptyString('hello')).toBe(true);
		});

		test('returns false for empty string', () => {
			expect(isNonEmptyString('')).toBe(false);
		});

		test('returns false for whitespace only', () => {
			expect(isNonEmptyString('   ')).toBe(false);
		});

		test('returns false for non-string', () => {
			expect(isNonEmptyString(123)).toBe(false);
		});
	});

	describe('isNonEmptyArray', () => {
		test('returns true for non-empty array', () => {
			expect(isNonEmptyArray([1, 2, 3])).toBe(true);
		});

		test('returns false for empty array', () => {
			expect(isNonEmptyArray([])).toBe(false);
		});

		test('returns false for non-array', () => {
			expect(isNonEmptyArray('not array')).toBe(false);
		});

		test('returns false for null', () => {
			expect(isNonEmptyArray(null)).toBe(false);
		});
	});
});
