# Thorpe Timbers website

The marketing website for Thorpe Timbers, a family-owned sawmill
in Ngome, KwaZulu-Natal. It is a small, fast, static site: four pages (Home, About,
Products, Contact), plus a thank-you page for the enquiry form and a photo credits page.

It is built with [Astro](https://astro.build) and [Tailwind CSS](https://tailwindcss.com),
and it is hosted free on [Netlify](https://www.netlify.com). There is no database. All the
text lives in a few plain files you can edit.

---

## Before telling customers about the site

The site is currently a **preview**:

- [ ] Replace the 7 stock photos (see `IMAGES.md`). They were downloaded from stock
      sites and are not licensed for use on a live business website.
- [ ] Fill in the remaining `[PLACEHOLDER: ...]` items (`npm run placeholders`).
- [ ] Set `"hideFromSearchEngines": false` in `src/data/site.json`. While it is `true`,
      every page asks Google not to list it.
- [ ] Connect `thorpetimbers.co.za` (section 5) and turn on form emails (section 4).

---

## 1. Changing the words, products and contact details

Edit these files. You do not need to touch any layout code.

| What | File |
| --- | --- |
| Company name, phone, email, WhatsApp, address, trading hours, map, logo | `src/data/site.json` |
| Home page: hero headline and buttons, intro, the 4 trust points | `src/data/home.json` |
| About page: values, timeline, "Thorpe Timbers today" | `src/data/about.json` |
| About page: family story (normal paragraphs) | `src/content/family-story.md` |
| Products: names, descriptions, applications, sizes, photos | `src/data/products.json` |
| Which photo is which, and its description for screen readers | `src/data/images.json` |
| Photo credits | `IMAGES.md` |

Tips for the `.json` files:

- Only change the text **between the quotes** on the right-hand side, e.g.
  `"phoneDisplay": "082 703 7179"`.
- Keep the commas and brackets exactly as they are. If the site stops building, a
  missing comma or quote is the usual cause. Paste the file into
  <https://jsonlint.com> to find the line.
- Lines starting with `"_help"` are notes for you; the website ignores them.
- Anything still written as `[PLACEHOLDER: ...]` shows up **highlighted in yellow** on the
  website so it can't be missed. To list every one that's left, run
  `npm run placeholders` (see section 3), or search the files for `PLACEHOLDER`.

You can edit these files straight on GitHub: open the file, click the pencil icon, make
the change and click "Commit changes". Netlify rebuilds the site by itself within a
couple of minutes.

### Adding a certification badge (CCA poles)

Only once the poles are certified, set `"certificationBadge": "Certified to SANS 457-3"`
on the CCA Treated Poles entry in `src/data/products.json`. While it is empty, no badge
is shown.

### Using a logo file instead of the text wordmark

Put the logo in `public/images/` (SVG or PNG, about 80 px tall) and set
`"logo": "/images/your-logo.svg"` in `src/data/site.json`.

### Google Maps

When you have the real map: Google Maps → find the Thorpe Timbers listing → **Share** →
**Embed a map** → copy only the address inside `src="..."` and paste it into
`"embedUrl"` in `src/data/site.json`. Until then, the map searches for
"Thorpe Timbers, Ngome, KwaZulu-Natal".

---

## 2. Changing a photo

1. Put the original photo (JPG, PNG, HEIC/AVIF or WebP; the bigger the better) in
   `my-photos/`. Originals are never changed.
2. In `src/data/images.json`, either point an existing entry's `"source"` at your new file,
   or add a new entry with a short descriptive `"name"` (lower case, dashes, e.g.
   `"cca-treated-poles-stack"`) and a one-sentence `"alt"` description of what the photo
   shows.
3. To use a new photo on a product, put its name in that product's `"image"` in
   `src/data/products.json` (`""` shows the "Photo coming soon" panel).
4. Update `IMAGES.md` (it feeds the Photo credits page).

The resized WebP versions in `public/images/` are made automatically on every build
(or by running `npm run images`). Recommended sizes for each slot are listed in
`IMAGES.md`.

---

## 3. Running the site on your own computer (optional)

You only need this if you want to preview changes before publishing.

1. Install **Node.js 22 (LTS)** from <https://nodejs.org>.
2. Open a terminal (Mac: Terminal; Windows: PowerShell) in this `website` folder.
3. The first time only, run:

   ```
   npm install
   ```

4. Start a preview:

   ```
   npm run dev
   ```

   Open <http://localhost:4321> in your browser. It updates as you save files. Press
   `Ctrl + C` in the terminal to stop.

Other commands:

| Command | What it does |
| --- | --- |
| `npm run build` | Builds the finished site into the `dist/` folder (this is what Netlify runs) |
| `npm run preview` | Shows the built `dist/` site at <http://localhost:4321> |
| `npm run images` | Re-makes the resized WebP photos from `my-photos/` |
| `npm run placeholders` | Lists every `[PLACEHOLDER: ...]` still to fill in |

The enquiry form only sends messages once the site is on Netlify; on your own computer
it just goes to the thank-you page.

---

## 4. Publishing on Netlify (free `*.netlify.app` address)

One-time setup:

1. Create a free account at <https://app.netlify.com/signup> (sign up with GitHub).
2. Click **Add new site → Import an existing project → GitHub**, and choose this
   repository.
3. Netlify reads the settings from `netlify.toml` at the top of the repository (the site
   is in the `website` folder, build command `npm run build`, publish folder `dist`).
   Just click **Deploy**.
4. Under **Site configuration → Change site name**, choose `thorpetimbers`, so the
   preview address is `https://thorpetimbers.netlify.app`.

`"siteUrl"` in `src/data/site.json` is already set to `https://thorpetimbers.co.za`, the
address the site will have once the domain is connected (section 5). Google and link
previews use it.

After that, every change committed to the repository's main branch publishes itself.

### Enquiry form emails

Netlify picks up the enquiry form automatically on the first deploy. To get each enquiry
by email:

1. In Netlify, open the site → **Forms** → enable form detection if asked, then
   redeploy once.
2. **Site configuration → Notifications → Emails and webhooks → Form submission
   notifications → Add notification → Email notification**.
3. Event: *New form submission*; form: **enquiry**; email: `clem@lowveldlumber.com`.

All submissions are also kept under **Forms → enquiry** in Netlify. Spam is filtered
with a hidden "honeypot" field and Netlify's own spam filter. The free plan includes
100 submissions a month.

---

## 5. Connecting a `.co.za` domain later

1. Register `thorpetimbers.co.za` with any South African registrar
   (e.g. Domains.co.za, Afrihost, Xneelo).
2. In Netlify: **Domain management → Add a domain** → type the domain → **Verify**.
3. Netlify shows the DNS records to add. Either:
   - **Easiest:** change the domain's *nameservers* at your registrar to the four Netlify
     nameservers shown, **or**
   - keep your registrar's DNS and add the records Netlify lists (an `A` record for the
     bare domain and a `CNAME` for `www` pointing to `thorpe-timbers.netlify.app`).
     Keep any existing email (`MX`) records if you use email on that domain.
4. Wait for DNS to update (minutes to a day). Netlify then adds a free HTTPS certificate
   by itself.
5. In Netlify, make `thorpetimbers.co.za` the **primary domain** (it then redirects
   `www.` and the `.netlify.app` address to it). `"siteUrl"` in `src/data/site.json`
   already matches; change it only if you choose `www.thorpetimbers.co.za` as primary.
6. Optional: add the site to [Google Search Console](https://search.google.com/search-console)
   and submit `https://your-domain/sitemap.xml`, and link the website from the Google
   Business Profile.

---

## How it is put together (for a developer)

- `src/pages/`: one file per page; `robots.txt.ts` generates robots.txt; the sitemap
  comes from `@astrojs/sitemap` (`/sitemap.xml` redirects to `/sitemap-index.xml`).
- `src/layouts/BaseLayout.astro`: `<head>`, SEO/Open Graph tags, LocalBusiness JSON-LD,
  header, footer, floating WhatsApp button.
- `src/components/`: header, footer, product card, photo (`<img srcset>` from the
  generated sizes), icons (Lucide + Simple Icons, inlined at build time, no runtime JS).
- `src/lib/site.ts`: contact links, image lookup, placeholder highlighting.
- `scripts/optimise-images.mjs`: sharp → WebP at 400/640/960/1280/1600/1920 px (capped at
  the original's width), `src/data/image-sizes.json`, and the 1200 × 630 `og-image.jpg`.
- Fonts (Fraunces, Inter) are self-hosted through Fontsource; no third-party requests
  except the lazy-loaded Google Map on the Contact page.
- The only client-side JavaScript is the mobile menu toggle and the product pre-select on
  the Contact form.
