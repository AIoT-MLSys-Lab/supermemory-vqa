/**
 * Unit tests for bounding-box module
 */

import { describe, test, expect } from 'vitest';
import { BoundingBoxManager } from '$lib/utils/bounding-box';

describe('BoundingBoxManager', () => {
	describe('convertGeminiToPixel', () => {
		test('converts Gemini format to pixel format with 90-degree rotation', () => {
			// Gemini format: [y1, x1, y2, x2] normalized 0-1000
			// Pixel format: [x1, y1, x2, y2]
			// Applies 90-degree clockwise rotation: (x, y) -> (y, 1000 - x)
			const geminiBox = [100, 200, 500, 600]; // y1=100, x1=200, y2=500, x2=600
			const videoWidth = 1000;
			const videoHeight = 1000;

			const result = BoundingBoxManager.convertGeminiToPixel(geminiBox, videoWidth, videoHeight);

			// With rotation: x = y_norm, y = 1000 - x_norm
			// Expected: [y1*1, (1000-x2)*1, y2*1, (1000-x1)*1] = [100, 400, 500, 800]
			expect(result).toEqual([100, 400, 500, 800]);
		});

		test('scales coordinates to video dimensions', () => {
			const geminiBox = [500, 500, 1000, 1000]; // Center to bottom-right
			const videoWidth = 2000;
			const videoHeight = 2000;

			const result = BoundingBoxManager.convertGeminiToPixel(geminiBox, videoWidth, videoHeight);

			// Scale factor is 2 (2000/1000)
			// With rotation: [y1*2, (1000-x2)*2, y2*2, (1000-x1)*2] = [1000, 0, 2000, 1000]
			expect(result).toEqual([1000, 0, 2000, 1000]);
		});

		test('returns input for invalid box', () => {
			expect(BoundingBoxManager.convertGeminiToPixel(null, 1000, 1000)).toBe(null);
			expect(BoundingBoxManager.convertGeminiToPixel([1, 2, 3], 1000, 1000)).toEqual([1, 2, 3]);
		});
	});

	describe('convertPixelToGemini', () => {
		test('converts pixel format to Gemini format (inverse of rotation)', () => {
			// Pixel format: [x1, y1, x2, y2]
			// Gemini format: [y1, x1, y2, x2] normalized 0-1000
			// Inverse of rotation: y_norm = x, x_norm = 1000 - y
			const pixelBox = [100, 400, 500, 800]; // x1=100, y1=400, x2=500, y2=800
			const videoWidth = 1000;
			const videoHeight = 1000;

			const result = BoundingBoxManager.convertPixelToGemini(pixelBox, videoWidth, videoHeight);

			// Expected: [x1*1, 1000-y2*1, x2*1, 1000-y1*1] = [100, 200, 500, 600]
			expect(result).toEqual([100, 200, 500, 600]);
		});

		test('scales coordinates from video dimensions', () => {
			const pixelBox = [1000, 0, 2000, 1000];
			const videoWidth = 2000;
			const videoHeight = 2000;

			const result = BoundingBoxManager.convertPixelToGemini(pixelBox, videoWidth, videoHeight);

			// Scale factor is 0.5 (1000/2000)
			// With inverse rotation: [x1*0.5, 1000-y2*0.5, x2*0.5, 1000-y1*0.5] = [500, 500, 1000, 1000]
			expect(result).toEqual([500, 500, 1000, 1000]);
		});

		test('roundtrip conversion preserves values', () => {
			const originalGemini = [100, 200, 500, 600];
			const videoWidth = 1000;
			const videoHeight = 1000;

			const pixel = BoundingBoxManager.convertGeminiToPixel(
				originalGemini,
				videoWidth,
				videoHeight
			);
			const backToGemini = BoundingBoxManager.convertPixelToGemini(
				pixel as number[],
				videoWidth,
				videoHeight
			);

			expect(backToGemini).toEqual(originalGemini);
		});
	});

	describe('getHandleAt', () => {
		test('detects top-left corner handle', () => {
			const boxCoords = [100, 100, 300, 300]; // x1, y1, x2, y2
			expect(BoundingBoxManager.getHandleAt(100, 100, boxCoords)).toBe('nw');
		});

		test('detects top-right corner handle', () => {
			const boxCoords = [100, 100, 300, 300];
			expect(BoundingBoxManager.getHandleAt(300, 100, boxCoords)).toBe('ne');
		});

		test('detects bottom-left corner handle', () => {
			const boxCoords = [100, 100, 300, 300];
			expect(BoundingBoxManager.getHandleAt(100, 300, boxCoords)).toBe('sw');
		});

		test('detects bottom-right corner handle', () => {
			const boxCoords = [100, 100, 300, 300];
			expect(BoundingBoxManager.getHandleAt(300, 300, boxCoords)).toBe('se');
		});

		test('detects edge handles', () => {
			const boxCoords = [100, 100, 300, 300];
			expect(BoundingBoxManager.getHandleAt(200, 100, boxCoords)).toBe('n');
			expect(BoundingBoxManager.getHandleAt(200, 300, boxCoords)).toBe('s');
			expect(BoundingBoxManager.getHandleAt(100, 200, boxCoords)).toBe('w');
			expect(BoundingBoxManager.getHandleAt(300, 200, boxCoords)).toBe('e');
		});

		test('returns null when not on handle', () => {
			const boxCoords = [100, 100, 300, 300];
			expect(BoundingBoxManager.getHandleAt(200, 200, boxCoords)).toBe(null);
			expect(BoundingBoxManager.getHandleAt(50, 50, boxCoords)).toBe(null);
		});
	});

	describe('isInsideBox', () => {
		test('returns true for point inside box', () => {
			const boxCoords = [100, 100, 300, 300];
			expect(BoundingBoxManager.isInsideBox(200, 200, boxCoords)).toBe(true);
		});

		test('returns true for point on edge', () => {
			const boxCoords = [100, 100, 300, 300];
			expect(BoundingBoxManager.isInsideBox(100, 200, boxCoords)).toBe(true);
			expect(BoundingBoxManager.isInsideBox(300, 200, boxCoords)).toBe(true);
		});

		test('returns false for point outside box', () => {
			const boxCoords = [100, 100, 300, 300];
			expect(BoundingBoxManager.isInsideBox(50, 50, boxCoords)).toBe(false);
			expect(BoundingBoxManager.isInsideBox(400, 400, boxCoords)).toBe(false);
		});
	});

	describe('applyResize', () => {
		test('resizes from north handle', () => {
			const startCoords = [100, 100, 300, 300];
			const result = BoundingBoxManager.applyResize(startCoords, 'n', 0, -50);
			expect(result[1]).toBe(50); // y1 moved up
			expect(result[3]).toBe(300); // y2 unchanged
		});

		test('resizes from south handle', () => {
			const startCoords = [100, 100, 300, 300];
			const result = BoundingBoxManager.applyResize(startCoords, 's', 0, 50);
			expect(result[1]).toBe(100); // y1 unchanged
			expect(result[3]).toBe(350); // y2 moved down
		});

		test('resizes from east handle', () => {
			const startCoords = [100, 100, 300, 300];
			const result = BoundingBoxManager.applyResize(startCoords, 'e', 50, 0);
			expect(result[0]).toBe(100); // x1 unchanged
			expect(result[2]).toBe(350); // x2 moved right
		});

		test('resizes from west handle', () => {
			const startCoords = [100, 100, 300, 300];
			const result = BoundingBoxManager.applyResize(startCoords, 'w', -50, 0);
			expect(result[0]).toBe(50); // x1 moved left
			expect(result[2]).toBe(300); // x2 unchanged
		});

		test('resizes from corner handle', () => {
			const startCoords = [100, 100, 300, 300];
			const result = BoundingBoxManager.applyResize(startCoords, 'se', 50, 50);
			expect(result).toEqual([100, 100, 350, 350]);
		});

		test('enforces minimum size', () => {
			const startCoords = [100, 100, 120, 120]; // 20x20 box
			const result = BoundingBoxManager.applyResize(startCoords, 'w', 15, 0, 10);
			expect(result[2] - result[0]).toBeGreaterThanOrEqual(10);
		});
	});

	describe('clampToVideo', () => {
		test('clamps coordinates to video bounds', () => {
			const coords = [-50, -50, 1100, 1100];
			const result = BoundingBoxManager.clampToVideo(coords, 1000, 1000);
			expect(result).toEqual([0, 0, 1000, 1000]);
		});

		test('leaves valid coordinates unchanged', () => {
			const coords = [100, 100, 500, 500];
			const result = BoundingBoxManager.clampToVideo(coords, 1000, 1000);
			expect(result).toEqual([100, 100, 500, 500]);
		});
	});
});
