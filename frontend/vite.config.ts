import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	test: {
		include: ['src/**/*.{test,spec}.{js,ts}'],
		environment: 'jsdom',
		globals: true,
		setupFiles: ['./src/__tests__/setup.ts']
	},
	resolve: {
		conditions: ['browser']
	},
	build: {
		// Disable source maps in production for smaller bundle size
		sourcemap: false,
		// Enable minification for better performance
		minify: 'esbuild',
		// Chunk size warning limit
		chunkSizeWarningLimit: 1000
	},
	server: {
		proxy: {
			'/api': {
				target: 'http://localhost:5000',
				changeOrigin: true
			},
			'/uploads': {
				target: 'http://localhost:5000',
				changeOrigin: true
			}
		}
	}
});
