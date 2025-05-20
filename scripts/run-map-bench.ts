#!/usr/bin/env node
// Runs the MapPerformance benchmark using Vitest
import { spawn } from 'child_process';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const frontendDir = join(__dirname, '..', 'frontend');

const child = spawn(
  'npx',
  ['vitest', 'run', 'src/features/map/__tests__/MapPerformance.test.tsx'],
  { stdio: 'inherit', cwd: frontendDir }
);

child.on('exit', (code) => process.exit(code ?? 0));
