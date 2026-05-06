import adapter from '@sveltejs/adapter-static';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	kit: {
		adapter: adapter({
			// Build to ../static/frontend so Flask can serve it
			pages: '../static/frontend',
			assets: '../static/frontend',
			fallback: 'index.html',
			precompress: false,
			strict: true
		}),
		paths: {
			base: ''
		}
	}
};

export default config;
