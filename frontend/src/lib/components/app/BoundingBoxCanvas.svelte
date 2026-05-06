<script lang="ts">
	import { onMount, onDestroy } from "svelte";
	import {
		convertGeminiToPixel,
		convertPixelToGemini,
	} from "$lib/utils/bounding-box";
	import type { LocationBox } from "$lib/types";

	interface Props {
		videoElement?: HTMLVideoElement;
		activeBox?: LocationBox | null;
		activeBoxIndex?: number;
		onBoxUpdate?: (box: LocationBox, index: number) => void;
		onBoxCreate?: (box: LocationBox) => void;
	}

	let {
		videoElement,
		activeBox = null,
		activeBoxIndex = -1,
		onBoxUpdate,
		onBoxCreate,
	}: Props = $props();

	let canvas: HTMLCanvasElement | undefined = $state();
	let ctx: CanvasRenderingContext2D | null = $state(null);

	// Edit mode state
	let editMode = $state({
		active: false,
		dragging: false,
		resizing: false,
		resizeHandle: "" as string,
		startX: 0,
		startY: 0,
		originalBox: null as number[] | null,
	});

	// Draw mode for creating new boxes
	let drawMode = $state({
		active: false,
		startX: 0,
		startY: 0,
		currentBox: null as number[] | null,
	});

	const GEMINI_NORM_MAX = 1000;
	const BOX_COLOR = "hsl(0 72% 51%)"; // Primary red
	const BOX_ACTIVE_COLOR = "hsl(142 71% 45%)"; // Success green
	const HANDLE_SIZE = 8;

	onMount(() => {
		if (canvas) {
			ctx = canvas.getContext("2d");
			resizeCanvas();
			window.addEventListener("resize", resizeCanvas);
		}
	});

	onDestroy(() => {
		window.removeEventListener("resize", resizeCanvas);
	});

	function resizeCanvas() {
		if (!canvas || !videoElement) return;

		canvas.width = videoElement.clientWidth;
		canvas.height = videoElement.clientHeight;

		if (activeBox) {
			drawBox();
		}
	}

	/**
	 * Calculate the actual video display area within the video element
	 * HTML video elements with w-full scale naturally (no letterboxing) -
	 * the video fills the element and maintains aspect ratio automatically.
	 * We only need to track the container size for coordinate conversion.
	 */
	function getVideoDisplayBounds(): {
		offsetX: number;
		offsetY: number;
		displayWidth: number;
		displayHeight: number;
	} | null {
		if (!videoElement || !canvas) return null;

		const intrinsicWidth = videoElement.videoWidth;
		const intrinsicHeight = videoElement.videoHeight;

		if (intrinsicWidth === 0 || intrinsicHeight === 0) return null;

		// Video element with w-full scales to fill width, height auto-adjusts
		// No letterboxing occurs - the element's clientWidth/clientHeight IS the video display area
		return {
			offsetX: 0,
			offsetY: 0,
			displayWidth: canvas.width,
			displayHeight: canvas.height,
		};
	}

	// Watch for video changes
	$effect(() => {
		if (videoElement) {
			const redrawEvents = [
				"loadedmetadata",
				"resize",
				"seeked",
				"loadeddata",
			];
			redrawEvents.forEach((event) =>
				videoElement.addEventListener(event, resizeCanvas),
			);
			return () => {
				redrawEvents.forEach((event) =>
					videoElement.removeEventListener(event, resizeCanvas),
				);
			};
		}
	});

	// Watch for active box changes - only draw, never auto-clear
	// The parent component controls when to clear via the clear() method
	$effect(() => {
		if (activeBox && ctx) {
			drawBox();
		}
		// DO NOT auto-clear when activeBox becomes null
		// This prevents re-renders from clearing the box unexpectedly
	});

	function clearCanvas() {
		if (!ctx || !canvas) return;
		ctx.clearRect(0, 0, canvas.width, canvas.height);
	}

	function drawBox() {
		if (!ctx || !canvas || !videoElement || !activeBox?.box_2d) return;

		clearCanvas();

		const videoWidth = videoElement.videoWidth;
		const videoHeight = videoElement.videoHeight;

		// Get the actual display bounds accounting for aspect ratio
		const bounds = getVideoDisplayBounds();
		if (!bounds) return;

		const { offsetX, offsetY, displayWidth, displayHeight } = bounds;

		// Convert from Gemini format to pixel format
		const pixelBox = convertGeminiToPixel(
			activeBox.box_2d,
			videoWidth,
			videoHeight,
		);
		if (!pixelBox) return;

		// Scale to the actual video display area (not the full canvas)
		const scaleX = displayWidth / videoWidth;
		const scaleY = displayHeight / videoHeight;

		const [x1, y1, x2, y2] = pixelBox;
		// Apply scaling and offset for the actual video display position
		const displayX1 = x1 * scaleX + offsetX;
		const displayY1 = y1 * scaleY + offsetY;
		const displayX2 = x2 * scaleX + offsetX;
		const displayY2 = y2 * scaleY + offsetY;

		// Draw box
		ctx.strokeStyle = editMode.active ? BOX_ACTIVE_COLOR : BOX_COLOR;
		ctx.lineWidth = 2;
		ctx.setLineDash([]);
		ctx.strokeRect(
			displayX1,
			displayY1,
			displayX2 - displayX1,
			displayY2 - displayY1,
		);

		// Draw label
		ctx.fillStyle = editMode.active ? BOX_ACTIVE_COLOR : BOX_COLOR;
		ctx.font = "14px Arial";
		const label = `Box ${activeBoxIndex + 1}`;
		const labelWidth = ctx.measureText(label).width + 8;
		ctx.fillRect(displayX1, displayY1 - 20, labelWidth, 20);
		ctx.fillStyle = "white";
		ctx.fillText(label, displayX1 + 4, displayY1 - 6);

		// Draw resize handles if in edit mode
		if (editMode.active) {
			drawResizeHandles(displayX1, displayY1, displayX2, displayY2);
		}
	}

	function drawResizeHandles(x1: number, y1: number, x2: number, y2: number) {
		if (!ctx) return;

		const handles = [
			{ x: x1, y: y1, cursor: "nw-resize", name: "nw" },
			{ x: x2, y: y1, cursor: "ne-resize", name: "ne" },
			{ x: x1, y: y2, cursor: "sw-resize", name: "sw" },
			{ x: x2, y: y2, cursor: "se-resize", name: "se" },
			{ x: (x1 + x2) / 2, y: y1, cursor: "n-resize", name: "n" },
			{ x: (x1 + x2) / 2, y: y2, cursor: "s-resize", name: "s" },
			{ x: x1, y: (y1 + y2) / 2, cursor: "w-resize", name: "w" },
			{ x: x2, y: (y1 + y2) / 2, cursor: "e-resize", name: "e" },
		];

		ctx.fillStyle = BOX_ACTIVE_COLOR;
		handles.forEach((handle) => {
			ctx!.fillRect(
				handle.x - HANDLE_SIZE / 2,
				handle.y - HANDLE_SIZE / 2,
				HANDLE_SIZE,
				HANDLE_SIZE,
			);
		});
	}

	function getMousePos(e: MouseEvent): { x: number; y: number } {
		if (!canvas) return { x: 0, y: 0 };
		const rect = canvas.getBoundingClientRect();
		return {
			x: e.clientX - rect.left,
			y: e.clientY - rect.top,
		};
	}

	function handleMouseDown(e: MouseEvent) {
		if (!canvas || !videoElement) return;

		const pos = getMousePos(e);

		if (drawMode.active) {
			// Start drawing new box
			drawMode.startX = pos.x;
			drawMode.startY = pos.y;
			drawMode.currentBox = [pos.x, pos.y, pos.x, pos.y];
			return;
		}

		if (editMode.active && activeBox?.box_2d) {
			const videoWidth = videoElement.videoWidth;
			const videoHeight = videoElement.videoHeight;

			const bounds = getVideoDisplayBounds();
			if (!bounds) return;
			const { offsetX, offsetY, displayWidth, displayHeight } = bounds;

			const pixelBox = convertGeminiToPixel(
				activeBox.box_2d,
				videoWidth,
				videoHeight,
			);
			if (!pixelBox) return;

			const scaleX = displayWidth / videoWidth;
			const scaleY = displayHeight / videoHeight;

			const [x1, y1, x2, y2] = pixelBox;
			const displayX1 = x1 * scaleX + offsetX;
			const displayY1 = y1 * scaleY + offsetY;
			const displayX2 = x2 * scaleX + offsetX;
			const displayY2 = y2 * scaleY + offsetY;

			// Check if clicking on a resize handle
			const handle = getResizeHandle(
				pos.x,
				pos.y,
				displayX1,
				displayY1,
				displayX2,
				displayY2,
			);
			if (handle) {
				editMode.resizing = true;
				editMode.resizeHandle = handle;
				editMode.startX = pos.x;
				editMode.startY = pos.y;
				editMode.originalBox = [...activeBox.box_2d];
				return;
			}

			// Check if clicking inside the box for dragging
			if (
				pos.x >= displayX1 &&
				pos.x <= displayX2 &&
				pos.y >= displayY1 &&
				pos.y <= displayY2
			) {
				editMode.dragging = true;
				editMode.startX = pos.x;
				editMode.startY = pos.y;
				editMode.originalBox = [...activeBox.box_2d];
			}
		}
	}

	function handleMouseMove(e: MouseEvent) {
		if (!canvas || !videoElement || !ctx) return;

		const pos = getMousePos(e);

		if (drawMode.active && drawMode.currentBox) {
			// Update drawing box
			drawMode.currentBox = [
				drawMode.startX,
				drawMode.startY,
				pos.x,
				pos.y,
			];
			drawDrawingBox();
			return;
		}

		if (!activeBox?.box_2d) return;

		const videoWidth = videoElement.videoWidth;
		const videoHeight = videoElement.videoHeight;

		const bounds = getVideoDisplayBounds();
		if (!bounds) return;
		const { offsetX, offsetY, displayWidth, displayHeight } = bounds;

		const scaleX = displayWidth / videoWidth;
		const scaleY = displayHeight / videoHeight;

		if (editMode.dragging && editMode.originalBox) {
			const deltaX = (pos.x - editMode.startX) / scaleX;
			const deltaY = (pos.y - editMode.startY) / scaleY;

			// Convert original box to pixel format, apply delta, convert back
			const origPixel = convertGeminiToPixel(
				editMode.originalBox,
				videoWidth,
				videoHeight,
			);
			if (!origPixel) return;

			const newPixel = [
				origPixel[0] + deltaX,
				origPixel[1] + deltaY,
				origPixel[2] + deltaX,
				origPixel[3] + deltaY,
			];

			const newGemini = convertPixelToGemini(
				newPixel,
				videoWidth,
				videoHeight,
			);
			if (newGemini && activeBox) {
				activeBox.box_2d = newGemini;
				drawBox();
			}
		} else if (editMode.resizing && editMode.originalBox) {
			const origPixel = convertGeminiToPixel(
				editMode.originalBox,
				videoWidth,
				videoHeight,
			);
			if (!origPixel) return;

			const deltaX = (pos.x - editMode.startX) / scaleX;
			const deltaY = (pos.y - editMode.startY) / scaleY;

			const newPixel = applyResize(
				origPixel,
				editMode.resizeHandle,
				deltaX,
				deltaY,
			);
			const newGemini = convertPixelToGemini(
				newPixel,
				videoWidth,
				videoHeight,
			);
			if (newGemini && activeBox) {
				activeBox.box_2d = newGemini;
				drawBox();
			}
		} else if (editMode.active) {
			// Update cursor based on position
			const pixelBox = convertGeminiToPixel(
				activeBox.box_2d,
				videoWidth,
				videoHeight,
			);
			if (!pixelBox) return;

			const [x1, y1, x2, y2] = pixelBox;
			const displayX1 = x1 * scaleX + offsetX;
			const displayY1 = y1 * scaleY + offsetY;
			const displayX2 = x2 * scaleX + offsetX;
			const displayY2 = y2 * scaleY + offsetY;

			const handle = getResizeHandle(
				pos.x,
				pos.y,
				displayX1,
				displayY1,
				displayX2,
				displayY2,
			);
			if (handle) {
				canvas.style.cursor = getCursorForHandle(handle);
			} else if (
				pos.x >= displayX1 &&
				pos.x <= displayX2 &&
				pos.y >= displayY1 &&
				pos.y <= displayY2
			) {
				canvas.style.cursor = "move";
			} else {
				canvas.style.cursor = "default";
			}
		}
	}

	function handleMouseUp(e: MouseEvent) {
		if (drawMode.active && drawMode.currentBox) {
			// Finalize new box
			finalizeDrawing();
			return;
		}

		if (
			(editMode.dragging || editMode.resizing) &&
			activeBox &&
			onBoxUpdate
		) {
			onBoxUpdate(activeBox, activeBoxIndex);
		}

		editMode.dragging = false;
		editMode.resizing = false;
		editMode.resizeHandle = "";
		editMode.originalBox = null;
	}

	function drawDrawingBox() {
		if (!ctx || !canvas || !drawMode.currentBox) return;

		clearCanvas();

		const [x1, y1, x2, y2] = drawMode.currentBox;
		ctx.strokeStyle = BOX_COLOR;
		ctx.lineWidth = 2;
		ctx.setLineDash([5, 5]);
		ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
	}

	function finalizeDrawing() {
		if (!canvas || !videoElement || !drawMode.currentBox || !onBoxCreate)
			return;

		const videoWidth = videoElement.videoWidth;
		const videoHeight = videoElement.videoHeight;

		const bounds = getVideoDisplayBounds();
		if (!bounds) return;
		const { offsetX, offsetY, displayWidth, displayHeight } = bounds;

		const scaleX = videoWidth / displayWidth;
		const scaleY = videoHeight / displayHeight;

		const [x1, y1, x2, y2] = drawMode.currentBox;
		// Subtract offset before scaling to get coordinates relative to video display area
		const pixelBox = [
			(Math.min(x1, x2) - offsetX) * scaleX,
			(Math.min(y1, y2) - offsetY) * scaleY,
			(Math.max(x1, x2) - offsetX) * scaleX,
			(Math.max(y1, y2) - offsetY) * scaleY,
		];

		const geminiBox = convertPixelToGemini(
			pixelBox,
			videoWidth,
			videoHeight,
		);
		if (geminiBox) {
			const newBox: LocationBox = {
				box_2d: geminiBox,
				timestamp: formatTimestamp(videoElement.currentTime),
			};
			onBoxCreate(newBox);
		}

		drawMode.currentBox = null;
		clearCanvas();
	}

	function formatTimestamp(seconds: number): string {
		const mins = Math.floor(seconds / 60);
		const secs = Math.floor(seconds % 60);
		return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
	}

	function getResizeHandle(
		x: number,
		y: number,
		x1: number,
		y1: number,
		x2: number,
		y2: number,
	): string {
		const handles: { name: string; x: number; y: number }[] = [
			{ name: "nw", x: x1, y: y1 },
			{ name: "ne", x: x2, y: y1 },
			{ name: "sw", x: x1, y: y2 },
			{ name: "se", x: x2, y: y2 },
			{ name: "n", x: (x1 + x2) / 2, y: y1 },
			{ name: "s", x: (x1 + x2) / 2, y: y2 },
			{ name: "w", x: x1, y: (y1 + y2) / 2 },
			{ name: "e", x: x2, y: (y1 + y2) / 2 },
		];

		for (const handle of handles) {
			if (
				Math.abs(x - handle.x) <= HANDLE_SIZE &&
				Math.abs(y - handle.y) <= HANDLE_SIZE
			) {
				return handle.name;
			}
		}
		return "";
	}

	function getCursorForHandle(handle: string): string {
		const cursors: Record<string, string> = {
			nw: "nw-resize",
			ne: "ne-resize",
			sw: "sw-resize",
			se: "se-resize",
			n: "n-resize",
			s: "s-resize",
			w: "w-resize",
			e: "e-resize",
		};
		return cursors[handle] || "default";
	}

	function applyResize(
		box: number[],
		handle: string,
		dx: number,
		dy: number,
	): number[] {
		const [x1, y1, x2, y2] = box;
		const result = [...box];

		switch (handle) {
			case "nw":
				result[0] = x1 + dx;
				result[1] = y1 + dy;
				break;
			case "ne":
				result[2] = x2 + dx;
				result[1] = y1 + dy;
				break;
			case "sw":
				result[0] = x1 + dx;
				result[3] = y2 + dy;
				break;
			case "se":
				result[2] = x2 + dx;
				result[3] = y2 + dy;
				break;
			case "n":
				result[1] = y1 + dy;
				break;
			case "s":
				result[3] = y2 + dy;
				break;
			case "w":
				result[0] = x1 + dx;
				break;
			case "e":
				result[2] = x2 + dx;
				break;
		}

		return result;
	}

	// Arrow key movement for bounding boxes
	const ARROW_MOVE_STEP = 5; // pixels to move per arrow key press

	function handleKeyDown(e: KeyboardEvent) {
		if (!editMode.active || !activeBox?.box_2d || !videoElement) return;

		const arrowKeys = ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"];
		if (!arrowKeys.includes(e.key)) return;

		e.preventDefault();
		e.stopPropagation();

		const videoWidth = videoElement.videoWidth;
		const videoHeight = videoElement.videoHeight;
		if (videoWidth === 0 || videoHeight === 0) return;

		const pixelBox = convertGeminiToPixel(
			activeBox.box_2d,
			videoWidth,
			videoHeight,
		);
		if (!pixelBox) return;

		let dx = 0;
		let dy = 0;
		switch (e.key) {
			case "ArrowUp":
				dy = -ARROW_MOVE_STEP;
				break;
			case "ArrowDown":
				dy = ARROW_MOVE_STEP;
				break;
			case "ArrowLeft":
				dx = -ARROW_MOVE_STEP;
				break;
			case "ArrowRight":
				dx = ARROW_MOVE_STEP;
				break;
		}

		const newPixel = [
			pixelBox[0] + dx,
			pixelBox[1] + dy,
			pixelBox[2] + dx,
			pixelBox[3] + dy,
		];

		const newGemini = convertPixelToGemini(
			newPixel,
			videoWidth,
			videoHeight,
		);
		if (newGemini && activeBox) {
			activeBox.box_2d = newGemini;
			drawBox();
			if (onBoxUpdate) {
				onBoxUpdate(activeBox, activeBoxIndex);
			}
		}
	}

	// Exposed methods
	export function enableEditMode() {
		editMode.active = true;
		drawBox();
	}

	export function disableEditMode() {
		editMode.active = false;
		editMode.dragging = false;
		editMode.resizing = false;
		if (canvas) canvas.style.cursor = "default";
		drawBox();
	}

	export function enableDrawMode() {
		drawMode.active = true;
		if (canvas) canvas.style.cursor = "crosshair";
	}

	export function disableDrawMode() {
		drawMode.active = false;
		drawMode.currentBox = null;
		if (canvas) canvas.style.cursor = "default";
		clearCanvas();
	}

	export function clear() {
		clearCanvas();
	}

	export function redraw() {
		if (activeBox) {
			drawBox();
		}
	}
</script>

<canvas
	bind:this={canvas}
	class="absolute top-0 left-0 w-full h-full pointer-events-auto"
	class:pointer-events-none={!editMode.active && !drawMode.active}
	tabindex={editMode.active ? 0 : -1}
	aria-label="Bounding box canvas"
	onmousedown={(e) => {
		handleMouseDown(e);
		if (editMode.active && canvas) canvas.focus();
	}}
	onmousemove={handleMouseMove}
	onmouseup={handleMouseUp}
	onmouseleave={handleMouseUp}
	onkeydown={handleKeyDown}
></canvas>
