import { spawn, spawnSync } from 'node:child_process';
import { mkdirSync, existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const python = resolve(root, 'backend/.venv/bin/python');
if (!existsSync(python) || !existsSync(resolve(root, 'frontend/node_modules'))) {
  console.error('Run `make install` first. See README.md for Python/Node requirements.');
  process.exit(1);
}
mkdirSync(resolve(root, '.local'), { recursive: true });
// An operator must migrate/adopt explicitly. Never silently stamp an old database.
const schema = spawnSync(python, ['-m', 'app.database_cli', 'check'], {
  cwd: resolve(root, 'backend'), stdio: 'inherit', env: process.env,
});
if (schema.status !== 0) process.exit(schema.status || 1);
const processes = [
  spawn(python, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000', '--no-access-log'], {
    cwd: resolve(root, 'backend'), stdio: 'inherit', env: process.env,
  }),
  spawn('npm', ['run', 'dev'], {
    cwd: resolve(root, 'frontend'), stdio: 'inherit', env: process.env,
  }),
];
let stopping = false;
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of processes) child.kill('SIGTERM');
  process.exitCode = code;
}
for (const child of processes) {
  child.on('error', error => { console.error(error.message); stop(1); });
  child.on('exit', code => { if (!stopping) stop(code || 0); });
}
process.on('SIGINT', () => stop());
process.on('SIGTERM', () => stop());
console.log('Staytus: http://127.0.0.1:3000 · backend docs: http://127.0.0.1:8000/docs');
