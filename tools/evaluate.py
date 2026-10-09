import argparse
import csv
import json
import os
import statistics

from rapidfuzz import fuzz

from app.stages.resolve import norm

TITLE_MATCH = 85  # fuzzy score (0-100) for "same title"; token_set handles subtitles and word order

BARS = {  # from the brief
    "count_error_pct": 5.0, "titles_correct_pct": 70.0, "titles_wrong_pct": 3.0, "spine_error_pct": 15.0,
    "price_error_pct": 25.0, "items_found_pct": 80.0, "floor_error_pct": 10.0, "wall_error_pct": 15.0,
}


def read_csv(folder, name):
    path = os.path.join(folder, name)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:  # utf-8-sig: Excel adds a BOM
        return [r for r in csv.DictReader(f) if any((v or "").strip() for v in r.values())]


def num(x):
    try:
        return float(str(x).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def same_title(a, b):
    a, b = norm(a), norm(b)
    return bool(a and b) and fuzz.token_set_ratio(a, b) >= TITLE_MATCH


def pct_err(pred, true):
    return abs(pred - true) / true * 100.0 if pred is not None and true else None


def match_one_to_one(preds, truths, key_pred, key_true):
    """Greedy one-to-one pairing by title, best score first. Each ground-truth book is used once."""
    pairs = []
    for i, p in enumerate(preds):
        for j, t in enumerate(truths):
            a, b = norm(key_pred(p)), norm(key_true(t))
            if a and b:
                s = fuzz.token_set_ratio(a, b)
                if s >= TITLE_MATCH:
                    pairs.append((s, i, j))
    used_p, used_t, out = set(), set(), []
    for s, i, j in sorted(pairs, reverse=True):
        if i not in used_p and j not in used_t:
            used_p.add(i); used_t.add(j); out.append((preds[i], truths[j]))
    return out


def evaluate(packet, gt):
    books = [b for b in packet["books"] if not b.get("excluded_by_user")]
    res = {}

    # 1. Book count (every physical book, readable or not)
    gt_books = read_csv(gt, "books.csv")
    if gt_books:
        n_true, n_pred = len(gt_books), len(books)
        res["count"] = {"true": n_true, "pred": n_pred, "error_pct": round(pct_err(n_pred, n_true), 1),
                        "pass": pct_err(n_pred, n_true) <= BARS["count_error_pct"]}

    # 2. Titles: correct among human-legible spines; confidently wrong among books we named
    legible = [r for r in gt_books if (r.get("legible") or "").strip().lower() == "yes" and (r.get("title") or "").strip()]
    named = [b for b in books if b["status"] in ("identified", "needs_appraisal") and b.get("title")]
    if legible:
        pairs = match_one_to_one(named, legible, lambda b: b["title"], lambda r: r["title"])
        all_titles = [r["title"] for r in gt_books if (r.get("title") or "").strip()]
        wrong = [b["title"] for b in named if not any(same_title(b["title"], t) for t in all_titles)]
        correct_pct = len(pairs) / len(legible) * 100
        wrong_pct = len(wrong) / len(named) * 100 if named else 0.0
        res["titles"] = {"legible": len(legible), "named_by_system": len(named), "correct": len(pairs),
                         "correct_pct": round(correct_pct, 1), "confidently_wrong": len(wrong),
                         "wrong_pct": round(wrong_pct, 1), "wrong_titles": wrong,
                         "pass": correct_pct >= BARS["titles_correct_pct"] and wrong_pct <= BARS["titles_wrong_pct"]}

    # 3. Spine dimensions on the hand-measured books
    spines = read_csv(gt, "spine_measurements.csv")
    if spines:
        rows, errs = [], []
        for b, t in match_one_to_one(named, spines, lambda b: b["title"], lambda r: r["title"]):
            for dim, col in (("spine_height_cm", "height_cm"), ("spine_thickness_cm", "thickness_cm")):
                e = pct_err(b.get(dim), num(t.get(col)))
                if e is not None:
                    errs.append(e)
                    rows.append({"title": t["title"], "dim": col, "true": num(t[col]), "pred": b[dim], "error_pct": round(e, 1)})
        within = sum(e <= BARS["spine_error_pct"] for e in errs)
        res["spines"] = {"measured_books": len(spines), "dimensions_compared": len(errs),
                         "within_15pct": within, "median_error_pct": round(statistics.median(errs), 1) if errs else None,
                         "pass": bool(errs) and within == len(errs), "rows": rows,
                         "note": "a book counts only if the system identified it AND measured it"}

    # 4. Prices against hand lookups on the same source type, same country/currency
    prices = [r for r in read_csv(gt, "prices.csv") if (r.get("country") or "").upper() == packet["sweep"]["country"].upper()]
    if prices:
        rows, errs = [], []
        for b, t in match_one_to_one(named, prices, lambda b: b["title"], lambda r: r["title"]):
            for kind, col in (("replacement_cost", "new_price"), ("used_value", "used_price")):
                e = pct_err((b.get(kind) or {}).get("amount"), num(t.get(col)))
                if e is not None:
                    errs.append(e)
                    rows.append({"title": t["title"], "kind": kind, "true": num(t[col]),
                                 "pred": b[kind]["amount"], "error_pct": round(e, 1)})
        within = sum(e <= BARS["price_error_pct"] for e in errs)
        res["prices"] = {"hand_priced_books": len(prices), "prices_compared": len(errs), "within_25pct": within,
                         "median_error_pct": round(statistics.median(errs), 1) if errs else None,
                         "pass": bool(errs) and within == len(errs), "rows": rows}

    # 5. Non-book items found (matched by category words; each ground-truth item used once)
    gt_items = read_csv(gt, "items.csv")
    if gt_items:
        used, found = set(), []
        for t in gt_items:
            twords = set(norm(f"{t.get('category', '')} {t.get('description', '')}").split())
            for i, it in enumerate(packet["items"]):
                iwords = set(norm(f"{it.get('category', '')} {it.get('description') or ''}").split())
                if i not in used and twords & iwords:
                    used.add(i); found.append(t.get("category")); break
        found_pct = len(found) / len(gt_items) * 100
        res["items"] = {"true": len(gt_items), "found": len(found), "found_pct": round(found_pct, 1),
                        "pass": found_pct >= BARS["items_found_pct"],
                        "note": "category-word match is lenient; check items by eye in the report"}

    # 6. Room areas from tape: floor = L x W, gross wall = 2(L+W) x H unless an explicit area row is given
    room = {r["measurement"].strip(): num(r.get("value_m")) for r in read_csv(gt, "room.csv") if r.get("measurement")}
    L, W, H = room.get("room_length"), room.get("room_width"), room.get("ceiling_height")
    floor_true = room.get("floor_area_m2") or (L * W if L and W else None)
    wall_true = room.get("wall_area_m2") or (2 * (L + W) * H if L and W and H else None)
    pr = packet.get("room") or {}
    for name, true, pred, bar in (("floor", floor_true, pr.get("floor_area_m2"), "floor_error_pct"),
                                  ("wall", wall_true, pr.get("wall_area_m2"), "wall_error_pct")):
        if true:
            e = pct_err(pred, true)
            res[f"{name}_area"] = {"true_m2": round(true, 2), "pred_m2": pred,
                                   "error_pct": round(e, 1) if e is not None else None,
                                   "pass": e is not None and e <= BARS[bar]}
    return res


def to_markdown(res, packet):
    t = packet.get("telemetry", {})
    lines = [f"# Results: sweep {packet['sweep']['id']} ({packet['sweep']['country']}/{packet['sweep']['currency']})", "",
             "| Bar (from the brief) | Ground truth | System | Result |", "|---|---|---|---|"]
    def row(name, true, pred, ok):
        lines.append(f"| {name} | {true} | {pred} | {'PASS' if ok else 'FAIL'} |")
    if "count" in res:
        c = res["count"]; row("Book count ±5%", c["true"], f"{c['pred']} ({c['error_pct']}% off)", c["pass"])
    if "titles" in res:
        c = res["titles"]
        row("Titles ≥70% of legible, ≤3% confidently wrong", f"{c['legible']} legible",
            f"{c['correct_pct']}% correct, {c['wrong_pct']}% wrong ({c['confidently_wrong']}/{c['named_by_system']})", c["pass"])
    if "spines" in res:
        c = res["spines"]; row("Spine dims ±15% (20 books)", f"{c['measured_books']} books",
                               f"{c['within_15pct']}/{c['dimensions_compared']} dims within, median {c['median_error_pct']}%", c["pass"])
    if "prices" in res:
        c = res["prices"]; row("Prices ±25% (15 books)", f"{c['hand_priced_books']} books",
                               f"{c['within_25pct']}/{c['prices_compared']} within, median {c['median_error_pct']}%", c["pass"])
    if "items" in res:
        c = res["items"]; row("Items ≥80% found", c["true"], f"{c['found']} ({c['found_pct']}%)", c["pass"])
    for k, label in (("floor_area", "Floor area ±10%"), ("wall_area", "Wall area ±15%")):
        if k in res:
            c = res[k]; row(label, f"{c['true_m2']} m²", f"{c['pred_m2']} m² ({c['error_pct']}% off)", c["pass"])
    lines += ["", f"Latency: vision {t.get('vision_s')} s · identify {t.get('identify_s')} s · price {t.get('price_s')} s · "
                  f"total {t.get('total_s')} s", "", "Wrong titles (named by the system, not on the shelf): "
              + (", ".join(res.get("titles", {}).get("wrong_titles", [])) or "none")]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="Score a claim packet against ground truth")
    ap.add_argument("packet")
    ap.add_argument("ground_truth_dir")
    a = ap.parse_args()
    with open(a.packet, encoding="utf-8") as f:
        packet = json.load(f)
    res = evaluate(packet, a.ground_truth_dir)
    out = os.path.dirname(a.packet)
    with open(os.path.join(out, "results.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2, ensure_ascii=False)
    md = to_markdown(res, packet)
    with open(os.path.join(out, "results.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(md)


if __name__ == "__main__":
    main()