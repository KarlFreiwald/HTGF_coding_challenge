# HTGF UI style reference

## Project rule

All visual UI decisions must follow HTGF's website palette and visual direction.
This applies to current and future pages, controls, typography, spacing, states,
and any illustrations. Reuse the CSS variables in `app/static/styles.css` rather
than adding unrelated colors or a separate component theme.

Reference: [HTGF website](https://www.htgf.de/), inspected on 18 November 2026.
This is an implementation reference derived from the public website, not an
official brand manual.

## Observed theme palette

| Website token | Color | Our use |
| --- | --- | --- |
| `contrast` | `#000000` | Primary text and buttons |
| `base` | `#FFFFFF` | Surfaces and text on dark buttons |
| `fond` / `accent-1` | `#F0EEEB` | Page background |
| `accent-2` | `#F7F6F5` | Optional lighter neutral surface |
| `fond-dark` | `#221F19` | Secondary text |
| `grey` | `#D9D4CC` | Dividers and borders |
| `berry` | `#FA6446` | Coral accents and error-state markers |
| `lime` | `#D9D464` | Highlight and button-hover accent |
| `mint` | `#64C2C8` | Positive/status accents |
| `wcag--outline-color` | `#F5653F` | Focus accent, paired with a black outline |

The palette values come from HTGF's custom theme and inline styles. Generic
WordPress preset colors are not treated as HTGF brand colors.

## Visual direction

- Warm neutral backgrounds, black text, generous whitespace, and clear hierarchy.
- Large headings with selected editorial serif emphasis, alongside geometric
  sans-serif interface text.
- Rounded pill buttons, clear borders, and restrained use of colorful accents.
- The website uses gradient artwork. Our small CSS gradient uses the observed
  coral/lime/mint palette; it is an approximation, not the original artwork.
- Keep normal text dark on light surfaces. Bright accents primarily decorate
  backgrounds and state markers; they are not substitutes for readable text.
- Communicate status in words as well as color and preserve visible keyboard focus.
- Keep the page usable on narrow screens and retain the coding-challenge context.

The website declares **ITC Avant Garde Gothic** and **ES Face** fonts. This project
currently uses local geometric-sans and Georgia fallbacks, so typography is an
approximation. No font files, logos, or website artwork are bundled or hotlinked.
If exact typography or assets are desired later, select them together and check
their availability and usage terms before adding them.

## Sources

On 23 November 2026 we checked the desktop header's **Mein Pitch** control in Chrome.
At rest its fill is transparent with a black inset outline. Hovering the wrapper
reveals HTGF's gradient image on the link's overlay at 60% opacity. The prototype
uses a white pill and a locally defined pastel gradient on hover and keyboard focus.
The link leads to the [pitch-deck intake](https://www.htgf.de/pitch-deck-upload/).

- [HTGF homepage and inline theme presets](https://www.htgf.de/)
- [HTGF theme stylesheet](https://www.htgf.de/wp-content/themes/htgf/assets/css/theme.css?ver=6.3.59)
- [HTGF button stylesheet](https://www.htgf.de/wp-content/themes/htgf/assets/css/blocks-overwrites/core-buttons.css?ver=6.3.59)
