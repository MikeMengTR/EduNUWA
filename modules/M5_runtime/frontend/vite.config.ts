import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import fs from 'fs';

function dataServerPlugin() {
  const dataRoot = path.resolve(__dirname, '../../../data');

  return {
    name: 'serve-data',
    configureServer(server: any) {
      server.middlewares.use('/data', (req: any, res: any, next: any) => {
        const urlPath = req.url?.split('?')[0] || '/';
        const filePath = path.join(dataRoot, urlPath.replace(/^\/data\/?/, ''));
        if (!filePath.startsWith(dataRoot)) {
          res.statusCode = 403;
          res.end('Forbidden');
          return;
        }
        if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
          const ext = path.extname(filePath).toLowerCase();
          const mimeTypes: Record<string, string> = {
            '.json': 'application/json',
            '.wav': 'audio/wav',
            '.mp3': 'audio/mpeg',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
          };
          res.setHeader('Content-Type', mimeTypes[ext] || 'application/octet-stream');
          fs.createReadStream(filePath).pipe(res);
        } else {
          next();
        }
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), dataServerPlugin()],
  base: '/runtime/',
  root: __dirname,
  server: {
    port: 5173,
    fs: { allow: ['../../..'] },
  },
  build: {
    outDir: 'dist',
  },
});
