/**
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

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
