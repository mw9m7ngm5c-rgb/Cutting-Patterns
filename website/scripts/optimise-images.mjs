// Turns the original photos listed in src/data/images.json into resized WebP
// files in public/images/, and records their sizes in src/data/image-sizes.json.
// Run with: npm run images   (it also runs automatically before dev and build).
import fs from 'node:fs';
import path from 'node:path';
import sharp from 'sharp';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const outDir = path.join(root, 'public/images');
const manifestPath = path.join(root, 'src/data/images.json');
const sizesPath = path.join(root, 'src/data/image-sizes.json');
const site = JSON.parse(fs.readFileSync(path.join(root, 'src/data/site.json'), 'utf8'));
const home = JSON.parse(fs.readFileSync(path.join(root, 'src/data/home.json'), 'utf8'));

const WIDTHS = [400, 640, 960, 1280, 1600, 1920];
const QUALITY = 74;

fs.mkdirSync(outDir, { recursive: true });
const { images } = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
const sizes = {};
let made = 0;

const isStale = (out, src) => !fs.existsSync(out) || fs.statSync(out).mtimeMs < fs.statSync(src).mtimeMs;

for (const img of images) {
  const src = path.join(root, img.source);
  if (!fs.existsSync(src)) {
    console.error(`✗ ${img.name}: original not found at ${img.source}`);
    process.exitCode = 1;
    continue;
  }
  const meta = await sharp(src).rotate().metadata();
  // .rotate() honours the camera's orientation; swap sides for portrait shots.
  const swap = meta.orientation && meta.orientation >= 5;
  const width = swap ? meta.height : meta.width;
  const height = swap ? meta.width : meta.height;
  const widths = [...WIDTHS.filter((w) => w < width), Math.min(width, WIDTHS.at(-1))];

  for (const w of widths) {
    const out = path.join(outDir, `${img.name}-${w}.webp`);
    if (!isStale(out, src)) continue;
    await sharp(src).rotate().resize({ width: w }).webp({ quality: QUALITY }).toFile(out);
    made++;
  }
  sizes[img.name] = { widths, width: widths.at(-1), height: Math.round((height * widths.at(-1)) / width) };
}

// Social sharing preview (Facebook, WhatsApp, LinkedIn): 1200 × 630 JPEG of the home hero photo.
const heroSrc = images.find((i) => i.name === home.hero.image);
if (heroSrc) {
  const src = path.join(root, heroSrc.source);
  const out = path.join(root, 'public', site.seo.ogImage);
  if (fs.existsSync(src) && isStale(out, src)) {
    await sharp(src).rotate().resize(1200, 630, { fit: 'cover' }).jpeg({ quality: 80, mozjpeg: true }).toFile(out);
    made++;
  }
}

fs.writeFileSync(sizesPath, JSON.stringify(sizes, null, 2) + '\n');
console.log(`Images: ${images.length} photos, ${made} file(s) written to public/images/`);
