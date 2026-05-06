<script lang="ts">
	import './layout.css';
	import { alertMessage } from '$lib/stores';
	import Alert from '$lib/components/ui/alert/Alert.svelte';
	import Header from '$lib/components/app/Header.svelte';

	let { children } = $props();
</script>

<svelte:head>
	<title>SuperMemory - Video Annotation Platform</title>
	<meta name="description" content="Video Annotation Review Platform for AR Memory Assistant" />
</svelte:head>

<div class="min-h-screen bg-background">
	{#if $alertMessage}
		<div class="fixed top-4 right-4 z-50 max-w-md">
			<Alert variant={$alertMessage.type === 'error' ? 'destructive' : $alertMessage.type === 'success' ? 'success' : 'info'}>
				{$alertMessage.message}
			</Alert>
		</div>
	{/if}

	<Header />

	{@render children()}
</div>
