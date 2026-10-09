from html import escape
import json


def _money(p, ccy):
    if not p or p.amount is None:
        return "—"
    tag = " (converted)" if p.converted else ""
    link = f' <a href="{escape(p.url)}">source</a>' if p.url else ""
    return f"{p.amount:,.2f} {escape(ccy)}{tag}{link}"


def write_report(packet, path):
    s, t, ccy = packet.sweep, packet.totals, packet.sweep.currency
    shelf_run = f"{t.shelf_run_m} m" if t.shelf_run_m is not None else "not measured (no metric scale in frames)"
    rows = "".join(
        f"<tr><td>{escape(b.id)}</td><td>{escape(b.status.value)}</td><td>{escape(b.title or '—')}</td>"
        f"<td>{escape(b.author or '—')}</td><td>{escape(b.edition or '')}</td>"
        f"<td>{b.spine_height_cm if b.spine_height_cm is not None else '—'} × "
        f"{b.spine_thickness_cm if b.spine_thickness_cm is not None else '—'}</td>"
        f"<td>{_money(b.replacement_cost, ccy)}</td><td>{_money(b.used_value, ccy)}</td>"
        f"<td><a href=\"{escape(b.frame_ref)}\">frame</a></td></tr>" for b in packet.books)
    items = "".join(
        f"<tr><td>{escape(i.id)}</td><td>{escape(i.category)}</td><td>{escape(i.description or '')}</td>"
        f"<td>{escape(i.status.value)}</td><td><a href=\"{escape(i.frame_ref)}\">frame</a></td></tr>"
        for i in packet.items)
    review = "".join(f"<li><b>{escape(r.ref_id)}</b>: {escape(r.reason)}</li>" for r in packet.review_queue)
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>Claim packet {escape(s.id)}</title>
<style>body{{font-family:sans-serif;margin:24px}}table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #ccc;padding:4px 6px;font-size:13px;text-align:left}}th{{background:#f3f3f3}}</style></head><body>
<h1>Contents claim packet</h1>
<p>Sweep <b>{escape(s.id)}</b> · {escape(s.captured_at)} · {escape(s.country)} / {escape(ccy)}</p>
<h2>Totals (computed in code from the lines)</h2>
<ul><li>Books: {t.book_count} ({t.books_identified} identified, {t.books_unidentified} unidentified,
{t.books_needs_appraisal} need appraisal)</li><li>Shelf run: {shelf_run}</li>
<li>Books replacement cost: {t.books_replacement_cost:,.2f} {escape(ccy)} · used value: {t.books_used_value:,.2f} {escape(ccy)}</li>
<li>Items: {t.items_replacement_cost_low:,.2f}–{t.items_replacement_cost_high:,.2f} {escape(ccy)}</li>
<li>Lines excluded from totals: {t.excluded_from_totals}</li></ul>
<h2>Books</h2><table><tr><th>ID</th><th>Status</th><th>Title</th><th>Author</th><th>Edition</th>
<th>Spine h × t (cm)</th><th>Replacement</th><th>Used</th><th>Evidence</th></tr>{rows}</table>
<h2>Other items</h2><table><tr><th>ID</th><th>Category</th><th>Description</th><th>Status</th><th>Evidence</th></tr>{items}</table>
<h2>Run telemetry</h2><pre>{escape(json.dumps(packet.telemetry, indent=2))}</pre>
<h2>Review queue ({len(packet.review_queue)})</h2><ul>{review}</ul></body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)