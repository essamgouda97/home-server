#!/usr/bin/env python3
"""Convert one owner-selected HEIC/HEIF photo to a bounded JPEG MCP preview."""
from pathlib import Path
import sys
from PIL import Image
from pillow_heif import register_heif_opener

if len(sys.argv) != 2:
    raise SystemExit('one image path required')
register_heif_opener()
Image.MAX_IMAGE_PIXELS = 50_000_000
with Image.open(Path(sys.argv[1])) as original:
    original.thumbnail((1800, 1800))
    preview = original.convert('RGB')
    preview.save(sys.stdout.buffer, format='JPEG', quality=82)
