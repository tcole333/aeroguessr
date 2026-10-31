import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

// Vite serves public/ at the site root. The favicon once pointed at a public/vite.svg that
// .gitignore kept out of the repo, so it 404ed everywhere but the machine that made it.
// CI checks out only committed files, so this catches that.
const frontendRoot = join(__dirname, '..', '..');

test('every icon index.html links is a file in public/', () => {
  const html = readFileSync(join(frontendRoot, 'index.html'), 'utf8');
  const doc = new DOMParser().parseFromString(html, 'text/html');
  const iconLinks = doc.querySelectorAll('link[rel~="icon"], link[rel~="apple-touch-icon"]');
  const hrefs = [...iconLinks].map((link) => link.getAttribute('href') ?? '');

  expect(hrefs).not.toHaveLength(0);
  for (const href of hrefs) {
    expect(existsSync(join(frontendRoot, 'public', href)), href).toBe(true);
  }
});
