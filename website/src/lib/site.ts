import site from '../data/site.json';
import imageList from '../data/images.json';
import imageSizes from '../data/image-sizes.json';

export { site };

const c = site.contact;
export const links = {
  tel: `tel:${c.phoneInternational}`,
  mailto: `mailto:${c.email}`,
  whatsapp: `https://wa.me/${c.whatsappNumber}?text=${encodeURIComponent(c.whatsappMessage)}`,
  mapEmbed:
    site.map.embedUrl ||
    `https://www.google.com/maps?q=${encodeURIComponent(site.map.query)}&output=embed`,
  directions: `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(site.map.query)}`,
};

export const nav = [
  { label: 'Home', href: '/' },
  { label: 'About', href: '/about/' },
  { label: 'Products', href: '/products/' },
  { label: 'Contact', href: '/contact/' },
];

const PLACEHOLDER = /\[PLACEHOLDER[^\]]*\]/g;

export const isPlaceholder = (s: string) => /\[PLACEHOLDER/.test(s);

const escape = (s: string) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

/** Escapes text for HTML and highlights any [PLACEHOLDER: ...] still waiting for real content. */
export function formatText(s: string) {
  return escape(s).replace(PLACEHOLDER, (m) => `<em class="placeholder">${m}</em>`);
}

type Sized = { widths: number[]; width: number; height: number };

export function getImage(name: string) {
  if (!name) return undefined;
  const entry = imageList.images.find((i) => i.name === name);
  const sizes = (imageSizes as Record<string, Sized>)[name];
  if (!entry || !sizes) throw new Error(`Image "${name}" is not in images.json, or "npm run images" has not been run.`);
  return {
    alt: entry.alt,
    src: `/images/${name}-${sizes.width}.webp`,
    srcset: sizes.widths.map((w) => `/images/${name}-${w}.webp ${w}w`).join(', '),
    width: sizes.width,
    height: sizes.height,
  };
}
