# Images

Every photo on the website, where it is used, where it came from and the size to aim for
when you replace it with a photo of our own mill.

The **Photo credits** page on the website is built from the first table below, so keep
its columns in the same order. To swap a photo, see "Changing a photo" in README.md.

## Photos on the site

| File (in public/images/) | Used on | Source | Photographer / owner | Licence | Recommended size |
| --- | --- | --- | --- | --- | --- |
| log-yard-pine-logs | Home: hero banner; social sharing image | Stock photo, source unknown (original: my-photos/industrial-wood-working-factory-with-tree-trunks-ready-be-cut.jpg.avif) | Unknown | Not licensed: preview only (see note 1) | 1920 × 1080 (landscape, at least 1600 wide) |
| log-loader-at-log-yard | About: top banner | Stock photo, source unknown (original: my-photos/wood-processing-factory.jpg.avif) | Unknown | Not licensed: preview only (see note 1) | 1920 × 800 (wide landscape) |
| bandsaw-breaking-down-log | Home: intro section; Products: top banner | Stock photo, source unknown (original: my-photos/photo-4.jpg) | Unknown | Not licensed: preview only (see note 1) | 1920 × 800 (wide landscape) |
| stacked-sawn-pine-boards | Products and Home: Structural Timber card | Stock photo, source unknown (original: my-photos/photo-1.jpg) | Unknown | Not licensed: preview only (see note 1) | 1200 × 800 (3:2) |
| stacked-select-grade-boards | Products and Home: Furniture Grade Timber card | Stock photo, source unknown (original: my-photos/photo-3.jpg) | Unknown | Not licensed: preview only (see note 1) | 1200 × 800 (3:2) |
| table-saw-cutting-timber | About: family story | Stock photo, source unknown (original: my-photos/photo-2.jpg) | Unknown | Not licensed: preview only (see note 1) | 1200 × 900 (4:3) |
| logs-arriving-by-truck | About: Thorpe Timbers today | Stock photo, source unknown (original: my-photos/photo-5.webp) | Unknown | Not licensed: preview only (see notes 1 and 2) | 1600 × 1000 (16:10) |

### Notes

1. **Preview only: replace before going live.** All seven photos were downloaded from
   stock sites (they look like Freepik / iStock previews), which need a paid licence
   for business use. They are kept only while the site is a private preview, which is
   also why `"hideFromSearchEngines"` is `true` in `src/data/site.json`. Replace each
   with a photo of our own mill or a free Unsplash/Pexels photo (suggestions below),
   then update its row. They are also small (540 to 1000 pixels wide), so the
   full-width banners look a little soft on large screens.
2. The truck photo shows a transport company's name on the trailer. If that is not our
   own haulier, or they would rather not appear, replace it.

No photos were skipped: none of the supplied photos were blurry, badly lit or showed
people's faces clearly.

## Suggested free replacements

### Products with no photo yet

These products currently show a "Photo coming soon" panel. Best option: a photo of our
own product at the mill (1200 × 800, landscape). Stock photos could not be downloaded
from the build environment, so the links below are **suggestions only**. They were
found by search and have not been viewed, so check each one looks right (South African
plantation timber, no snow, no logos, no posed people) before using it.

| Product (image slot) | Suggested stock photo | Site | Photographer |
| --- | --- | --- | --- |
| Pallet Material | Choose from https://www.pexels.com/search/wooden%20pallets/ (a stack of new, unbranded pallet boards or pallets) | Pexels | Shown on the photo page |
| CCA Treated Poles | Choose from https://www.pexels.com/search/wooden%20poles/ (stock photos rarely show green CCA-treated gum poles, so our own photo is strongly recommended) | Pexels | Shown on the photo page |
| Decking | https://unsplash.com/photos/a-wooden-deck-surrounded-by-trees-and-plants-h4r2V9fdf5Q | Unsplash | Shown on the photo page |
| Firewood | https://www.pexels.com/photo/brown-fire-wood-170560/ or https://www.pexels.com/photo/pile-of-firewoods-235964/ | Pexels | Shown on the photo page |
| Sawdust & Shavings | https://unsplash.com/photos/selective-photography-sawdust-on-plank-hdW4rZPHe2g, or choose from https://unsplash.com/s/photos/wood-shavings | Unsplash | Clem Onojeghuo (first link) |

### Replacing the stock photos above

Search these and pick South African-looking plantation scenes (pine/gum, no snow, no
logos, no posed people), landscape, 1920 pixels wide or more:

- Log yard / hero: https://unsplash.com/s/photos/log-yard and https://www.pexels.com/search/sawmill/
- Sawmill machinery: https://unsplash.com/s/photos/sawmill
- Stacked sawn timber: https://www.pexels.com/search/lumber/
- Pine plantation: https://unsplash.com/s/photos/pine-plantation
- Timber truck: https://www.pexels.com/search/logging%20truck/

Download each one, put it in `my-photos/`, point the matching entry in
`src/data/images.json` at it, and update its row in the first table.

Both Unsplash and Pexels allow free commercial use without attribution, but we credit
photographers on the Photo credits page anyway. When you add one of these, move its row
into the first table with the photographer's name and the photo page link.
