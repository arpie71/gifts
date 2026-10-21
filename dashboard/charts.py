"""Plotly figure builders for the gifts dashboard."""

import math

import networkx as nx
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from data import fmt_metric, fmt_money

BLUE, ORANGE = "#2a78d6", "#eb6834"
SEQ_SCALE = [[0.0, "#cde2fb"], [0.25, "#86b6ef"], [0.5, "#3987e5"], [0.75, "#1c5cab"], [1.0, "#0d366b"]]
HEAT_SCALE = [[0.0, "#f4f8fd"], [0.15, "#cde2fb"], [0.4, "#86b6ef"], [0.65, "#3987e5"],
              [0.85, "#1c5cab"], [1.0, "#0d366b"]]
LAND, GRID = "#e9e8e4", "#e1e0d9"

METRIC_LABEL = {"n": "Gifts", "value": "Value ($)"}


def _log_ticks(vmax):
    """Tick values/labels for a log10(v+1) colour axis."""
    ticks = [0] + [10 ** k for k in range(0, int(math.log10(max(vmax, 1))) + 1)]
    return [math.log10(t + 1) for t in ticks], [fmt_money(t) for t in ticks]


def _colorbar(metric, log, vmax):
    cb = dict(title=METRIC_LABEL[metric], thickness=12, len=0.6, outlinewidth=0)
    if log:
        tv, tt = _log_ticks(vmax)
        cb.update(tickvals=tv, ticktext=tt)
    return cb


def _z(values, log):
    v = np.asarray(values, dtype=float)
    return np.log10(v + 1) if log else v


def _geo():
    return dict(showframe=False, showcoastlines=False, projection_type="natural earth",
                showland=True, landcolor=LAND, showcountries=True, countrycolor="white",
                resolution=50, lataxis_range=[-58, 85], bgcolor="rgba(0,0,0,0)")


def _hover(df, metric):
    return [f"<b>{c}</b><br>Gifts: {n:,}<br>Value: {fmt_money(v)}<br>US recipients: {r:,}"
            for c, n, v, r in zip(df.giver_country, df.n, df.value, df.recipients)]


def world_map(df, metric, log, title):
    """Static choropleth from a country table with n / value / recipients."""
    d = df[df[metric] > 0]
    vmax = float(d[metric].max()) if len(d) else 1.0
    fig = go.Figure(go.Choropleth(
        locations=d.giver_iso3, locationmode="ISO-3", z=_z(d[metric], log),
        zmin=0, zmax=_z([vmax], log)[0], colorscale=SEQ_SCALE, marker_line_color="white",
        marker_line_width=0.4, text=_hover(d, metric), hoverinfo="text",
        colorbar=_colorbar(metric, log, vmax)))
    fig.update_layout(geo=_geo(), title=title, height=560, margin=dict(l=0, r=0, t=50, b=0))
    return fig


def animated_map(cy, metric, log, years, title):
    """Choropleth with one frame per year on a fixed colour scale."""
    vmax = float(cy[metric].max()) if len(cy) else 1.0
    zmax = _z([vmax], log)[0]

    def trace(y):
        d = cy[(cy.yr == y) & (cy[metric] > 0)]
        return go.Choropleth(locations=d.giver_iso3, locationmode="ISO-3", z=_z(d[metric], log),
                             zmin=0, zmax=zmax, colorscale=SEQ_SCALE, marker_line_color="white",
                             marker_line_width=0.4, text=_hover(d, metric), hoverinfo="text",
                             colorbar=_colorbar(metric, log, vmax))

    years = list(range(years[0], years[1] + 1))
    fig = go.Figure(data=[trace(years[0])],
                    frames=[go.Frame(data=[trace(y)], name=str(y)) for y in years])
    steps = [dict(method="animate", label=str(y),
                  args=[[str(y)], dict(mode="immediate", frame=dict(duration=0, redraw=True),
                                       transition=dict(duration=0))]) for y in years]
    fig.update_layout(
        geo=_geo(), title=title, height=600, margin=dict(l=0, r=0, t=50, b=0),
        updatemenus=[dict(type="buttons", showactive=False, x=0.02, y=0.06, xanchor="left",
                          buttons=[dict(label="▶ Play", method="animate",
                                        args=[None, dict(frame=dict(duration=900, redraw=True),
                                                         fromcurrent=True, transition=dict(duration=0))]),
                                   dict(label="❚❚ Pause", method="animate",
                                        args=[[None], dict(mode="immediate", frame=dict(duration=0))])])],
        sliders=[dict(active=0, steps=steps, x=0.15, len=0.83, y=0.06,
                      currentvalue=dict(prefix="Year: ", font=dict(size=14)))])
    return fig


def heatmap(mat, metric, log, title):
    """Countries (rows) x years (cols)."""
    z = _z(mat.values, log)
    text = [[fmt_metric(v, metric) if v > 0 else "" for v in row] for row in mat.values]
    fig = go.Figure(go.Heatmap(
        z=z, x=[str(c) for c in mat.columns], y=list(mat.index), colorscale=HEAT_SCALE,
        zmin=0, text=text, texttemplate="%{text}" if metric == "n" else None,
        textfont=dict(size=10), xgap=2, ygap=2,
        customdata=[[fmt_metric(v, metric) for v in row] for row in mat.values],
        hovertemplate="%{y}, %{x}: %{customdata}<extra></extra>",
        colorbar=_colorbar(metric, log, float(mat.values.max()) if mat.size else 1.0)))
    fig.update_layout(title=title, height=110 + 42 * len(mat), margin=dict(l=10, r=10, t=50, b=10),
                      yaxis=dict(autorange="reversed"), xaxis=dict(side="top", type="category"))
    return fig


def hbar(labels, values, metric, title, height=None):
    fig = go.Figure(go.Bar(x=values, y=labels, orientation="h", marker_color=BLUE,
                           text=[fmt_metric(v, metric) for v in values], textposition="outside",
                           cliponaxis=False, hovertemplate="%{y}: %{text}<extra></extra>"))
    fig.update_layout(title=title, height=height or 120 + 26 * len(labels),
                      margin=dict(l=10, r=60, t=50, b=10), yaxis=dict(autorange="reversed"),
                      xaxis=dict(showgrid=True, gridcolor=GRID, title=METRIC_LABEL[metric]),
                      bargap=0.35)
    return fig


def columns_by_year(series, metric, title):
    fig = go.Figure(go.Bar(x=series.index, y=series.values, marker_color=BLUE,
                           customdata=[fmt_metric(v, metric) for v in series.values],
                           hovertemplate="%{x}: %{customdata}<extra></extra>"))
    fig.update_layout(title=title, height=320, margin=dict(l=10, r=10, t=50, b=10),
                      yaxis=dict(title=METRIC_LABEL[metric], gridcolor=GRID), bargap=0.3,
                      xaxis=dict(dtick=2))
    return fig


def role_branch(t, normalize, title):
    text = [[(f"{v:.0f}%" if normalize else f"{v:,.0f}") for v in row] for row in t.values]
    fig = go.Figure(go.Heatmap(
        z=t.values, x=list(t.columns), y=list(t.index), colorscale=HEAT_SCALE, zmin=0,
        text=text, texttemplate="%{text}", textfont=dict(size=11), xgap=2, ygap=2,
        hovertemplate="%{y} ← %{x}: %{text}<extra></extra>",
        colorbar=dict(title="% of row" if normalize else "Gifts", thickness=12, outlinewidth=0)))
    fig.update_layout(title=title, height=420, margin=dict(l=10, r=10, t=80, b=10),
                      yaxis=dict(autorange="reversed"), xaxis=dict(side="top"))
    return fig


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------
def ring_layout(G, strength):
    """U.S. nodes on an inner ring, countries on an outer ring near their main U.S. partners."""
    us = sorted((v for v in G if v[0] == "u"), key=strength.get, reverse=True)
    countries = [v for v in G if v[0] == "c"]
    pos = {}
    r_in = 0.0 if len(us) == 1 else min(0.7, 0.3 + 0.01 * len(us))
    for i, v in enumerate(us):
        a = 2 * math.pi * i / len(us)
        pos[v] = (r_in * math.cos(a), r_in * math.sin(a))
    # Each country's preferred angle is the weighted circular mean of its partners' angles;
    # countries are then spaced evenly in that order so labels do not collide.
    pref = {}
    for c in countries:
        sx = sy = 0.0
        for u in G[c]:
            w = G[c][u]["weight"]
            sx += w * pos[u][0]
            sy += w * pos[u][1]
        pref[c] = math.atan2(sy, sx) if (sx or sy) else 0.0
    order = sorted(countries, key=pref.get)
    for i, c in enumerate(order):
        a = 2 * math.pi * i / len(order) + (pref[order[0]] if order else 0)
        pos[c] = (math.cos(a), math.sin(a))
    return pos


def network(edges, metric, us_title, layout="Rings", n_labels=40, seed=7):
    """Bipartite country <-> US network. Node size and edge width scale with the metric."""
    if edges.empty:
        return go.Figure().update_layout(title="No edges match these filters", height=300)
    G = nx.Graph()
    for r in edges.itertuples(index=False):
        c, u = ("c", r.giver_country), ("u", r.us)
        G.add_node(c, label=r.giver_country, side="Giving country")
        G.add_node(u, label=r.us_label, side=us_title)
        G.add_edge(c, u, weight=float(getattr(r, metric)), n=r.n, value=r.value)

    strength = dict(G.degree(weight="weight"))
    smax = max(strength.values()) or 1.0
    if layout == "Rings":
        pos = ring_layout(G, strength)
    else:
        # Spring layout on sqrt weights keeps heavy ties close without collapsing the rest.
        for a, b, d in G.edges(data=True):
            d["w_layout"] = math.sqrt(d["weight"] / smax) + 0.05
        pos = nx.spring_layout(G, weight="w_layout", seed=seed,
                               k=2.5 / math.sqrt(G.number_of_nodes()), iterations=300)

    wmax = max(d["weight"] for _, _, d in G.edges(data=True)) or 1.0
    traces = []
    # Plotly lines have one width per trace, so edges are binned into width classes.
    bins = [(0.0, 0.1, 0.6), (0.1, 0.3, 1.6), (0.3, 0.6, 3.0), (0.6, 1.01, 5.0)]
    for lo, hi, width in bins:
        xs, ys = [], []
        for a, b, d in G.edges(data=True):
            f = d["weight"] / wmax
            if lo <= f < hi:
                xs += [pos[a][0], pos[b][0], None]
                ys += [pos[a][1], pos[b][1], None]
        if xs:
            traces.append(go.Scatter(x=xs, y=ys, mode="lines", hoverinfo="skip", showlegend=False,
                                     line=dict(width=width, color="rgba(137,135,129,0.45)")))
    # Invisible midpoints carry the edge hover text.
    mx, my, mt = [], [], []
    for a, b, d in G.edges(data=True):
        mx.append((pos[a][0] + pos[b][0]) / 2)
        my.append((pos[a][1] + pos[b][1]) / 2)
        mt.append(f"{G.nodes[a]['label']} → {G.nodes[b]['label']}<br>Gifts: {d['n']:,}<br>"
                  f"Value: {fmt_money(d['value'])}")
    traces.append(go.Scatter(x=mx, y=my, mode="markers", marker=dict(size=10, opacity=0),
                             text=mt, hoverinfo="text", showlegend=False))

    for side, color, symbol in [("Giving country", BLUE, "circle"), (us_title, ORANGE, "diamond")]:
        nodes = [v for v in G.nodes if G.nodes[v]["side"] == side]
        # Sizes are relative within each side, so countries are comparable to each other
        # rather than all dwarfed by the largest U.S. hub.
        side_max = max(strength[v] for v in nodes) or 1.0
        sizes = [10 + 40 * math.sqrt(strength[v] / side_max) for v in nodes]
        # Crowded inner rings only label their largest nodes; hover shows the rest.
        n_lab = n_labels if side == "Giving country" or len(nodes) <= 20 else 15
        top = set(sorted(nodes, key=strength.get, reverse=True)[:n_lab])
        if layout == "Rings" and side == "Giving country":
            where = ["middle right" if pos[v][0] >= 0 else "middle left" for v in nodes]
        else:
            where = "top center"
        traces.append(go.Scatter(
            x=[pos[v][0] for v in nodes], y=[pos[v][1] for v in nodes], mode="markers+text",
            name=side, marker=dict(size=sizes, color=color, symbol=symbol,
                                   line=dict(width=2, color="white")),
            text=[G.nodes[v]["label"] if v in top else "" for v in nodes],
            textposition=where, textfont=dict(size=11),
            hovertext=[f"<b>{G.nodes[v]['label']}</b><br>{METRIC_LABEL[metric]}: "
                       f"{fmt_metric(strength[v], metric)}<br>Connections: {G.degree(v)}" for v in nodes],
            hoverinfo="text"))

    fig = go.Figure(traces)
    fig.update_layout(height=760, margin=dict(l=10, r=10, t=30, b=10), hovermode="closest",
                      legend=dict(orientation="h", y=1.02, x=0),
                      xaxis=dict(visible=False, range=[-1.45, 1.45] if layout == "Rings" else None),
                      yaxis=dict(visible=False, scaleanchor="x"))
    return fig


# ---------------------------------------------------------------------------
# World cartogram with flows to the U.S.
# ---------------------------------------------------------------------------
HUB_COLOR = ORANGE


def _seq_color(t):
    """Interpolate HEAT_SCALE at t in [0, 1] -> hex."""
    t = min(1.0, max(0.0, t))
    for (t0, c0), (t1, c1) in zip(HEAT_SCALE, HEAT_SCALE[1:]):
        if t <= t1:
            f = (t - t0) / (t1 - t0) if t1 > t0 else 0
            a = [int(c0[i:i + 2], 16) for i in (1, 3, 5)]
            b = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
            return "#" + "".join(f"{round(x + (y - x) * f):02x}" for x, y in zip(a, b))
    return HEAT_SCALE[-1][1]


def cartogram_map(countries, totals, metric, n_flows, hub_iso, anchor, title):
    """countries: distorted shapes from cartogram.build; totals: iso -> (name, n, value)."""
    vals = {iso: t[metric] for iso, t in totals.items()}
    vmax = max(vals.values()) if vals else 1.0
    log = metric == "value"
    zmax = _z([vmax], log)[0] or 1.0
    traces = []
    for c in countries:
        xs, ys = [], []
        for r in c["rings"]:
            xs += list(np.round(r[:, 0], 4)) + [float(r[0, 0]), None]
            ys += list(np.round(r[:, 1], 4)) + [float(r[0, 1]), None]
        t = totals.get(c["iso"])
        if c["iso"] == hub_iso:
            fill, hover = HUB_COLOR, "<b>United States</b><br>(recipient hub, true size)"
        elif t is None:
            fill, hover = LAND, f"<b>{c['name']}</b><br>No gifts in selection"
        else:
            fill = _seq_color(_z([t[metric]], log)[0] / zmax)
            hover = f"<b>{t['name']}</b><br>Gifts: {t['n']:,}<br>Value: {fmt_money(t['value'])}"
        traces.append(go.Scatter(x=xs, y=ys, mode="lines", fill="toself", fillcolor=fill,
                                 line=dict(color="white", width=0.6), hoveron="fills",
                                 text=hover, hoverinfo="text", showlegend=False))

    by_iso = {c["iso"]: c for c in countries}
    if hub_iso in by_iso:
        hx, hy = anchor(by_iso[hub_iso])
        ranked = sorted(((v, iso) for iso, v in vals.items() if iso in by_iso and v > 0), reverse=True)
        flows = ranked[:n_flows]
        fmax = flows[0][0] if flows else 1.0
        # Curved flow lines, binned into width classes (one width per plotly trace).
        for lo, hi, width in [(0.0, 0.1, 0.8), (0.1, 0.3, 1.8), (0.3, 0.6, 3.2), (0.6, 1.01, 5.0)]:
            xs, ys = [], []
            for v, iso in flows:
                f = v / fmax
                if not lo <= f < hi:
                    continue
                x0, y0 = anchor(by_iso[iso])
                mx, my = (x0 + hx) / 2, (y0 + hy) / 2
                # Control point offset perpendicular to the chord, so lines arc instead of overlapping.
                dx, dy = hx - x0, hy - y0
                cx, cy = mx - 0.18 * dy, my + 0.18 * dx
                for s in np.linspace(0, 1, 24):
                    xs.append((1 - s) ** 2 * x0 + 2 * (1 - s) * s * cx + s ** 2 * hx)
                    ys.append((1 - s) ** 2 * y0 + 2 * (1 - s) * s * cy + s ** 2 * hy)
                xs.append(None)
                ys.append(None)
            if xs:
                traces.append(go.Scatter(x=xs, y=ys, mode="lines", hoverinfo="skip", showlegend=False,
                                         line=dict(width=width, color="rgba(11,11,11,0.38)")))
        # Hoverable flow origins and labels for the largest givers.
        ox = [anchor(by_iso[iso])[0] for _, iso in flows]
        oy = [anchor(by_iso[iso])[1] for _, iso in flows]
        traces.append(go.Scatter(
            x=ox, y=oy, mode="markers+text", showlegend=False,
            marker=dict(size=6, color="#0b0b0b", line=dict(width=1.5, color="white")),
            text=[totals[iso]["name"] if i < 15 else "" for i, (_, iso) in enumerate(flows)],
            textposition="top center", textfont=dict(size=11),
            hovertext=[f"<b>{totals[iso]['name']}</b> → United States<br>Gifts: {totals[iso]['n']:,}"
                       f"<br>Value: {fmt_money(totals[iso]['value'])}" for _, iso in flows],
            hoverinfo="text"))
        traces.append(go.Scatter(x=[hx], y=[hy], mode="markers+text", text=["United States"],
                                 textposition="bottom center", showlegend=False, hoverinfo="skip",
                                 marker=dict(size=12, color=HUB_COLOR, symbol="diamond",
                                             line=dict(width=2, color="white"))))
    # Invisible trace that carries the colour bar.
    traces.append(go.Scatter(x=[None], y=[None], mode="markers", showlegend=False, hoverinfo="skip",
                             marker=dict(colorscale=HEAT_SCALE, cmin=0, cmax=zmax, color=[0],
                                         colorbar=_colorbar(metric, log, vmax), showscale=True)))
    fig = go.Figure(traces)
    fig.update_layout(title=title, height=680, margin=dict(l=0, r=0, t=50, b=0), hovermode="closest",
                      xaxis=dict(visible=False), yaxis=dict(visible=False, scaleanchor="x"),
                      plot_bgcolor="rgba(0,0,0,0)")
    return fig
