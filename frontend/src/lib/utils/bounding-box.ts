/**
 * Bounding box handling for video annotations
 * @module bounding-box
 */

import { GEMINI_NORM_MAX, MIN_BOX_SIZE } from '$lib/utils';

export interface EditModeState {
	active: boolean;
	annotationIndex: number;
	boxIndex: number;
	currentBox: number[] | null;
	dragging: boolean;
	resizing: boolean;
	resizeHandle: string | null;
	startX: number;
	startY: number;
	originalBox: number[] | null;
	originalAnnotation: unknown | null;
	startBoxCoords: number[] | null;
	tempBoxCoords: number[] | null;
}

export interface DrawModeState {
	active: boolean;
	annotationIndex: number;
	startX: number;
	startY: number;
}

export type ResizeHandle = 'nw' | 'ne' | 'sw' | 'se' | 'n' | 's' | 'e' | 'w';

/**
 * Bounding Box Manager
 * Handles drawing, editing, and coordinate conversion for bounding boxes
 */
export const BoundingBoxManager = {
	// Edit mode state
	editMode: {
		active: false,
		annotationIndex: -1,
		boxIndex: -1,
		currentBox: null,
		dragging: false,
		resizing: false,
		resizeHandle: null,
		startX: 0,
		startY: 0,
		originalBox: null,
		originalAnnotation: null,
		startBoxCoords: null,
		tempBoxCoords: null
	} as EditModeState,

	// Draw mode state for creating new boxes
	drawMode: {
		active: false,
		annotationIndex: -1,
		startX: 0,
		startY: 0
	} as DrawModeState,

	/**
	 * Convert Gemini format [y1, x1, y2, x2] normalized 0-1000 to pixel [x1, y1, x2, y2]
	 * @param box2d - Box in Gemini format
	 * @param videoWidth - Video width in pixels
	 * @param videoHeight - Video height in pixels
	 * @returns Box in pixel format [x1, y1, x2, y2]
	 */
	convertGeminiToPixel(
		box2d: number[] | null | undefined,
		videoWidth: number,
		videoHeight: number
	): number[] | null | undefined {
		if (!box2d || box2d.length !== 4) return box2d;

		const [y1_norm, x1_norm, y2_norm, x2_norm] = box2d;
		const scaleX = videoWidth / GEMINI_NORM_MAX;
		const scaleY = videoHeight / GEMINI_NORM_MAX;

		// Apply 90-degree clockwise rotation: (x, y) -> (y, 1000 - x)
		// Model [ymin, xmin, ymax, xmax] -> Pixel [x1, y1, x2, y2]
		// New x = y_norm, New y = 1000 - x_norm
		return [
			y1_norm * scaleX,
			(GEMINI_NORM_MAX - x2_norm) * scaleY,
			y2_norm * scaleX,
			(GEMINI_NORM_MAX - x1_norm) * scaleY
		];
	},

	/**
	 * Convert pixel format [x1, y1, x2, y2] to Gemini format [y1, x1, y2, x2] normalized 0-1000
	 * @param box2d - Box in pixel format
	 * @param videoWidth - Video width in pixels
	 * @param videoHeight - Video height in pixels
	 * @returns Box in Gemini format
	 */
	convertPixelToGemini(
		box2d: number[] | null | undefined,
		videoWidth: number,
		videoHeight: number
	): number[] | null | undefined {
		if (!box2d || box2d.length !== 4) return box2d;

		const [x1, y1, x2, y2] = box2d;
		const scaleX = GEMINI_NORM_MAX / videoWidth;
		const scaleY = GEMINI_NORM_MAX / videoHeight;

		// Inverse of 90-degree clockwise rotation
		// Pixel [x1, y1, x2, y2] -> Model [ymin, xmin, ymax, xmax]
		// y_norm = x_pixel, x_norm = 1000 - y_pixel
		return [
			Math.round(x1 * scaleX),
			Math.round(GEMINI_NORM_MAX - y2 * scaleY),
			Math.round(x2 * scaleX),
			Math.round(GEMINI_NORM_MAX - y1 * scaleY)
		];
	},

	/**
	 * Draw a bounding box on canvas
	 * @param canvas - Canvas element
	 * @param video - Video element
	 * @param box2d - Box coordinates in Gemini format
	 * @param label - Label text
	 */
	drawBox(
		canvas: HTMLCanvasElement | null,
		video: HTMLVideoElement | null,
		box2d: number[] | null | undefined,
		label: string
	): void {
		if (!canvas || !video || !box2d || box2d.length !== 4) {
			// Silently return for invalid parameters in production
			return;
		}

		// Resize canvas to match video
		if (canvas.width !== video.offsetWidth || canvas.height !== video.offsetHeight) {
			canvas.width = video.offsetWidth;
			canvas.height = video.offsetHeight;
		}

		const ctx = canvas.getContext('2d');
		if (!ctx) return;

		ctx.clearRect(0, 0, canvas.width, canvas.height);

		const videoWidth = video.videoWidth || 1;
		const videoHeight = video.videoHeight || 1;

		// Convert from Gemini format to pixel coordinates
		const convertedBox = this.convertGeminiToPixel(box2d, videoWidth, videoHeight);
		if (!convertedBox) return;

		// Scale to canvas display size
		const scaleX = canvas.width / videoWidth;
		const scaleY = canvas.height / videoHeight;

		const [x1, y1, x2, y2] = convertedBox;
		const x = x1 * scaleX;
		const y = y1 * scaleY;
		const width = (x2 - x1) * scaleX;
		const height = (y2 - y1) * scaleY;

		// Draw box
		ctx.strokeStyle = '#ff4444';
		ctx.lineWidth = 3;
		ctx.strokeRect(x, y, width, height);

		// Draw label
		ctx.fillStyle = '#ff4444';
		ctx.font = 'bold 12px Arial';
		const labelPadding = 8;
		const labelHeight = 20;
		const labelWidth = ctx.measureText(label).width + labelPadding * 2;
		ctx.fillRect(x, Math.max(0, y - labelHeight), labelWidth, labelHeight);

		ctx.fillStyle = 'white';
		ctx.fillText(label, x + labelPadding, Math.max(labelHeight - 6, y - 6));
	},

	/**
	 * Draw editable box with resize handles
	 * @param canvas - Canvas element
	 * @param video - Video element
	 * @param box2d - Box in pixel format [x1, y1, x2, y2]
	 * @param label - Label text
	 */
	drawEditableBox(
		canvas: HTMLCanvasElement | null,
		video: HTMLVideoElement | null,
		box2d: number[] | null | undefined,
		label: string
	): void {
		if (!canvas || !video || !box2d || box2d.length !== 4) return;

		const ctx = canvas.getContext('2d');
		if (!ctx) return;

		ctx.clearRect(0, 0, canvas.width, canvas.height);

		const videoWidth = video.videoWidth || 1;
		const videoHeight = video.videoHeight || 1;
		const scaleX = canvas.width / videoWidth;
		const scaleY = canvas.height / videoHeight;

		const [x1, y1, x2, y2] = box2d;
		const x = x1 * scaleX;
		const y = y1 * scaleY;
		const width = (x2 - x1) * scaleX;
		const height = (y2 - y1) * scaleY;

		// Draw dashed selection box
		ctx.strokeStyle = '#ffaa00';
		ctx.lineWidth = 3;
		ctx.setLineDash([5, 5]);
		ctx.strokeRect(x, y, width, height);
		ctx.setLineDash([]);

		// Draw resize handles
		const handleSize = 8;
		const handles = [
			{ x: x, y: y, type: 'nw' },
			{ x: x + width, y: y, type: 'ne' },
			{ x: x, y: y + height, type: 'sw' },
			{ x: x + width, y: y + height, type: 'se' },
			{ x: x + width / 2, y: y, type: 'n' },
			{ x: x + width / 2, y: y + height, type: 's' },
			{ x: x, y: y + height / 2, type: 'w' },
			{ x: x + width, y: y + height / 2, type: 'e' }
		];

		handles.forEach((handle) => {
			ctx.fillStyle = '#ff4444';
			ctx.strokeStyle = 'white';
			ctx.lineWidth = 2;
			ctx.beginPath();
			ctx.arc(handle.x, handle.y, handleSize / 2, 0, Math.PI * 2);
			ctx.fill();
			ctx.stroke();
		});

		// Draw label
		ctx.fillStyle = '#ffaa00';
		ctx.font = 'bold 12px Arial';
		const labelPadding = 8;
		const labelHeight = 20;
		const labelWidth = ctx.measureText(label).width + labelPadding * 2;
		ctx.fillRect(x, Math.max(0, y - labelHeight), labelWidth, labelHeight);

		ctx.fillStyle = 'white';
		ctx.fillText(label, x + labelPadding, Math.max(labelHeight - 6, y - 6));
	},

	/**
	 * Clear the canvas
	 * @param canvas - Canvas element
	 */
	clearCanvas(canvas: HTMLCanvasElement | null): void {
		if (canvas) {
			const ctx = canvas.getContext('2d');
			if (ctx) {
				ctx.clearRect(0, 0, canvas.width, canvas.height);
			}
		}
	},

	/**
	 * Get resize handle at position
	 * @param x - Mouse X position
	 * @param y - Mouse Y position
	 * @param boxCoords - Box coordinates [x1, y1, x2, y2] in canvas space
	 * @param handleSize - Handle size
	 * @returns Handle type or null
	 */
	getHandleAt(
		x: number,
		y: number,
		boxCoords: number[],
		handleSize = 8
	): ResizeHandle | null {
		const [x1, y1, x2, y2] = boxCoords;
		const width = x2 - x1;
		const height = y2 - y1;

		const handles: Array<{ x: number; y: number; type: ResizeHandle }> = [
			{ x: x1, y: y1, type: 'nw' },
			{ x: x2, y: y1, type: 'ne' },
			{ x: x1, y: y2, type: 'sw' },
			{ x: x2, y: y2, type: 'se' },
			{ x: x1 + width / 2, y: y1, type: 'n' },
			{ x: x1 + width / 2, y: y2, type: 's' },
			{ x: x1, y: y1 + height / 2, type: 'w' },
			{ x: x2, y: y1 + height / 2, type: 'e' }
		];

		for (const handle of handles) {
			if (Math.abs(x - handle.x) < handleSize && Math.abs(y - handle.y) < handleSize) {
				return handle.type;
			}
		}

		return null;
	},

	/**
	 * Check if point is inside box
	 * @param x - Mouse X position
	 * @param y - Mouse Y position
	 * @param boxCoords - Box coordinates [x1, y1, x2, y2]
	 * @returns True if inside box
	 */
	isInsideBox(x: number, y: number, boxCoords: number[]): boolean {
		const [x1, y1, x2, y2] = boxCoords;
		return x >= x1 && x <= x2 && y >= y1 && y <= y2;
	},

	/**
	 * Apply resize delta to box coordinates
	 * @param startCoords - Starting box coordinates
	 * @param handle - Resize handle type
	 * @param dx - Delta X
	 * @param dy - Delta Y
	 * @param minSize - Minimum box size
	 * @returns New box coordinates
	 */
	applyResize(
		startCoords: number[],
		handle: string,
		dx: number,
		dy: number,
		minSize = MIN_BOX_SIZE
	): number[] {
		let [x1, y1, x2, y2] = startCoords;

		if (handle.includes('n')) y1 += dy;
		if (handle.includes('s')) y2 += dy;
		if (handle.includes('w')) x1 += dx;
		if (handle.includes('e')) x2 += dx;

		// Ensure minimum size
		if (x2 - x1 < minSize) {
			if (handle.includes('w')) x1 = x2 - minSize;
			else x2 = x1 + minSize;
		}
		if (y2 - y1 < minSize) {
			if (handle.includes('n')) y1 = y2 - minSize;
			else y2 = y1 + minSize;
		}

		return [x1, y1, x2, y2];
	},

	/**
	 * Clamp box coordinates to video bounds
	 * @param coords - Box coordinates
	 * @param maxWidth - Maximum width
	 * @param maxHeight - Maximum height
	 * @returns Clamped coordinates
	 */
	clampToVideo(coords: number[], maxWidth: number, maxHeight: number): number[] {
		let [x1, y1, x2, y2] = coords;
		x1 = Math.max(0, Math.min(maxWidth, x1));
		y1 = Math.max(0, Math.min(maxHeight, y1));
		x2 = Math.max(0, Math.min(maxWidth, x2));
		y2 = Math.max(0, Math.min(maxHeight, y2));
		return [x1, y1, x2, y2];
	}
};

export default BoundingBoxManager;

// Standalone function exports for convenience
export function convertGeminiToPixel(
	box2d: number[] | null | undefined,
	videoWidth: number,
	videoHeight: number
): number[] | null {
	if (!box2d || box2d.length !== 4) return null;

	const [y1_norm, x1_norm, y2_norm, x2_norm] = box2d;
	const scaleX = videoWidth / GEMINI_NORM_MAX;
	const scaleY = videoHeight / GEMINI_NORM_MAX;

	return [
		y1_norm * scaleX,
		(GEMINI_NORM_MAX - x2_norm) * scaleY,
		y2_norm * scaleX,
		(GEMINI_NORM_MAX - x1_norm) * scaleY
	];
}

export function convertPixelToGemini(
	box2d: number[] | null | undefined,
	videoWidth: number,
	videoHeight: number
): number[] | null {
	if (!box2d || box2d.length !== 4) return null;

	const [x1, y1, x2, y2] = box2d;
	const scaleX = GEMINI_NORM_MAX / videoWidth;
	const scaleY = GEMINI_NORM_MAX / videoHeight;

	return [
		Math.round(x1 * scaleX),
		Math.round(GEMINI_NORM_MAX - y2 * scaleY),
		Math.round(x2 * scaleX),
		Math.round(GEMINI_NORM_MAX - y1 * scaleY)
	];
}
