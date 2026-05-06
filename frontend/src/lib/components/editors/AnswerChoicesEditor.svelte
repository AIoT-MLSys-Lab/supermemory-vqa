<script lang="ts">
	import type { AnswerChoice } from '$lib/types';
	import Button from '$lib/components/ui/button/Button.svelte';
	import Input from '$lib/components/ui/input/Input.svelte';
	import Label from '$lib/components/ui/label/Label.svelte';
	import { unescapeHtml } from '$lib/utils';

	interface Props {
		value?: AnswerChoice[];
		isAnswerable?: boolean;
		onChange?: (value: AnswerChoice[]) => void;
		onAnswerableChange?: (isAnswerable: boolean) => void;
	}

	let { value, isAnswerable = true, onChange, onAnswerableChange }: Props = $props();

	let choices = $state<AnswerChoice[]>(
		value || [
			{ text: '', choice_type: 'correct', explanation: '' },
			{ text: '', choice_type: 'vague', explanation: '' },
			{ text: '', choice_type: 'incorrect', explanation: '' }
		]
	);

	let localIsAnswerable = $state(isAnswerable);

	$effect(() => {
		if (value && value.length > 0) {
			choices = [...value];
		}
	});

	$effect(() => {
		localIsAnswerable = isAnswerable;
	});

	function updateChoice(index: number, field: keyof AnswerChoice, newValue: string) {
		choices[index] = { ...choices[index], [field]: newValue as any };
		onChange?.(choices);
	}

	function addChoice() {
		choices = [...choices, { text: '', choice_type: 'incorrect', explanation: '' }];
		onChange?.(choices);
	}

	function removeChoice(index: number) {
		if (choices.length > 1) {
			choices = choices.filter((_, i) => i !== index);
			onChange?.(choices);
		}
	}

	function toggleAnswerable() {
		localIsAnswerable = !localIsAnswerable;
		onAnswerableChange?.(localIsAnswerable);
	}

	const choiceTypeOptions = ['correct', 'vague', 'incorrect'];
</script>

<div class="space-y-4">
	<!-- Answerable Toggle -->
	<div class="flex items-center gap-2 p-3 bg-secondary rounded-lg">
		<input
			type="checkbox"
			id="is-answerable"
			checked={localIsAnswerable}
			onchange={toggleAnswerable}
			class="w-4 h-4 rounded border-border"
		/>
		<Label for="is-answerable" class="text-sm font-medium cursor-pointer">
			Question is answerable from evidence
		</Label>
	</div>

	<!-- Answer Choices -->
	<div class="space-y-3">
		<div class="flex items-center justify-between">
			<Label class="text-sm font-semibold">Answer Choices</Label>
			<Button onclick={addChoice} size="sm" variant="outline">
				+ Add Choice
			</Button>
		</div>

		{#each choices as choice, i}
			<div class="p-4 border-2 border-border rounded-lg bg-card space-y-3">
				<div class="flex items-center justify-between">
					<span class="font-medium text-sm">Option {String.fromCharCode(65 + i)}</span>
					{#if choices.length > 1}
						<button
							onclick={() => removeChoice(i)}
							class="text-xs text-destructive hover:text-destructive/80"
							type="button"
						>
							Remove
						</button>
					{/if}
				</div>

				<!-- Choice Type -->
				<div>
					<Label for="choice-type-{i}" class="text-xs">Type</Label>
					<select
						id="choice-type-{i}"
						value={choice.choice_type}
						onchange={(e) =>
							updateChoice(i, 'choice_type', (e.target as HTMLSelectElement).value)}
						class="w-full mt-1 px-3 py-2 border border-border rounded-md text-sm bg-background"
					>
						{#each choiceTypeOptions as option}
							<option value={option}>
								{option.charAt(0).toUpperCase() + option.slice(1)}
							</option>
						{/each}
					</select>
				</div>

				<!-- Answer Text -->
				<div>
					<Label for="choice-text-{i}" class="text-xs">Answer Text</Label>
					<textarea
						id="choice-text-{i}"
						value={unescapeHtml(choice.text)}
						oninput={(e) =>
							updateChoice(i, 'text', (e.target as HTMLTextAreaElement).value)}
						class="w-full mt-1 px-3 py-2 border border-border rounded-md text-sm bg-background min-h-[80px]"
						placeholder="Enter the answer text..."
					/>
				</div>

				<!-- Explanation -->
				<div>
					<Label for="choice-explanation-{i}" class="text-xs">Explanation</Label>
					<textarea
						id="choice-explanation-{i}"
						value={unescapeHtml(choice.explanation)}
						oninput={(e) =>
							updateChoice(i, 'explanation', (e.target as HTMLTextAreaElement).value)}
						class="w-full mt-1 px-3 py-2 border border-border rounded-md text-sm bg-background min-h-[60px]"
						placeholder="Explain why this answer has this type..."
					/>
				</div>
			</div>
		{/each}
	</div>

	<p class="text-xs text-muted-foreground">
		Tip: For answerable questions, include one correct, one vague, and one incorrect answer. For
		unanswerable questions, all three choices should be incorrect (plausible but fabricated).
	</p>
</div>
