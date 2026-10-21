"""Animated GIF of the world map, drawn with Pillow.

Kaleido (plotly's static exporter) needs a full Chrome with system libraries,
so the GIF is rendered here instead: Natural Earth 1:50m country polygons, the
Natural Earth projection, and one frame per year on a fixed colour scale.
"""

import io
import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

GEOJSON = Path(__file__).resolve().parent / "assets" / "ne_50m_admin_0_countries.geojson"

# Natural Earth uses KOS; Wikidata's ISO code for Kosovo is XKS.
ISO_ALIASES = {"KOS": "XKS"}

SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
NO_DATA = "#e9e8e4"
BORDER = "#fcfcfb"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"

W, H = 1100, 620
TINY_AREA = 40  # square pixels
MAP_TOP, MAP_H = 70, 470


def natural_earth(lon, lat):
    """Natural Earth projection (Šavrič et al. 2011), radians in, unit plane out."""
    p2 = lat * lat
    p4 = p2 * p2
    x = lon * (0.8707 - 0.131979 * p2 + p4 * (-0.013791 + p4 * (0.003971 * p2 - 0.001529 * p4)))
    y = lat * (1.007226 + p2 * (0.015085 + p4 * (-0.044475 + 0.028874 * p2 - 0.005916 * p4)))
    return x, y


@lru_cache(maxsize=1)
def projected_polygons():
    """[(iso3, [ring pixel arrays])] for every country except Antarctica."""
    features = json.loads(GEOJSON.read_text(encoding="utf-8"))["features"]
    x_max, _ = natural_earth(math.pi, 0.0)
    _, y_max = natural_earth(0.0, math.radians(84))
    _, y_min = natural_earth(0.0, math.radians(-58))
    scale = min((W - 40) / (2 * x_max), MAP_H / (y_max - y_min))
    x0 = W / 2
    out = []
    for f in features:
        p = f["properties"]
        if p.get("ADM0_A3") == "ATA":
            continue
        iso = p["ISO_A3_EH"] if p["ISO_A3_EH"] != "-99" else p["ADM0_A3"]
        iso = ISO_ALIASES.get(iso, iso)
        geom = f["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        rings = []
        for poly in polys:
            ring = np.radians(np.asarray(poly[0], dtype=float))
            x, y = natural_earth(ring[:, 0], ring[:, 1])
            px = x0 + x * scale
            py = MAP_TOP + (y_max - y) * scale
            rings.append(np.column_stack([px, py]).ravel().tolist())
        area = sum(abs(np.dot(r[0::2], np.roll(r[1::2], 1)) - np.dot(r[1::2], np.roll(r[0::2], 1))) / 2
                   for r in map(np.asarray, rings))
        biggest = max(rings, key=len)
        centroid = (float(np.mean(biggest[0::2])), float(np.mean(biggest[1::2])))
        out.append((area, iso, rings, centroid))
    # Largest first, so enclaves (Lesotho, San Marino, ...) are drawn on top.
    out.sort(key=lambda t: -t[0])
    return out


def _font(size, bold=False):
    for name in (["DejaVuSans-Bold.ttf"] if bold else []) + ["DejaVuSans.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _color(v, vmax, log):
    if v is None or v <= 0 or np.isnan(v):
        return NO_DATA
    t = math.log10(v + 1) / math.log10(vmax + 1) if log else v / vmax
    idx = min(len(SEQ) - 1, int(max(0.0, min(1.0, t)) * len(SEQ)))
    return SEQ[idx]


def _legend(draw, vmax, log, label, fmt):
    x, y, w, h = 300, MAP_TOP + MAP_H + 25, 500, 12
    step = w / len(SEQ)
    draw.rectangle([x - 110, y, x - 90, y + h], fill=NO_DATA)
    draw.text((x - 85, y - 1), "None", fill=INK2, font=_font(12))
    for i, c in enumerate(SEQ):
        draw.rectangle([x + i * step + 1, y, x + (i + 1) * step - 1, y + h], fill=c)
    for i in range(len(SEQ) + 1):
        t = i / len(SEQ)
        v = (10 ** (t * math.log10(vmax + 1)) - 1) if log else t * vmax
        if i in (0, len(SEQ)) or i % 2 == 0:
            s = fmt(v)
            tw = draw.textlength(s, font=_font(11))
            draw.text((x + i * step - tw / 2, y + h + 4), s, fill=MUTED, font=_font(11))
    draw.text((x + w + 15, y - 1), label + (" (log scale)" if log else ""), fill=INK2, font=_font(12))


def render_gif(frames, vmax, log, label, title, fmt, ms_per_frame=900):
    """frames: [(year, {iso3: value})] -> GIF bytes."""
    polys = projected_polygons()
    images = []
    for year, values in frames:
        img = Image.new("RGB", (W, H), "white")
        draw = ImageDraw.Draw(img)
        for area, iso, rings, _ in polys:
            fill = _color(values.get(iso), vmax, log)
            for ring in rings:
                if len(ring) >= 6:
                    draw.polygon(ring, fill=fill, outline=BORDER)
        # States too small to see (Singapore, Bahrain, Malta, ...) get a dot when they gave.
        for area, iso, rings, (cx, cy) in polys:
            v = values.get(iso)
            if area < TINY_AREA and v and v > 0:
                draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=_color(v, vmax, log), outline=INK2)
        draw.text((24, 18), title, fill=INK, font=_font(20, bold=True))
        draw.text((W - 24 - draw.textlength(str(year), font=_font(34, bold=True)), 12), str(year),
                  fill=INK2, font=_font(34, bold=True))
        _legend(draw, vmax, log, label, fmt)
        draw.text((24, H - 22), "Source: Federal Register foreign gift reports; gifts living-data pipeline.",
                  fill=MUTED, font=_font(11))
        images.append(img.convert("P", palette=Image.ADAPTIVE, colors=64))
    buf = io.BytesIO()
    images[0].save(buf, format="GIF", save_all=True, append_images=images[1:],
                   duration=ms_per_frame, loop=0, optimize=True)
    return buf.getvalue()
