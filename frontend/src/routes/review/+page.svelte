<script lang="ts">
	import { VideoUpload, VideoList, VideoPlayer } from '$lib/components/app';
	import { currentVideo, playerSectionActive } from '$lib/stores';
</script>

<main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
	{#if $playerSectionActive && $currentVideo}
		<VideoPlayer />
	{:else}
		<VideoUpload />
		<VideoList />
	{/if}
</main>
