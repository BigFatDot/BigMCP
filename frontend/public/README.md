# Frontend Public Assets

This directory contains static assets served directly by the frontend.

## Favicon Files

Currently available:
- `bigmcp-favicon.svg` - SVG favicon (source from `/assets/logos/`)
- `favicon-32x32.png` - 32x32px PNG favicon (source from `/assets/logos/bigmcp-favicon.png`)

### Additional sizes needed (optional)

To generate additional favicon sizes for better cross-browser support:

```bash
# Using ImageMagick or similar tool
magick bigmcp-favicon.png -resize 16x16 favicon-16x16.png
magick bigmcp-favicon.png -resize 180x180 apple-touch-icon.png
```

Or use an online favicon generator like [favicon.io](https://favicon.io/) with the source PNG.

## Logo Files

To add the full BigMCP logo to the frontend, copy from `/assets/logos/`:
- `bigmcp-logo.svg` - Full logo with text
- `bigmcp-logo-dark.svg` - Dark theme variant
- `bigmcp-logo-animated.svg` - Animated version
