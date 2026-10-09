import { defineConfig } from 'vite';

export default defineConfig({
  base: './',
  build: {
    target: 'es2022',
    outDir: 'dist',
    assetsInlineLimit: 0,
    // rapier3d-compat embeds its WASM as base64 (4.3 MB raw, 1.6 MB gzipped); it gets its own chunk.
    chunkSizeWarningLimit: 4500,
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('@dimforge/rapier3d')) return 'rapier';
          if (id.includes('node_modules/three/')) return 'three';
        },
      },
    },
  },
  define: {
    __DEV_TOOLS__: JSON.stringify(process.env.EOA_RELEASE !== '1'),
  },
  server: { port: 5173, strictPort: true },
});
