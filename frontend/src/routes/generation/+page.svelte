<script lang="ts">
	import { goto } from "$app/navigation";
	import {
		Card,
		CardHeader,
		CardTitle,
		CardContent,
	} from "$lib/components/ui/card";
	import Button from "$lib/components/ui/button/Button.svelte";
	import Label from "$lib/components/ui/label/Label.svelte";
	import Input from "$lib/components/ui/input/Input.svelte";
	import { apiClient } from "$lib/api";
	import {
		currentVideo,
		models,
		prompts,
		selectedModel,
		selectedPrompt,
		promptParameters,
		generateStatus,
		showAlert,
	} from "$lib/stores";
	import { onMount } from "svelte";
	import type { Prompt, PromptInputParameter } from "$lib/types";

	let currentPromptDetails = $state<Prompt | null>(null);
	let promptParamValues = $state<Record<string, unknown>>({});

	// Load models and prompts on mount
	onMount(async () => {
		try {
			const [modelData, promptData] = await Promise.all([
				apiClient.loadModels(),
				apiClient.loadPrompts(),
			]);
			models.set(modelData.models);
			prompts.set(promptData);

			if (modelData.models.length > 0 && !$selectedModel) {
				selectedModel.set(modelData.models[0].id);
			}
			if (promptData.length > 0 && !$selectedPrompt) {
				selectedPrompt.set(promptData[0].id);
			}
		} catch (error) {
			console.error("Failed to load models/prompts:", error);
			showAlert("error", "Failed to load models and prompts");
		}
	});

	// Load prompt details when selected prompt changes
	$effect(() => {
		if ($selectedPrompt) {
			loadPromptDetails($selectedPrompt);
		}
	});

	async function loadPromptDetails(promptId: string) {
		try {
			const result = await apiClient.getPromptDetails(promptId);
			if (result) {
				currentPromptDetails = result;
				// Initialize param values from defaults
				const params = currentPromptDetails.input_parameters || {};
				promptParamValues = Object.fromEntries(
					Object.entries(params).map(([name, param]) => [
						name,
						(param as PromptInputParameter).default ?? "",
					]),
				);
			}
		} catch (error) {
			console.error("Failed to load prompt details:", error);
		}
	}

	function updatePromptParam(name: string, value: unknown) {
		promptParamValues[name] = value;
		promptParameters.set(promptParamValues);
	}

	async function startGeneration() {
		if (!$currentVideo) {
			showAlert(
				"error",
				"No video selected. Please go to Review page first.",
			);
			return;
		}
		if (!$selectedModel || !$selectedPrompt) {
			showAlert("error", "Please select a model and prompt");
			return;
		}

		generateStatus.set({
			loading: true,
			message: "Generating annotations...",
		});

		try {
			const result = await apiClient.generateAnnotations({
				video_filename: $currentVideo.filename,
				model_id: $selectedModel,
				prompt_id: $selectedPrompt,
				prompt_params: promptParamValues,
			});

			if (result.success && result.data) {
				showAlert(
					"success",
					`Generated ${result.data.annotations.length} annotations`,
				);
				// Navigate back to review page
				goto("/review");
			} else {
				showAlert("error", result.error || "Generation failed");
			}
		} catch (error) {
			showAlert("error", `Error: ${error}`);
		} finally {
			generateStatus.set({ loading: false, message: "" });
		}
	}

	function cancelGeneration() {
		goto("/review");
	}
</script>

<main class="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
	<Card>
		<CardHeader>
			<div class="flex items-center justify-between">
				<div>
					<CardTitle>Generate Annotations</CardTitle>
					{#if $currentVideo}
						<p class="text-sm text-muted-foreground mt-1">
							Video: {$currentVideo.filename}
						</p>
					{:else}
						<p class="text-sm text-destructive mt-1">
							⚠️ No video selected. Please select a video from the
							Review page.
						</p>
					{/if}
				</div>
				<Button variant="outline" onclick={cancelGeneration}>
					← Back to Review
				</Button>
			</div>
		</CardHeader>
		<CardContent class="space-y-6">
			<!-- Model Selection -->
			<div class="space-y-2">
				<Label for="modelSelect">Model</Label>
				<select
					id="modelSelect"
					class="w-full px-3 py-2 border rounded-lg bg-white"
					bind:value={$selectedModel}
					disabled={$generateStatus.loading}
				>
					<option value="">Select a model...</option>
					{#each $models as model}
						<option value={model.id}>{model.name}</option>
					{/each}
				</select>
			</div>

			<!-- Prompt Selection -->
			<div class="space-y-2">
				<Label for="promptSelect">Prompt Template</Label>
				<select
					id="promptSelect"
					class="w-full px-3 py-2 border rounded-lg bg-white"
					bind:value={$selectedPrompt}
					disabled={$generateStatus.loading}
				>
					<option value="">Select a prompt...</option>
					{#each $prompts as prompt}
						<option value={prompt.id}>{prompt.name}</option>
					{/each}
				</select>
			</div>

			<!-- Prompt Parameters -->
			{#if currentPromptDetails && Object.keys(currentPromptDetails.input_parameters || {}).length > 0}
				<div class="space-y-4">
					<h3 class="font-semibold text-sm">Prompt Parameters</h3>
					<div class="grid md:grid-cols-2 gap-4">
						{#each Object.entries(currentPromptDetails.input_parameters || {}) as [name, paramUntyped]}
							{@const param =
								paramUntyped as PromptInputParameter}
							<div class="space-y-2">
								<Label for={`param_${name}`}>
									{name}
									<span class="text-muted-foreground text-xs"
										>({param.type})</span
									>
								</Label>
								<p class="text-xs text-muted-foreground">
									{param.description}
								</p>
								{#if param.type === "boolean"}
									<input
										type="checkbox"
										id={`param_${name}`}
										checked={Boolean(
											promptParamValues[name],
										)}
										onchange={(e) =>
											updatePromptParam(
												name,
												e.currentTarget.checked,
											)}
										class="w-4 h-4"
										disabled={$generateStatus.loading}
									/>
								{:else if param.type === "integer" || param.type === "float"}
									<Input
										type="number"
										id={`param_${name}`}
										value={String(
											promptParamValues[name] ??
												param.default ??
												"",
										)}
										step={param.type === "float"
											? "0.1"
											: "1"}
										onchange={(e) =>
											updatePromptParam(
												name,
												Number(e.currentTarget.value),
											)}
										disabled={$generateStatus.loading}
									/>
								{:else}
									<Input
										type="text"
										id={`param_${name}`}
										value={String(
											promptParamValues[name] ??
												param.default ??
												"",
										)}
										onchange={(e) =>
											updatePromptParam(
												name,
												e.currentTarget.value,
											)}
										disabled={$generateStatus.loading}
									/>
								{/if}
							</div>
						{/each}
					</div>
				</div>
			{/if}

			<!-- Advanced Options (collapsed by default) -->
			<details class="border rounded-lg p-4">
				<summary class="cursor-pointer font-medium"
					>Advanced Options</summary
				>
				<div class="mt-4 space-y-2">
					<p class="text-sm text-muted-foreground">
						Advanced configuration options will be added here.
					</p>
				</div>
			</details>

			<!-- Status Message -->
			{#if $generateStatus.loading}
				<div
					class="bg-primary/10 border border-primary/20 rounded-lg p-4"
				>
					<div class="flex items-center gap-3">
						<div class="spinner w-5 h-5"></div>
						<p class="text-sm font-medium">
							{$generateStatus.message}
						</p>
					</div>
				</div>
			{/if}

			<!-- Action Buttons -->
			<div class="flex gap-3 pt-4">
				<Button
					onclick={startGeneration}
					disabled={$generateStatus.loading ||
						!$currentVideo ||
						!$selectedModel ||
						!$selectedPrompt}
					class="flex-1"
				>
					{#if $generateStatus.loading}
						<span class="spinner w-4 h-4 mr-2"></span>
						Generating...
					{:else}
						Start Generation
					{/if}
				</Button>
				<Button
					variant="outline"
					onclick={cancelGeneration}
					disabled={$generateStatus.loading}
				>
					Cancel
				</Button>
			</div>
		</CardContent>
	</Card>

	<!-- Jobs Panel (placeholder for future implementation) -->
	<Card class="mt-6">
		<CardHeader>
			<CardTitle>Recent Jobs</CardTitle>
		</CardHeader>
		<CardContent>
			<p class="text-sm text-muted-foreground text-center py-8">
				Job history and status tracking will be displayed here.
			</p>
		</CardContent>
	</Card>
</main>
