/**
 * Centralized theme tokens for the SuperMemory UI.
 *
 * Every component should reference these maps instead of hardcoding
 * status colors, skill colors, or icon SVG paths.
 */

// ---------------------------------------------------------------------------
// Review / annotation status
// ---------------------------------------------------------------------------

export type ReviewStatus = 'accepted' | 'rejected' | 'pending';

/** Maps a review status to a Badge variant name (from Badge.svelte). */
export const REVIEW_BADGE_VARIANT: Record<ReviewStatus, string> = {
    accepted: 'success',
    rejected: 'destructive',
    pending: 'warning',
} as const;

/** Human-readable label (with leading icon) for each review status. */
export const REVIEW_LABEL: Record<ReviewStatus, string> = {
    accepted: '✓ Accepted',
    rejected: '✗ Rejected',
    pending: '⏳ Pending',
} as const;

/**
 * CSS color value used on the progress bar markers & other places that
 * need a raw colour rather than a Tailwind class (e.g. SVG fill).
 */
export const REVIEW_COLOR: Record<ReviewStatus, string> = {
    accepted: 'var(--color-success)',
    rejected: 'var(--color-destructive)',
    pending: 'var(--color-info)',
} as const;

// ---------------------------------------------------------------------------
// Processing status badges  (VideoList, etc.)
// ---------------------------------------------------------------------------

export type ProcessingStatus = 'processed' | 'has_vrs' | 'pending' | 'approved' | 'rejected';

export const PROCESSING_BADGE_VARIANT: Record<ProcessingStatus, string> = {
    processed: 'info',
    has_vrs: 'success',
    pending: 'pending',
    approved: 'approved',
    rejected: 'rejected',
} as const;

export const PROCESSING_LABEL: Record<ProcessingStatus, string> = {
    processed: 'Processed',
    has_vrs: 'Has VRS',
    pending: 'Pending',
    approved: 'Approved',
    rejected: 'Rejected',
} as const;

// ---------------------------------------------------------------------------
// Skill type tokens
// ---------------------------------------------------------------------------

export type SkillType =
    | 'object_location_memory'
    | 'conversational_memory'
    | 'visual_recall'
    | 'timeline_reconstruction'
    | 'intent_recall'
    | 'in_context_retrieval';

/**
 * Tailwind classes applied to skill chips.
 * Uses the colour classes already defined in layout.css for consistency.
 */
export const SKILL_CLASSES: Record<string, string> = {
    object_location_memory: 'bg-blue-50 text-blue-700 border border-blue-200',
    conversational_memory: 'bg-purple-50 text-purple-700 border border-purple-200',
    visual_recall: 'bg-emerald-50 text-emerald-700 border border-emerald-200',
    timeline_reconstruction: 'bg-amber-50 text-amber-700 border border-amber-200',
    intent_recall: 'bg-rose-50 text-rose-700 border border-rose-200',
    in_context_retrieval: 'bg-cyan-50 text-cyan-700 border border-cyan-200',
} as const;

export const SKILL_DEFAULT_CLASS = 'bg-zinc-50 text-zinc-600 border border-zinc-200';

/** Human-readable skill labels. */
export const SKILL_LABEL: Record<string, string> = {
    object_location_memory: 'Object Location',
    conversational_memory: 'Conversational',
    visual_recall: 'Visual Recall',
    timeline_reconstruction: 'Timeline',
    intent_recall: 'Intent Recall',
    in_context_retrieval: 'In-Context',
} as const;

// ---------------------------------------------------------------------------
// Modality tokens
// ---------------------------------------------------------------------------

export const MODALITY_CLASSES: Record<string, string> = {
    visual: 'bg-indigo-50 text-indigo-700 border border-indigo-200',
    audio: 'bg-teal-50 text-teal-700 border border-teal-200',
    text: 'bg-orange-50 text-orange-700 border border-orange-200',
} as const;

export const MODALITY_DEFAULT_CLASS = 'bg-secondary text-foreground border border-border';

// ---------------------------------------------------------------------------
// Caption importance
// ---------------------------------------------------------------------------

export type ImportanceLevel = 'high' | 'medium' | 'low';

/** CSS color value for caption importance levels. */
export const IMPORTANCE_COLOR: Record<ImportanceLevel, string> = {
    high: 'hsl(0 72% 51%)',      // red
    medium: 'hsl(38 92% 50%)',   // amber/orange
    low: 'hsl(142 72% 40%)',     // green
} as const;

export const IMPORTANCE_COLOR_DEFAULT = 'hsl(240 4% 46%)'; // muted gray

// ---------------------------------------------------------------------------
// Caption confidence (used on timeline blocks)
// ---------------------------------------------------------------------------

export type ConfidenceLevel = 'very low' | 'low' | 'medium' | 'high' | 'very high';

/** CSS color value for caption confidence levels (used on timeline blocks). */
export const CONFIDENCE_COLOR: Record<ConfidenceLevel, string> = {
    'very low': 'hsl(0 72% 51%)',      // red
    'low': 'hsl(25 95% 53%)',          // orange
    'medium': 'hsl(38 92% 50%)',       // amber
    'high': 'hsl(142 72% 40%)',        // green
    'very high': 'hsl(160 84% 39%)',   // teal
} as const;

export const CONFIDENCE_COLOR_DEFAULT = 'hsl(240 4% 46%)'; // muted gray

// ---------------------------------------------------------------------------
// Shared sizing constants
// ---------------------------------------------------------------------------

/** Standard icon sizes in px for consistency. */
export const ICON_SIZE = {
    xs: 12,
    sm: 16,
    md: 20,
    lg: 24,
} as const;
