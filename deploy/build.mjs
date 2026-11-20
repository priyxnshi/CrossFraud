import { copyFile, mkdir, readFile, writeFile } from 'node:fs/promises';

await mkdir('public', { recursive: true });
const source = 'crossfraud/review_web/';
const html = await readFile(source + 'index.html', 'utf8');
await writeFile('public/index.html', html.replace('<head>', '<head><script src="/demo.js" defer></script>'));
for (const [from, to] of [[source+'ui.js','ui.js'],[source+'ui.css','ui.css'],['deploy/demo.js','demo.js'],['deploy/demo.json','demo.json']]) {
  await copyFile(from, 'public/' + to);
}
