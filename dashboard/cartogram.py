"""Contiguous cartogram of giving countries, with flow lines to the United States.

Country areas are resized in proportion to a weight (gifts or value, optionally
logged) with the rubber-sheet algorithm of Dougenik, Chrisman & Niemeyer (1985),
"An Algorithm to Construct Continuous Area Cartograms", Professional Geographer
37(1). Every vertex moves as a function of its position only, so borders shared
by two countries move together and the map stays connected.

Work happens in the Natural Earth projection plane used by gifmap.py.
"""

import json
import math
from functools import lru_cache

import numpy as np

from gifmap import GEOJSON, ISO_ALIASES, natural_earth

HUB = "USA"            # drawn at its true size; every flow line ends here
MIN_RING_AREA = 2e-5   # drop specks (tiny islands) except a country's main ring
MAX_STEP_ERR = 3.0     # cap on per-country size error in the force reduction factor
GRID = 0.004           # vertex snapping grid; the map is about 5.5 units wide


@lru_cache(maxsize=1)
def base_map():
    """Countries in the projected plane: list of dicts with iso, name, rings."""
    features = json.loads(GEOJSON.read_text(encoding="utf-8"))["features"]
    countries = []
    for f in features:
        p = f["properties"]
        if p.get("ADM0_A3") == "ATA":
            continue
        iso = p["ISO_A3_EH"] if p["ISO_A3_EH"] != "-99" else p["ADM0_A3"]
        geom = f["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        rings = []
        for poly in polys:
            lonlat = np.radians(np.asarray(poly[0], dtype=float))
            x, y = natural_earth(lonlat[:, 0], lonlat[:, 1])
            rings.append(_snap(np.column_stack([x, y])))
        areas = [abs(_ring_area(r)) for r in rings]
        main = int(np.argmax(areas))
        rings = [r for i, r in enumerate(rings) if i == main or areas[i] >= MIN_RING_AREA]
        countries.append({"iso": ISO_ALIASES.get(iso, iso), "name": p["NAME"], "rings": rings})
    return countries


def _snap(ring):
    """Snap to a fine grid and drop repeated points.

    Neighbouring countries share border vertices, so they snap to the same points
    and stay contiguous, while dense coastlines lose most of their vertices.
    Rings that would collapse (Bahrain, Singapore, ...) are kept as they are.
    """
    q = np.round(ring / GRID) * GRID
    keep = np.ones(len(q), dtype=bool)
    keep[1:] = np.any(q[1:] != q[:-1], axis=1)
    q = q[keep]
    if len(q) > 1 and np.all(q[0] == q[-1]):
        q = q[:-1]
    orig = ring[:-1]
    if len(q) < 4 or abs(_ring_area(q)) < 0.8 * abs(_ring_area(orig)):
        return orig
    return q


def _ring_area(r):
    x, y = r[:, 0], r[:, 1]
    return 0.5 * (np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _ring_centroid(r):
    x, y = r[:, 0], r[:, 1]
    cross = x * np.roll(y, -1) - np.roll(x, -1) * y
    a = cross.sum() / 2
    if abs(a) < 1e-12:
        return float(x.mean()), float(y.mean()), 0.0
    cx = ((x + np.roll(x, -1)) * cross).sum() / (6 * a)
    cy = ((y + np.roll(y, -1)) * cross).sum() / (6 * a)
    return float(cx), float(cy), abs(float(a))


def transform(values, scale):
    v = np.asarray(values, dtype=float)
    if scale == "Log":
        return np.log10(v + 1)
    if scale == "Square root":
        return np.sqrt(v)
    return v


def build(weights, iterations=40, tol=0.05):
    """Distort the base map so each country's area follows `weights` (iso -> w >= 0).

    The hub keeps its original area; countries without a weight (non-givers)
    get a small floor so they shrink to slivers instead of disappearing.
    Returns (countries with distorted rings, share of area still misallocated).
    """
    countries = base_map()
    # One flat vertex array plus slices back into rings, so each iteration is vectorised.
    pts = np.concatenate([r for c in countries for r in c["rings"]])
    slices, start = [], 0
    for c in countries:
        cs = []
        for r in c["rings"]:
            cs.append((start, start + len(r)))
            start += len(r)
        slices.append(cs)

    w = np.array([weights.get(c["iso"], 0.0) for c in countries], dtype=float)
    positive = w[w > 0]
    floor = 0.05 * positive.min() if len(positive) else 1.0
    w = np.where(w > 0, w, floor)
    hub = np.array([c["iso"] == HUB for c in countries])

    # Index of each vertex's successor within its own ring, for the shoelace sums.
    ring_bounds = [ab for cs in slices for ab in cs]
    ring_country = np.repeat(np.arange(len(countries)), [len(cs) for cs in slices])
    starts = np.array([a for a, _ in ring_bounds])
    nxt = np.arange(len(pts)) + 1
    for a, b in ring_bounds:
        nxt[b - 1] = a
    n = len(countries)

    def measure(p):
        x, y = p[:, 0], p[:, 1]
        cross = x * y[nxt] - x[nxt] * y
        a_r = np.add.reduceat(cross, starts) / 2
        a_r = np.where(np.abs(a_r) < 1e-15, 1e-15, a_r)
        cx_r = np.add.reduceat((x + x[nxt]) * cross, starts) / (6 * a_r)
        cy_r = np.add.reduceat((y + y[nxt]) * cross, starts) / (6 * a_r)
        w_r = np.abs(a_r)
        area = np.bincount(ring_country, w_r, n)
        cx = np.bincount(ring_country, cx_r * w_r, n) / area
        cy = np.bincount(ring_country, cy_r * w_r, n) / area
        return cx, cy, area

    _, _, area0 = measure(pts)
    area0 = np.maximum(area0, 1e-7)
    total = area0.sum()
    desired = np.empty(len(countries))
    hub_area = area0[hub].sum()
    desired[hub] = area0[hub]
    desired[~hub] = (total - hub_area) * w[~hub] / w[~hub].sum()

    err = np.inf
    for _ in range(iterations):
        cx, cy, area = measure(pts)
        area = np.maximum(area, 1e-7)
        # Convergence is judged on the share of map area that is misallocated;
        # the plain mean ratio is dominated by slivers and never settles.
        err = float(np.abs(area - desired).sum() / desired.sum())
        if err < tol:
            break
        # Dougenik's force reduction uses the mean size error. Capping each country's
        # error keeps near-zero targets from shrinking every step to nothing.
        size_err = np.minimum(np.maximum(area, desired) / np.minimum(area, desired), MAX_STEP_ERR)
        reduction = 1.0 / (1.0 + float(size_err.mean()))
        radius = np.sqrt(area / math.pi)
        mass = np.sqrt(desired / math.pi) - radius
        active = np.flatnonzero(np.abs(mass) > 1e-9)
        # All country forces on all vertices at once: (countries x vertices), float32.
        P = pts.astype(np.float32)
        dx = P[None, :, 0] - cx[active, None].astype(np.float32)
        dy = P[None, :, 1] - cy[active, None].astype(np.float32)
        d = np.maximum(np.hypot(dx, dy), np.float32(1e-9))
        r = radius[active, None].astype(np.float32)
        m = mass[active, None].astype(np.float32)
        ratio = d / r
        force = np.where(ratio > 1, m / ratio, m * ratio * ratio * (4 - 3 * ratio)) / d
        shift = np.column_stack([(force * dx).sum(axis=0), (force * dy).sum(axis=0)])
        pts = pts + reduction * shift.astype(float)

    out = []
    for c, cs in zip(countries, slices):
        out.append({"iso": c["iso"], "name": c["name"], "rings": [pts[a:b] for a, b in cs]})
    return out, err


def anchor(country):
    """Label/flow anchor: centroid of the country's largest ring."""
    best = max((_ring_centroid(r) for r in country["rings"]), key=lambda t: t[2])
    return best[0], best[1]
