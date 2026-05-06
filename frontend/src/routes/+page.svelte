<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';

	onMount(() => {
		goto('/review');
	});
</script>

<div class="flex items-center justify-center min-h-screen">
	<p class="text-muted-foreground">Redirecting...</p>
</div>
