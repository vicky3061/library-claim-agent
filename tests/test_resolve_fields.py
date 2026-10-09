from app.stages import resolve as R

NANSEN = {"title": "In Nacht und Eis", "authors": ["Fridtjof Nansen"], "source": "OL", "source_id": "1"}
ATOMIC = {"title": "Atomic Habits", "authors": ["James Clear"], "source": "GB", "source_id": "2"}
HABITS = {"title": "Habits", "authors": ["Someone Else"], "source": "GB", "source_id": "3"}
HP1 = {"title": "Harry Potter and the Philosopher's Stone", "authors": ["J. K. Rowling"], "source": "GB", "source_id": "4"}
HP2 = {"title": "Harry Potter and the Chamber of Secrets", "authors": ["J. K. Rowling"], "source": "GB", "source_id": "5"}
HOEHLE = {"title": "Die Höhlenkinder im Pfahlbau", "authors": ["Alois Theodor Sonnleitner", "Alois Tlučhoř"],
          "source": "OL", "source_id": "6"}
BORGES = {"title": "Erzählungen", "authors": ["Jorge Luis Borges"], "source": "GB", "source_id": "7"}
OTHER_ERZ = {"title": "Erzählungen", "authors": ["Franz Kafka"], "source": "GB", "source_id": "8"}


def test_publisher_noise_no_longer_hurts():
    r = R.choose_fields("IN NACHT UND EIS", "NANSEN", [NANSEN])
    assert r["status"] == "identified" and r["confidence"] >= 0.9


def test_partial_title_still_not_guessed():
    assert R.choose_fields("HARRY POTTER", "", [HP1, HP2])["status"] == "unidentified"


def test_short_title_trap_still_blocked():
    r = R.choose_fields("ATOMIC HABITS", "JAMES CLEAR", [HABITS, ATOMIC])
    assert r["match"] is ATOMIC
    assert R.score_fields("ATOMIC HABITS", "JAMES CLEAR", HABITS) < 0.8


def test_pen_name_matches_via_alternative_name():
    assert R.choose_fields("Die Höhlenkinder im Pfahlbau", "SONNLEITNER", [HOEHLE])["status"] == "identified"


def test_author_separates_same_title_by_different_authors():
    r = R.choose_fields("Erzählungen", "Jorge Luis Borges", [OTHER_ERZ, BORGES])
    assert r["status"] == "identified" and r["match"] is BORGES


def test_wrong_author_is_not_accepted():
    assert R.choose_fields("Erzählungen", "Jorge Luis Borges", [OTHER_ERZ])["status"] == "unidentified"


def test_resolve_spine_uses_targeted_queries(monkeypatch):
    seen = []
    def fake_gb(q, max_results=5):
        seen.append(("gb", q))
        return [NANSEN] if "inauthor:nansen" in q else []
    def fake_ol(params, limit=5):
        seen.append(("ol", params))
        return []
    monkeypatch.setattr(R, "_gb", fake_gb)
    monkeypatch.setattr(R, "_ol", fake_ol)
    r = R.resolve_spine({"text": "NANSEN IN NACHT UND EIS I LEIPZIG F.A. BROCKHAUS", "title": "IN NACHT UND EIS",
                         "author": "NANSEN", "publisher": "F.A. BROCKHAUS", "volume": "I"})
    assert r["status"] == "identified" and r["volume"] == "I"
    assert all("BROCKHAUS" not in str(q) for _, q in seen)  # publisher never pollutes the query


def test_no_title_field_falls_back_to_full_text(monkeypatch):
    monkeypatch.setattr(R, "google_books_candidates", lambda t: [ATOMIC])
    monkeypatch.setattr(R, "open_library_candidates", lambda t: [])
    r = R.resolve_spine({"text": "ATOMIC HABITS JAMES CLEAR", "title": "", "author": ""})
    assert r["status"] == "identified"

def test_sharp_s_spellings_are_the_same_title():
    # Real failure: "Auf großer Fahrt" vs "Auf grosser Fahrt" was flagged ambiguous
    assert R.norm("Auf großer Fahrt") == R.norm("AUF GROSSER FAHRT") == "auf grosser fahrt"
    a = {"title": "Auf großer Fahrt", "authors": ["Sven Hedin"], "source": "GB", "source_id": "a"}
    b = {"title": "Auf grosser Fahrt", "authors": ["Sven Anders Hedin"], "source": "OL", "source_id": "b"}
    assert R.choose_fields("AUF GROSSER FAHRT", "HEDIN", [a, b])["status"] == "identified"