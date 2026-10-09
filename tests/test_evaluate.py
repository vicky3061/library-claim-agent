import csv
from tools import evaluate as E


def _csv(folder, name, header, rows):
    with open(folder / name, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)


def _book(title, status="identified", h=None, t=None, repl=None):
    return {"title": title, "status": status, "spine_height_cm": h, "spine_thickness_cm": t,
            "replacement_cost": {"amount": repl}, "used_value": {"amount": None}}


def test_scores_every_bar(tmp_path):
    _csv(tmp_path, "books.csv", ["shelf_unit", "shelf_row", "position", "orientation", "legible", "title", "author"], [
        ["A", 1, 1, "upright", "yes", "Atomic Habits", "James Clear"],
        ["A", 1, 2, "upright", "yes", "Sapiens: A Brief History of Humankind", "Yuval Noah Harari"],
        ["A", 1, 3, "upright", "no", "Old Notebook", ""],
        ["A", 1, 4, "upright", "yes", "Deep Work", "Cal Newport"]])
    _csv(tmp_path, "spine_measurements.csv", ["shelf_unit", "shelf_row", "position", "title", "height_cm", "thickness_cm"],
         [["A", 1, 1, "Atomic Habits", 20.0, 2.0]])
    _csv(tmp_path, "prices.csv", ["title", "country", "new_price", "used_price"], [["Atomic Habits", "IN", 500, ""]])
    _csv(tmp_path, "items.csv", ["item_no", "category", "description"], [[1, "lamp", "desk lamp"], [2, "shelving", "bookcase"]])
    _csv(tmp_path, "room.csv", ["measurement", "value_m"], [["room_length", 4], ["room_width", 3], ["ceiling_height", 2.5]])
    packet = {"sweep": {"id": "t", "country": "IN", "currency": "INR"},
              "books": [_book("Atomic Habits", h=21.0, t=2.1, repl=472), _book("Sapiens"),
                        _book("Harry Potter"), _book(None, status="unidentified")],
              "items": [{"category": "shelving", "description": "wooden bookcase"}],
              "room": {"floor_area_m2": 12.6, "wall_area_m2": 29.0}, "telemetry": {}}
    r = E.evaluate(packet, str(tmp_path))
    assert r["count"]["error_pct"] == 0 and r["count"]["pass"]
    assert r["titles"]["correct"] == 2 and r["titles"]["legible"] == 3          # subtitle still matches
    assert r["titles"]["wrong_titles"] == ["Harry Potter"] and not r["titles"]["pass"]
    assert r["spines"]["within_15pct"] == 2 and r["spines"]["pass"]
    assert r["prices"]["rows"][0]["error_pct"] == 5.6 and r["prices"]["pass"]
    assert r["items"]["found"] == 1 and not r["items"]["pass"]
    assert r["floor_area"]["error_pct"] == 5.0 and r["floor_area"]["pass"]       # 12.6 vs 12.0
    assert r["wall_area"]["true_m2"] == 35.0 and not r["wall_area"]["pass"]      # 29 vs 35 = 17.1% > 15%
    assert "FAIL" in E.to_markdown(r, packet)


def test_missing_files_are_skipped(tmp_path):
    r = E.evaluate({"sweep": {"id": "t", "country": "IN", "currency": "INR"}, "books": [], "items": [], "room": {}}, str(tmp_path))
    assert r == {}