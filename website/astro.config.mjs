import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';
import site from './src/data/site.json' with { type: 'json' };

export default defineConfig({
  site: site.siteUrl,
  trailingSlash: 'always',
  integrations: [
    sitemap({ filter: (page) => !page.includes('/contact/thanks/') }),
  ],
  vite: { plugins: [tailwindcss()] },
});
