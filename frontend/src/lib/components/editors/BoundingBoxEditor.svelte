<script lang="ts">
	import Input from "$lib/components/ui/input/Input.svelte";
	import Label from "$lib/components/ui/label/Label.svelte";
	import Button from "$lib/components/ui/button/Button.svelte";
	import type { BoundingBoxData } from "$lib/types/annotation-data-types";

	interface Props {
		data: BoundingBoxData;
		label?: string;
		currentVideoPath?: string;
		availableVideoSources?: string[];
		onChange: (newData: BoundingBoxData) => void;
		onRequestCanvasEdit?: () => void; // Callback to enable canvas drag/resize mode
	}

	let {
		data,
		label = "Bounding Box",
		currentVideoPath,
		availableVideoSources = [],
		onChange,
		onRequestCanvasEdit,
	}: Props = $props();

	function handleCoordChange(index: number, value: string) {
		const numValue = parseInt(value) || 0;
		const box_2d = [...(data.value?.box_2d || [0, 0, 100, 100])];
		box_2d[index] = numValue;
		onChange({
			...data,
			value: {
				...data.value,
				box_2d,
			},
		});
	}

	function handleTimestampChange(e: Event) {
		const target = e.currentTarget as HTMLInputElement;
		onChange({
			...data,
			value: {
				box_2d: data.value?.box_2d || [0, 0, 100, 100],
				...data.value,
				timestamp: target.value,
			},
		});
	}

	function handleVideoPathChange(e: Event) {
		const target = e.currentTarget as HTMLSelectElement;
		onChange({
			...data,
			value: {
				box_2d: data.value?.box_2d || [0, 0, 100, 100],
				...data.value,
				video_path: target.value,
			},
		});
	}

	function handleDescriptionChange(e: Event) {
		const target = e.currentTarget as HTMLInputElement;
		onChange({
			...data,
			value: {
				box_2d: data.value?.box_2d || [0, 0, 100, 100],
				...data.value,
				description: target.value,
			},
		});
	}

	function getVideoDisplayName(path?: string): string {
		if (!path) return "Current video";
		const parts = path.split("/");
		return parts[parts.length - 1] || path;
	}
</script>

<div class="bounding-box-editor space-y-3">
	{#if label}
		<div class="flex items-center justify-between">
			<Label>{label}</Label>
			{#if data.editable && onRequestCanvasEdit}
				<Button
					size="sm"
					variant="outline"
					onclick={onRequestCanvasEdit}
					class="text-xs"
				>
					🎨 Edit on canvas
				</Button>
			{/if}
		</div>
	{/if}

	<div class="grid grid-cols-2 gap-3">
		<div class="space-y-1">
			<Label class="text-xs">Timestamp</Label>
			<Input
				type="text"
				value={data.value?.timestamp || ""}
				oninput={handleTimestampChange}
				placeholder="00:00"
			/>
		</div>
		<div class="space-y-1">
			<Label class="text-xs">Video Source</Label>
			{#if availableVideoSources.length > 0}
				<select
					class="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
					value={data.value?.video_path || currentVideoPath}
					onchange={handleVideoPathChange}
				>
					{#each availableVideoSources as source}
						<option value={source}>
							{getVideoDisplayName(source)}
							{source === currentVideoPath ? "(Current)" : ""}
						</option>
					{/each}
				</select>
			{:else}
				<Input type="text" value={currentVideoPath || ""} disabled />
			{/if}
		</div>
	</div>

	<div class="space-y-1">
		<Label class="text-xs">Description (optional)</Label>
		<Input
			type="text"
			value={data.value?.description || ""}
			oninput={handleDescriptionChange}
			placeholder="Describe the bounding box..."
		/>
	</div>

	<div class="grid grid-cols-4 gap-2">
		<div class="space-y-1">
			<Label class="text-xs">Y1</Label>
			<Input
				type="text"
				value={String(data.value?.box_2d?.[0] || 0)}
				oninput={(e) => handleCoordChange(0, e.currentTarget.value)}
			/>
		</div>
		<div class="space-y-1">
			<Label class="text-xs">X1</Label>
			<Input
				type="text"
				value={String(data.value?.box_2d?.[1] || 0)}
				oninput={(e) => handleCoordChange(1, e.currentTarget.value)}
			/>
		</div>
		<div class="space-y-1">
			<Label class="text-xs">Y2</Label>
			<Input
				type="text"
				value={String(data.value?.box_2d?.[2] || 0)}
				oninput={(e) => handleCoordChange(2, e.currentTarget.value)}
			/>
		</div>
		<div class="space-y-1">
			<Label class="text-xs">X2</Label>
			<Input
				type="text"
				value={String(data.value?.box_2d?.[3] || 0)}
				oninput={(e) => handleCoordChange(3, e.currentTarget.value)}
			/>
		</div>
	</div>
	<div class="text-xs text-gray-500">
		Coordinates in Gemini format: [y1, x1, y2, x2] (0-1000)
	</div>
</div>
