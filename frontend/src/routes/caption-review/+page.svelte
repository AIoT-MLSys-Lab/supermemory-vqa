<script lang="ts">
	import { VideoUpload, VideoList } from '$lib/components/app';
	import CaptionPlayer from '$lib/components/app/CaptionPlayer.svelte';
	import { currentVideo, playerSectionActive } from '$lib/stores';
</script>

<main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
	{#if $playerSectionActive && $currentVideo}
		<CaptionPlayer />
	{:else}
		<VideoUpload />
		<VideoList />
	{/if}
</main>
