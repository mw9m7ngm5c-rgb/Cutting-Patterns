// Lists every [PLACEHOLDER: ...] still in the site's content files.
// Run with: npm run placeholders
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const dirs = ['src/data', 'src/content'];
let count = 0;
for (const dir of dirs) {
  for (const file of fs.readdirSync(path.join(root, dir))) {
    const lines = fs.readFileSync(path.join(root, dir, file), 'utf8').split('\n');
    lines.forEach((line, i) => {
      if (/^\s*"_/.test(line)) return; // help notes, not content
      for (const m of line.matchAll(/\[PLACEHOLDER[^\]]*\]/g)) {
        console.log(`${dir}/${file}:${i + 1}  ${m[0]}`);
        count++;
      }
    });
  }
}
console.log(count ? `\n${count} placeholder(s) still to fill in.` : 'No placeholders left.');
