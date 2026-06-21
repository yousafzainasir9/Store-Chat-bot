# TrendEvoker — brand guide

The visual identity applied across the chatbot widget and (optionally) the admin
dashboard and storefront. The source of truth for colors is
[`assets/brand/brand-tokens.css`](../assets/brand/brand-tokens.css); the logo is
[`assets/brand/trendevoker-logo.svg`](../assets/brand/trendevoker-logo.svg).

## Palette

| Token | Hex | Use |
|---|---|---|
| Burgundy (primary) | `#8C1D2C` | Script, hat, widget header, primary buttons, prices |
| Burgundy dark | `#6F1622` | Hover states, header gradient end |
| Gold (accent) | `#E0B43C` | Earrings, highlights, header accent rule |
| Gold dark | `#C79A2A` | Gold hover |
| Cream | `#F6EFD8` | Soft backgrounds, the face "halo", assistant chat bubbles |
| Ink | `#2A1216` | Body text on light surfaces |

> **Accessibility:** gold (`#E0B43C`) does not meet WCAG AA for small text on
> white, so it's used only for **decorative** elements (rules, dots, borders),
> never for body copy. Text links and prices use burgundy, which passes.

## Logo

`assets/brand/trendevoker-logo.svg` is a scalable (vector) recreation of the
wordmark — the wide-brim hat, cherry-gold drop earrings, lips, and "TrendEvoker"
script. It scales to any size without blur.

> Note: this SVG is a faithful **recreation** in brand colors, not the original
> uploaded PNG (that file wasn't available to embed). If you have the original
> artwork, drop it next to this file as `trendevoker-logo.png` and reference it
> where a raster version is needed (e.g. Shopify store logo, favicon, social
> share images).

A simplified one-color **mark** (hat + two gold earring dots) is embedded inline
in the chat widget header — see `widget/src/Widget.tsx`.

## Where it's applied

- **Chat widget** (`widget/src/`): burgundy header with a gold accent rule and
  the brand mark, cream assistant bubbles, burgundy launcher and send button.
  Defaults live in `config.ts` / `styles.css`; a merchant can still override the
  primary color from the admin (served via `/widget/config`).
- **Backend defaults**: `STORE_NAME` defaults to `TrendEvoker` and the served
  widget `primary_color` defaults to burgundy.

## Applying it elsewhere (not yet done)

- **Shopify store**: rename the dev store to *TrendEvoker* and upload the logo
  under *Online Store → Themes → Customize → Logo* (plus *Settings → Favicon*).
- **Admin dashboard** (`admin/src/styles.css`): swap `--primary: #1f6feb` for
  `--te-burgundy` and add the logo to the sidebar header.
