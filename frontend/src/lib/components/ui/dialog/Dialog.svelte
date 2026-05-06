<script lang="ts">
	import { onMount } from 'svelte';

	interface Props {
		open?: boolean;
		children?: import('svelte').Snippet;
	}

	let { open = $bindable(false), children }: Props = $props();
	let dialogElement: HTMLDialogElement | undefined = $state();

	onMount(() => {
		if (open && dialogElement) {
			dialogElement.showModal();
		}
	});

	$effect(() => {
		if (dialogElement) {
			if (open) {
				if (!dialogElement.open) {
					dialogElement.showModal();
				}
			} else {
				if (dialogElement.open) {
					dialogElement.close();
				}
			}
		}
	});

	function handleClose() {
		open = false;
	}

	function handleClick(event: MouseEvent) {
		if (event.target === dialogElement) {
			handleClose();
		}
	}

	function handleKeydown(event: KeyboardEvent) {
		if (event.key === 'Escape') {
			handleClose();
		}
	}
</script>

<dialog
	bind:this={dialogElement}
	class="fixed inset-0 z-50 flex items-center justify-center bg-transparent p-0 backdrop:bg-black/50"
	onclick={handleClick}
	onkeydown={handleKeydown}
	onclose={handleClose}
>
	{#if open}
		{@render children?.()}
	{/if}
</dialog>
