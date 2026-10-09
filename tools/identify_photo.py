import sys

from app.stages import resolve, vision


def main(path):
    out, tel = vision.analyze_frame(open(path, "rb").read())
    if out is None:
        sys.exit(f"vision failed: {tel['attempts'][-1:]}")
    print(f"vision: {len(out.spines)} spines | model={tel.get('model')} | cache_hit={tel.get('cache_hit')}")
    counts = {"identified": 0, "unidentified": 0, "unreadable": 0}
    for i, s in enumerate(out.spines):
        if not s.text.strip() or s.legibility == "unreadable":
            counts["unreadable"] += 1
            print(f"{i:2d} UNREADABLE (logged with dimensions, no title guessed)")
            continue
        r = resolve.resolve_spine(s.model_dump())
        counts[r["status"]] += 1
        m = r["match"]
        result = f"{m['title']} | {', '.join(m['authors'][:2])} | {m['source']}" if m else r["reason"]
        vol = f" vol {r['volume']}" if r.get("volume") else ""
        print(f"{i:2d} {r['status']:12s} {r['confidence']:.2f} | read: {s.title or s.text[:40]!r}{vol} -> {result}")
    print(counts)


if __name__ == "__main__":
    main(sys.argv[1])