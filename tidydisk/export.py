"""Raport w jednym pliku HTML (pelny obraz na jednym ekranie) i JSON. Bez zewnetrznych zasobow."""
from __future__ import annotations

import html
import time

from . import core, spacelog


def _svg_chart(points: list, w: int = 560, h: int = 120) -> str:
    s = spacelog.series(points)
    if len(s) < 2:
        return "<p class='muted'>Za mało pomiarów na wykres - pojawią się po kilku skanach.</p>"
    xs, ys = [p[0] for p in s], [p[1] for p in s]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    dx, dy = max(x1 - x0, 1), max(y1 - y0, 1)
    pts = " ".join(f"{(x - x0) / dx * (w - 20) + 10:.1f},{h - 15 - (y - y0) / dy * (h - 30):.1f}" for x, y in s)
    return (f"<svg viewBox='0 0 {w} {h}' width='100%' role='img' aria-label='Zajęte miejsce w czasie'>"
            f"<polyline fill='none' stroke='#4c8dff' stroke-width='2' points='{pts}'/></svg>"
            f"<p class='muted'>Zajęte: od {core.fmt_size(y0)} do {core.fmt_size(y1)} "
            f"({time.strftime('%d.%m.%Y', time.localtime(x0))} - {time.strftime('%d.%m.%Y', time.localtime(x1))})</p>")


def data_from_cats(cats: list, disk_info: dict, version: str) -> dict:
    """Te same dane co w CLI, z kategorii pokazanych w oknie (tylko pozycje do usuniecia sa 'zaznaczone')."""
    from . import kb
    out, safe = [], 0
    for c in cats:
        ents = [{"label": x.label, "size": x.size, "rating": x.rating, "checked": bool(x.checked), "root": bool(x.root),
                 "warn": x.warn, "paths": [], "what": x.what} for x in c.entries]
        safe += sum(x["size"] for x in ents if x["rating"] == kb.SAFE and x["checked"] and not x["warn"])
        out.append({"key": c.key, "title": c.title, "root": c.root, "entries": ents})
    return {"version": version, "time": int(time.time()),
            "disks": {m: {"used": u, "total": t} for m, (u, t) in disk_info.items()},
            "categories": out, "safe_reclaimable": safe}


def to_html(data: dict, points: list | None = None) -> str:
    e = html.escape
    rows = []
    for c in data["categories"]:
        for it in sorted(c["entries"], key=lambda x: -x["size"])[:25]:
            rows.append(f"<tr><td>{e(c['title'])}</td><td>{e(it['label'])}</td><td class='n'>{core.fmt_size(it['size'])}</td>"
                        f"<td>{'tak' if it['checked'] else ''}</td></tr>")
    disks = "".join(
        f"<div class='tile'><b>{e(m)}</b><br>zajęte {core.fmt_size(d['used'])} z {core.fmt_size(d['total'])}"
        f"<div class='bar'><i style='width:{(100 * d['used'] / d['total']) if d['total'] else 0:.0f}%'></i></div></div>"
        for m, d in data["disks"].items())
    grow = ""
    if points:
        g, days = spacelog.growth(points)
        if days:
            grow = f"<p>Przez ostatnie {days} dni zajęte miejsce {'wzrosło' if g >= 0 else 'spadło'} o {core.fmt_size(abs(g))}.</p>"
    return f"""<!doctype html><html lang="pl"><meta charset="utf-8"><title>TidyDisk - raport</title>
<style>body{{font-family:system-ui,sans-serif;max-width:900px;margin:2em auto;padding:0 1em;color:#222;background:#fff}}
.tile{{display:inline-block;min-width:240px;margin:0 1em 1em 0;padding:.8em 1em;border:1px solid #8883;border-radius:10px}}
.bar{{height:8px;background:#8883;border-radius:4px;margin-top:6px}}.bar i{{display:block;height:8px;background:#2ec4a6;border-radius:4px}}
table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #8883;padding:4px 8px;text-align:left}}.n{{text-align:right}}
.muted{{color:#777}}@media(prefers-color-scheme:dark){{body{{background:#14171c;color:#e6e6e6}}}}</style>
<h1>TidyDisk {e(data['version'])}</h1><p class='muted'>{time.strftime('%d.%m.%Y %H:%M', time.localtime(data['time']))}</p>
<h2>Dyski</h2>{disks}<h2>Do odzyskania bezpiecznie: {core.fmt_size(data['safe_reclaimable'])}</h2>{grow}{_svg_chart(points or [])}
<h2>Największe pozycje</h2><table><tr><th>Kategoria</th><th>Pozycja</th><th>Rozmiar</th><th>Zaznaczone</th></tr>{''.join(rows)}</table></html>"""
