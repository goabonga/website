import { defineConfig } from 'vite';

export default defineConfig(({ mode }) => ({
  base: mode === 'production' ? '/static/' : '/',
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'https://api.goabonga.com',
        changeOrigin: true,
        secure: true,
      },
      '/oauth2': {
        target: 'https://auth.goabonga.com',
        changeOrigin: true,
        secure: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        entryFileNames: 'assets/index.js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: 'assets/[name][extname]',
      },
    },
  },
}));
