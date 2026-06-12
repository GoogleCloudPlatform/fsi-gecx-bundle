import { defineConfig } from 'vite';

export default defineConfig(({ command }) => {
  const base = command === 'serve' ? '/' : '/__VITE_BASE_PATH__/';
  return {
    base: base,
  server: {
    port: 8080
  },
  plugins: [
    {
      name: 'rewrite-login-config',
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          if (req.url && (req.url.startsWith('/login/config.js') || req.url.startsWith('/__VITE_BASE_PATH__/config.js'))) {
            req.url = '/config.js';
          }
          if (req.url && req.url.startsWith('/__VITE_BASE_PATH__/')) {
            req.url = req.url.replace('/__VITE_BASE_PATH__/', '/');
          }
          next();
        });
      }
    }
  ],
  build: {
    outDir: 'dist',
    sourcemap: true
  }
}
});
