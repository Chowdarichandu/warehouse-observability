import { execFileSync } from 'node:child_process';
import { renameSync, rmSync } from 'node:fs';
import { resolve } from 'node:path';

// Keep a valid generated module visible while the generator is writing.
const temporary = resolve(`src/api/.generated-${process.pid}.ts`);
try {
  execFileSync('openapi-typescript', ['../backend/openapi.json', '-o', temporary], { stdio: 'inherit' });
  renameSync(temporary, resolve('src/api/generated.ts'));
} finally {
  rmSync(temporary, { force: true });
}
