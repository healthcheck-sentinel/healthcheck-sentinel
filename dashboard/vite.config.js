import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Fixed, local, read-only upstreams. No backend CORS or Docker changes required.
const routes = new Set(['/api/status', '/api/prometheus/targets', '/api/prometheus/resources']);
const resourceQuery = encodeURIComponent('{__name__=~"healthcheck_process_cpu_percent|healthcheck_process_memory_bytes"}');
const proxy = {
  '/api/status': { target: 'http://127.0.0.1:9101', rewrite: () => '/status', proxyTimeout: 5000 },
  '/api/prometheus/targets': { target: 'http://127.0.0.1:9090', rewrite: () => '/api/v1/targets', proxyTimeout: 5000 },
  '/api/prometheus/resources': { target: 'http://127.0.0.1:9090', rewrite: () => '/api/v1/query?query=' + resourceQuery, proxyTimeout: 5000 },
};
function readOnlyApi() {
  const install = server => { server.middlewares.use((req, res, next) => {
    if (!req.url?.startsWith('/api/')) return next();
    if (req.method !== 'GET' || !routes.has(req.url)) {
      res.statusCode = req.method === 'GET' ? 404 : 405;
      res.setHeader('Allow', 'GET');
      res.end('Read-only dashboard route');
      return;
    }
    res.setHeader('Cache-Control', 'no-store');
    next();
  }); };
  return { name: 'sentinel-read-only-api', configureServer: install, configurePreviewServer: install };
}
export default defineConfig({
  plugins: [readOnlyApi(), react()],
  server: { host: '127.0.0.1', port: 5173, strictPort: true, proxy },
  preview: { host: '127.0.0.1', port: 4173, strictPort: true, proxy },
});
