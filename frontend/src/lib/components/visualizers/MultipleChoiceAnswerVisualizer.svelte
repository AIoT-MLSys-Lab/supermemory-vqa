<script lang="ts">
	import type { AnswerChoice } from '$lib/types';
	import { unescapeHtml } from '$lib/utils';

	interface Props {
		value?: AnswerChoice[];
		isAnswerable?: boolean;
		selectedIndex?: number;
		onSelect?: (index: number) => void;
		showExplanations?: boolean;
	}

	let {
		value,
		isAnswerable = true,
		selectedIndex = -1,
		onSelect,
		showExplanations = true
	}: Props = $props();

	const choices = $derived(value || []);

	// Icon components for different choice types
	function getIcon(choiceType: string) {
		switch (choiceType) {
			case 'correct':
				return '✓';
			case 'vague':
				return '≈';
			case 'incorrect':
				return '✗';
			default:
				return '•';
		}
	}

	function getColorClass(choiceType: string, isSelected: boolean) {
		if (!isSelected) {
			return 'border-border bg-card hover:bg-secondary/50';
		}

		switch (choiceType) {
			case 'correct':
				return 'border-emerald-400 bg-emerald-50 ring-2 ring-emerald-400';
			case 'vague':
				return 'border-amber-400 bg-amber-50 ring-2 ring-amber-400';
			case 'incorrect':
				return 'border-red-400 bg-red-50 ring-2 ring-red-400';
			default:
				return 'border-border bg-secondary';
		}
	}

	function getIconColorClass(choiceType: string) {
		switch (choiceType) {
			case 'correct':
				return 'text-emerald-600 bg-emerald-100 border-emerald-300';
			case 'vague':
				return 'text-amber-600 bg-amber-100 border-amber-300';
			case 'incorrect':
				return 'text-red-600 bg-red-100 border-red-300';
			default:
				return 'text-muted-foreground bg-secondary border-border';
		}
	}

	function getLabel(choiceType: string) {
		switch (choiceType) {
			case 'correct':
				return 'Correct';
			case 'vague':
				return 'Vague';
			case 'incorrect':
				return 'Incorrect';
			default:
				return '';
		}
	}
</script>

{#if !isAnswerable}
	<div class="mb-3 p-3 bg-blue-50 border-l-4 border-blue-400 rounded">
		<div class="flex items-center gap-2 mb-2">
			<span class="text-blue-700 font-semibold text-sm">⚠ Unanswerable Question</span>
		</div>
		<p class="text-xs text-blue-700">
			This question cannot be answered from the available evidence.
		</p>
	</div>
{/if}

{#if choices.length > 0}
	<div class="space-y-2">
		<div class="text-xs font-medium text-muted-foreground mb-2">
			Answer Options:
		</div>
		{#each choices as choice, i}
			<button
				class="w-full text-left p-3 rounded-lg border-2 transition-all {getColorClass(
					choice.choice_type,
					selectedIndex === i
				)}"
				onclick={() => onSelect?.(i)}
				type="button"
			>
				<div class="flex items-start gap-3">
					<!-- Icon Badge -->
					<div
						class="flex-shrink-0 w-8 h-8 rounded-full border-2 flex items-center justify-center font-bold text-sm {getIconColorClass(
							choice.choice_type
						)}"
					>
						{getIcon(choice.choice_type)}
					</div>

					<!-- Content -->
					<div class="flex-1 min-w-0">
						<div class="flex items-center gap-2 mb-1">
							<span class="font-medium text-sm text-foreground">
								Option {String.fromCharCode(65 + i)}
							</span>
							<span
								class="text-[10px] font-semibold px-1.5 py-0.5 rounded {getIconColorClass(
									choice.choice_type
								)}"
							>
								{getLabel(choice.choice_type)}
							</span>
						</div>
						<p class="text-sm text-foreground break-words">
							{unescapeHtml(choice.text)}
						</p>
						{#if showExplanations && choice.explanation}
							<p class="text-xs text-muted-foreground italic mt-2 pl-3 border-l-2 border-border">
								{unescapeHtml(choice.explanation)}
							</p>
						{/if}
					</div>
				</div>
			</button>
		{/each}
	</div>
{:else}
	<p class="text-xs text-muted-foreground italic">No answer choices provided</p>
{/if}

<style>
	button {
		cursor: pointer;
	}

	button:hover {
		transform: translateY(-1px);
		box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
	}

	button:active {
		transform: translateY(0);
	}
</style>
