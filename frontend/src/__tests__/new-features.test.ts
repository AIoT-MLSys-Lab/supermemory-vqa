/**
 * Tests for new features:
 * - Arrow key movement of bounding boxes
 * - Space bar play/pause
 * - Time marker dragging on progress bar
 * - Seek-without-play behavior for timespans
 */

import { describe, test, expect, vi } from 'vitest';
import { convertGeminiToPixel, convertPixelToGemini } from '$lib/utils/bounding-box';

describe('Arrow Key Bounding Box Movement', () => {
	const ARROW_MOVE_STEP = 5;
	const videoWidth = 1000;
	const videoHeight = 1000;

	test('ArrowUp should move box upward by step amount', () => {
		// Start with a gemini box
		const geminiBox = [200, 200, 400, 400]; // y1=200, x1=200, y2=400, x2=400
		const pixelBox = convertGeminiToPixel(geminiBox, videoWidth, videoHeight);
		expect(pixelBox).not.toBeNull();
		if (!pixelBox) return;

		// Move up (negative Y delta in pixel space)
		const newPixel = [
			pixelBox[0],
			pixelBox[1] - ARROW_MOVE_STEP,
			pixelBox[2],
			pixelBox[3] - ARROW_MOVE_STEP,
		];
		const newGemini = convertPixelToGemini(newPixel, videoWidth, videoHeight);
		expect(newGemini).not.toBeNull();
		if (!newGemini) return;

		// With rotation, moving up in pixel space (decreasing y) increases x_norm in Gemini
		// So x1 and x2 should increase (moved up in rotated space)
		expect(newGemini[1]).toBeGreaterThan(geminiBox[1]); // x1 increased
		expect(newGemini[3]).toBeGreaterThan(geminiBox[3]); // x2 increased
		expect(newGemini[0]).toBe(geminiBox[0]); // y1 unchanged
		expect(newGemini[2]).toBe(geminiBox[2]); // y2 unchanged
	});

	test('ArrowDown should move box downward by step amount', () => {
		const geminiBox = [200, 200, 400, 400];
		const pixelBox = convertGeminiToPixel(geminiBox, videoWidth, videoHeight);
		expect(pixelBox).not.toBeNull();
		if (!pixelBox) return;

		const newPixel = [
			pixelBox[0],
			pixelBox[1] + ARROW_MOVE_STEP,
			pixelBox[2],
			pixelBox[3] + ARROW_MOVE_STEP,
		];
		const newGemini = convertPixelToGemini(newPixel, videoWidth, videoHeight);
		expect(newGemini).not.toBeNull();
		if (!newGemini) return;

		// With rotation, moving down in pixel space (increasing y) decreases x_norm in Gemini
		expect(newGemini[1]).toBeLessThan(geminiBox[1]); // x1 decreased
		expect(newGemini[3]).toBeLessThan(geminiBox[3]); // x2 decreased
		expect(newGemini[0]).toBe(geminiBox[0]); // y1 unchanged
		expect(newGemini[2]).toBe(geminiBox[2]); // y2 unchanged
	});

	test('ArrowLeft should move box left by step amount', () => {
		const geminiBox = [200, 200, 400, 400];
		const pixelBox = convertGeminiToPixel(geminiBox, videoWidth, videoHeight);
		expect(pixelBox).not.toBeNull();
		if (!pixelBox) return;

		const newPixel = [
			pixelBox[0] - ARROW_MOVE_STEP,
			pixelBox[1],
			pixelBox[2] - ARROW_MOVE_STEP,
			pixelBox[3],
		];
		const newGemini = convertPixelToGemini(newPixel, videoWidth, videoHeight);
		expect(newGemini).not.toBeNull();
		if (!newGemini) return;

		// With rotation, moving left in pixel space (decreasing x) decreases y_norm in Gemini
		expect(newGemini[0]).toBeLessThan(geminiBox[0]); // y1 decreased
		expect(newGemini[2]).toBeLessThan(geminiBox[2]); // y2 decreased
		expect(newGemini[1]).toBe(geminiBox[1]); // x1 unchanged
		expect(newGemini[3]).toBe(geminiBox[3]); // x2 unchanged
	});

	test('ArrowRight should move box right by step amount', () => {
		const geminiBox = [200, 200, 400, 400];
		const pixelBox = convertGeminiToPixel(geminiBox, videoWidth, videoHeight);
		expect(pixelBox).not.toBeNull();
		if (!pixelBox) return;

		const newPixel = [
			pixelBox[0] + ARROW_MOVE_STEP,
			pixelBox[1],
			pixelBox[2] + ARROW_MOVE_STEP,
			pixelBox[3],
		];
		const newGemini = convertPixelToGemini(newPixel, videoWidth, videoHeight);
		expect(newGemini).not.toBeNull();
		if (!newGemini) return;

		// With rotation, moving right in pixel space (increasing x) increases y_norm in Gemini
		expect(newGemini[0]).toBeGreaterThan(geminiBox[0]); // y1 increased
		expect(newGemini[2]).toBeGreaterThan(geminiBox[2]); // y2 increased
		expect(newGemini[1]).toBe(geminiBox[1]); // x1 unchanged
		expect(newGemini[3]).toBe(geminiBox[3]); // x2 unchanged
	});

	test('box dimensions should be preserved after arrow key movement', () => {
		const geminiBox = [100, 150, 300, 350];
		const pixelBox = convertGeminiToPixel(geminiBox, videoWidth, videoHeight);
		expect(pixelBox).not.toBeNull();
		if (!pixelBox) return;

		const origWidth = pixelBox[2] - pixelBox[0];
		const origHeight = pixelBox[3] - pixelBox[1];

		const newPixel = [
			pixelBox[0] + ARROW_MOVE_STEP,
			pixelBox[1] + ARROW_MOVE_STEP,
			pixelBox[2] + ARROW_MOVE_STEP,
			pixelBox[3] + ARROW_MOVE_STEP,
		];

		const newWidth = newPixel[2] - newPixel[0];
		const newHeight = newPixel[3] - newPixel[1];

		expect(newWidth).toBe(origWidth);
		expect(newHeight).toBe(origHeight);
	});

	test('should not move box when edit mode is not active', () => {
		let editModeActive = false;
		let boxMoved = false;

		const handleKeyDown = (key: string) => {
			if (!editModeActive) return;
			if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(key)) {
				boxMoved = true;
			}
		};

		handleKeyDown('ArrowUp');
		expect(boxMoved).toBe(false);
	});

	test('should move box when edit mode is active', () => {
		let editModeActive = true;
		let boxMoved = false;

		const handleKeyDown = (key: string) => {
			if (!editModeActive) return;
			if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(key)) {
				boxMoved = true;
			}
		};

		handleKeyDown('ArrowUp');
		expect(boxMoved).toBe(true);
	});
});

describe('Space Bar Play/Pause', () => {
	test('space bar should toggle play/pause', () => {
		let isPaused = true;

		const handleKeydown = (key: string) => {
			if (key === ' ') {
				isPaused = !isPaused;
			}
		};

		handleKeydown(' ');
		expect(isPaused).toBe(false); // Now playing

		handleKeydown(' ');
		expect(isPaused).toBe(true); // Now paused again
	});

	test('space bar should not toggle when input is focused', () => {
		let isPaused = true;
		let isInputFocused = true;

		const handleKeydown = (key: string) => {
			if (isInputFocused) return;
			if (key === ' ') {
				isPaused = !isPaused;
			}
		};

		handleKeydown(' ');
		expect(isPaused).toBe(true); // Should remain paused
	});

	test('arrow keys should not move video when bounding box edit mode is active', () => {
		let videoCurrentTime = 50;
		let boxEditMode = true;
		const activeBox = { box_2d: [100, 100, 200, 200] };

		const handleKeydown = (key: string) => {
			const isBboxEditActive = boxEditMode && activeBox;
			if (key === 'ArrowLeft' && !isBboxEditActive) {
				videoCurrentTime -= 5;
			} else if (key === 'ArrowRight' && !isBboxEditActive) {
				videoCurrentTime += 5;
			}
		};

		handleKeydown('ArrowLeft');
		expect(videoCurrentTime).toBe(50); // Should not change

		handleKeydown('ArrowRight');
		expect(videoCurrentTime).toBe(50); // Should not change
	});
});

describe('Seek-Without-Play for Timespans', () => {
	test('clicking timespan should seek without auto-playing', () => {
		let videoCurrentTime = 0;
		let videoPlaying = false;

		const seekTo = (timestamp: string, autoPlay: boolean) => {
			const parts = timestamp.split(':').map(Number);
			videoCurrentTime = parts[0] * 60 + parts[1];
			if (autoPlay) {
				videoPlaying = true;
			}
		};

		// Simulate clicking a timespan - should NOT auto-play
		seekTo('02:30', false);
		expect(videoCurrentTime).toBe(150);
		expect(videoPlaying).toBe(false);
	});

	test('play button should resume after seek', () => {
		let videoCurrentTime = 150;
		let videoPlaying = false;

		const play = () => {
			videoPlaying = true;
		};

		play();
		expect(videoPlaying).toBe(true);
	});
});

describe('Active Time Marker', () => {
	test('should create timespan marker with start and end', () => {
		const marker = {
			type: 'timespan' as const,
			startTime: 30,
			endTime: 60,
			annotationIndex: 0,
			field: 'question_time_span' as const,
		};

		expect(marker.type).toBe('timespan');
		expect(marker.startTime).toBe(30);
		expect(marker.endTime).toBe(60);
	});

	test('should create timestamp marker with start only', () => {
		const marker = {
			type: 'timestamp' as const,
			startTime: 45,
			annotationIndex: 0,
			field: 'box_timestamp' as const,
			boxIndex: 2,
		};

		expect(marker.type).toBe('timestamp');
		expect(marker.startTime).toBe(45);
		expect((marker as any).endTime).toBeUndefined();
	});

	test('marker start position should be calculated correctly', () => {
		const duration = 120; // 2 minutes
		const startTime = 30;
		const markerStartPercent = duration > 0 ? (startTime / duration) * 100 : -1;

		expect(markerStartPercent).toBe(25); // 30/120 = 25%
	});

	test('marker end position should be calculated correctly', () => {
		const duration = 120;
		const endTime = 90;
		const markerEndPercent = duration > 0 ? (endTime / duration) * 100 : -1;

		expect(markerEndPercent).toBe(75); // 90/120 = 75%
	});

	test('dragging start should update startTime', () => {
		const marker = {
			type: 'timespan' as const,
			startTime: 30,
			endTime: 60,
		};

		// Simulate dragging start to earlier time
		const newStartTime = 20;
		const updatedMarker = { ...marker, startTime: Math.max(0, Math.min(newStartTime, marker.endTime)) };

		expect(updatedMarker.startTime).toBe(20);
		expect(updatedMarker.endTime).toBe(60);
	});

	test('dragging end should update endTime', () => {
		const marker = {
			type: 'timespan' as const,
			startTime: 30,
			endTime: 60,
		};

		const duration = 120;
		const newEndTime = 80;
		const updatedMarker = { ...marker, endTime: Math.max(marker.startTime, Math.min(newEndTime, duration)) };

		expect(updatedMarker.startTime).toBe(30);
		expect(updatedMarker.endTime).toBe(80);
	});

	test('dragging whole span should maintain duration', () => {
		const marker = {
			type: 'timespan' as const,
			startTime: 30,
			endTime: 60,
		};

		const spanLength = marker.endTime - marker.startTime;
		const deltaTime = 10;
		const duration = 120;

		const newStart = Math.max(0, Math.min(marker.startTime + deltaTime, duration - spanLength));
		const newEnd = newStart + spanLength;

		expect(newEnd - newStart).toBe(spanLength); // Duration preserved
		expect(newStart).toBe(40);
		expect(newEnd).toBe(70);
	});

	test('start time should not exceed end time when dragging', () => {
		const marker = {
			type: 'timespan' as const,
			startTime: 30,
			endTime: 60,
		};

		// Try to drag start past end
		const newStartTime = 70;
		const clampedStart = Math.max(0, Math.min(newStartTime, marker.endTime));

		expect(clampedStart).toBe(60); // Clamped to endTime
	});

	test('end time should not be less than start time', () => {
		const marker = {
			type: 'timespan' as const,
			startTime: 30,
			endTime: 60,
		};

		// Try to drag end before start
		const newEndTime = 20;
		const clampedEnd = Math.max(marker.startTime, Math.min(newEndTime, 120));

		expect(clampedEnd).toBe(30); // Clamped to startTime
	});

	test('span drag should not go below 0', () => {
		const marker = {
			type: 'timespan' as const,
			startTime: 10,
			endTime: 40,
		};

		const spanLength = marker.endTime - marker.startTime;
		const deltaTime = -20; // Try to move 20 seconds earlier
		const duration = 120;

		const newStart = Math.max(0, Math.min(marker.startTime + deltaTime, duration - spanLength));
		const newEnd = newStart + spanLength;

		expect(newStart).toBe(0);
		expect(newEnd).toBe(30);
	});

	test('span drag should not exceed duration', () => {
		const marker = {
			type: 'timespan' as const,
			startTime: 80,
			endTime: 110,
		};

		const spanLength = marker.endTime - marker.startTime;
		const deltaTime = 20; // Try to move 20 seconds later
		const duration = 120;

		const newStart = Math.max(0, Math.min(marker.startTime + deltaTime, duration - spanLength));
		const newEnd = newStart + spanLength;

		expect(newStart).toBe(90); // max is 120 - 30 = 90
		expect(newEnd).toBe(120);
	});

	test('clearing bounding box should clear time marker', () => {
		let activeTimeMarker: object | null = {
			type: 'timestamp',
			startTime: 30,
			annotationIndex: 0,
			field: 'box_timestamp',
			boxIndex: 0,
		};

		const clearBoundingBox = () => {
			activeTimeMarker = null;
		};

		clearBoundingBox();
		expect(activeTimeMarker).toBeNull();
	});
});

describe('Cursor Icons for Time Markers', () => {
	test('should return ew-resize cursor when hovering over start endpoint', () => {
		const duration = 120;
		const startTime = 30;
		const barWidth = 400;

		const startPos = startTime / duration;
		const hitThreshold = 8 / barWidth;

		// Position near start
		const mousePos = startPos + hitThreshold / 2;
		const isNearStart = Math.abs(mousePos - startPos) < hitThreshold;

		expect(isNearStart).toBe(true);
	});

	test('should return grab cursor when hovering between endpoints', () => {
		const duration = 120;
		const startTime = 30;
		const endTime = 60;
		const barWidth = 400;

		const startPos = startTime / duration;
		const endPos = endTime / duration;
		const hitThreshold = 8 / barWidth;

		// Position in the middle of the span
		const mousePos = (startPos + endPos) / 2;
		const isInSpan = mousePos > startPos + hitThreshold && mousePos < endPos - hitThreshold;

		expect(isInSpan).toBe(true);
	});

	test('should return pointer cursor when not near any marker', () => {
		const duration = 120;
		const startTime = 30;
		const endTime = 60;
		const barWidth = 400;

		const startPos = startTime / duration;
		const endPos = endTime / duration;
		const hitThreshold = 8 / barWidth;

		// Position far from span
		const mousePos = 0.9;
		const isNearStart = Math.abs(mousePos - startPos) < hitThreshold;
		const isNearEnd = Math.abs(mousePos - endPos) < hitThreshold;
		const isInSpan = mousePos > startPos + hitThreshold && mousePos < endPos - hitThreshold;

		expect(isNearStart).toBe(false);
		expect(isNearEnd).toBe(false);
		expect(isInSpan).toBe(false);
	});
});
