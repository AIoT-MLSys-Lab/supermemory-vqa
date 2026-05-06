/**
 * Video Source Utilities
 *
 * Utilities for resolving video paths to playable URLs and managing video sources.
 */

/**
 * Resolve a video path to a playable URL.
 * Handles different path formats:
 * - Already proper server path (/uploads/...)
 * - Just a filename (assumes /uploads/)
 * - Absolute path (serves via API)
 * - Already an API call (returns as-is)
 */
export function resolveVideoSource(path: string): string {
	if (!path) return "";

	// Already a proper server path
	if (path.startsWith("/uploads/")) return path;

	// Just a filename, assume uploads
	if (!path.includes("/")) return `/uploads/${path}`;

	// Absolute path (e.g. /research/...) - needs to be served via API
	if (path.startsWith("/")) {
		// Check if it's already an API call to avoid double encoding if logic runs twice
		if (path.startsWith("/api/serve-video")) return path;
		return `/api/serve-video?path=${encodeURIComponent(path)}`;
	}

	return path;
}

/**
 * Extract filename from any video source path format.
 * Handles both regular paths and API-served paths.
 */
export function getFilenameFromSource(source: string): string {
	if (source.includes("/api/serve-video?path=")) {
		const encodedPath = source.split("path=")[1];
		if (encodedPath) {
			const decodedPath = decodeURIComponent(encodedPath);
			return decodedPath.split("/").pop() || source;
		}
	}
	return source.split("/").pop() || source;
}

/**
 * Deduplicate video sources by filename (case-insensitive).
 * Returns array of unique sources, keeping the first occurrence of each filename.
 */
export function deduplicateVideoSources(sources: string[]): string[] {
	const sourcesByFilename = new Map<string, string>();

	sources.forEach(source => {
		const filename = getFilenameFromSource(source);
		const normalizedKey = filename.toLowerCase();
		if (!sourcesByFilename.has(normalizedKey)) {
			sourcesByFilename.set(normalizedKey, source);
		}
	});

	return Array.from(sourcesByFilename.values());
}

/**
 * Build list of unique video sources from current video and annotations.
 * Includes main video path, active source, and all evidence video paths.
 */
export function collectVideoSourcesFromAnnotations(
	mainVideoPath: string,
	activeVideoSource: string,
	annotations: Array<{
		answer_evidence?: Array<{ video_path?: string }>;
		answer_video_path?: string;
	}>
): string[] {
	const sources: string[] = [];

	// Always include main video
	if (mainVideoPath) sources.push(mainVideoPath);

	// Always include currently active source
	if (activeVideoSource && activeVideoSource !== mainVideoPath) {
		sources.push(activeVideoSource);
	}

	// Collect from all annotations
	annotations.forEach(ann => {
		if (ann.answer_evidence) {
			ann.answer_evidence.forEach(ev => {
				if (ev.video_path) {
					const resolved = resolveVideoSource(ev.video_path);
					sources.push(resolved);
				}
			});
		}
		if (ann.answer_video_path) {
			sources.push(resolveVideoSource(ann.answer_video_path));
		}
	});

	return deduplicateVideoSources(sources);
}
