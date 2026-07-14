import { defineNuxtConfig } from 'nuxt/config';

export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  ssr: false,
  devtools: { enabled: false },
  app: {
    pageTransition: { name: 'page', mode: 'out-in' },
    head: {
      link: [
        { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
        { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: 'anonymous' },
        {
          rel: 'stylesheet',
          href: 'https://fonts.googleapis.com/css2?family=Inter:ital,opsz,wght@0,14..32,100..900;1,14..32,100..900&display=swap',
        },
      ],
    },
  },
  modules: ['@nuxtjs/i18n', 'vuetify-nuxt-module', '@pinia/nuxt', '@nuxt/eslint', '@comark/nuxt'],
  i18n: {
    defaultLocale: 'en',
    strategy: 'no_prefix',
    vueI18n: './i18n.config.ts',
  },
  components: [{ path: '~/components' }],
  css: ['./app/assets/styles/vuetify.scss', './app/assets/styles/index.scss', './app/assets/styles/tailwind.css'],
  build: { transpile: ['vuetify'] },
  vite: {
    server: {
      watch: {
        ignored: ['**/node_modules/**', '**/.nuxt/**', '**/.output/**', '**/dist/**', '**/.git/**'],
      },
    },
    optimizeDeps: { include: ['lucide-vue-next', 'markdown-it', 'dompurify', 'shiki', 'mermaid', 'echarts/core'] },
    build: {
      cssMinify: 'lightningcss',
      chunkSizeWarningLimit: 900,
      modulePreload: { polyfill: false },
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes('node_modules')) return;
            if (id.includes('vuetify')) return 'vendor-vuetify';
            if (id.includes('markdown-it') || id.includes('dompurify')) return 'vendor-markdown';
            if (id.includes('mermaid')) return 'vendor-mermaid';
            if (id.includes('echarts')) return 'vendor-echarts';
            if (id.includes('shiki') || id.includes('@shikijs')) return 'vendor-shiki';
            if (id.includes('lucide-vue-next')) return 'vendor-icons';
            return;
          },
        },
      },
    },
  },
  nitro: {
    watchOptions: {
      ignored: ['**/node_modules/**', '**/.nuxt/**', '**/.output/**', '**/dist/**', '**/.git/**'],
    },
  },
  postcss: { plugins: { '@tailwindcss/postcss': {} } },
  runtimeConfig: {
    public: {
      gdceApiEnabled: true,
      gdceApiBaseUrl: 'http://localhost:8000',
      maxImageSizeMb: 5,
      allowedImageTypes: 'image/jpeg,image/png,image/webp',
      gdceDevEmail: 'frontend-dev@example.com',
      gdceDevPassword: 'password123',
      asyncTaskPollEnabled: false,
      asyncTaskPollBaseUrl: '',
      asyncTaskPollPath: '/v1/tasks/{{taskId}}',
      asyncTaskPollApiToken: '',
    },
  },
});
