<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';

	let sessionId = $state('');

	onMount(async () => {
		try {
			const res = await fetch('/api/session-info');
			if (res.ok) {
				const data = await res.json();
				sessionId = data.session_id;
			}
		} catch (e) {
			console.error('Failed to fetch session info:', e);
		}
	});

	const navItems = [
		{ path: '/review', label: 'QA Review' },
		{ path: '/caption-review', label: 'Caption Review' }
	];

	function isActive(path: string): boolean {
		return $page.url.pathname === path || $page.url.pathname.startsWith(path + '/');
	}
</script>

<header class="bg-white border-b border-border shadow-sm">
	<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex justify-between items-center">
		<div class="flex items-center gap-6">
			<div class="flex items-center gap-3">
				<h1 class="text-base font-semibold text-foreground">SuperMemory Video Annotation</h1>
				<span class="text-xs text-muted-foreground hidden sm:inline">
					AR Memory Assistant
				</span>
			</div>
			<nav class="flex items-center gap-1">
				{#each navItems as item}
					<a
						href={item.path}
						class="px-3 py-1.5 text-sm font-medium rounded transition-colors {isActive(item.path)
							? 'bg-primary/10 text-primary'
							: 'text-muted-foreground hover:bg-secondary hover:text-foreground'}"
					>
						{item.label}
					</a>
				{/each}
			</nav>
		</div>
		{#if sessionId}
			<div class="text-xs text-muted-foreground bg-secondary px-2 py-1 rounded">
				Session: {sessionId.slice(0, 8)}
			</div>
		{/if}
	</div>
</header>
