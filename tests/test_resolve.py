from app.stages.resolve import choose, score_candidate

ATOMIC = {"title": "Atomic Habits", "authors": ["James Clear"], "publisher": "Penguin"}
HABITS = {"title": "Habits", "authors": ["Someone Else"]}
HP1 = {"title": "Harry Potter and the Philosopher's Stone", "authors": ["J. K. Rowling"]}
HP2 = {"title": "Harry Potter and the Chamber of Secrets", "authors": ["J. K. Rowling"]}


def test_clean_spine_is_identified():
    r = choose("ATOMIC HABITS JAMES CLEAR", [HABITS, ATOMIC])
    assert r["status"] == "identified"
    assert r["match"] is ATOMIC


def test_one_misread_letter_still_matches():
    r = choose("ATOMIC HABlTS JAMES CLEAR", [ATOMIC])
    assert r["status"] == "identified"


def test_partial_title_is_not_guessed():
    r = choose("HARRY POTTER", [HP1, HP2])
    assert r["status"] == "unidentified"


def test_short_title_trap_scores_low():
    assert score_candidate("ATOMIC HABITS JAMES CLEAR", HABITS) < 0.80


def test_empty_input_is_unidentified():
    assert choose("", [ATOMIC])["status"] == "unidentified"
    assert choose("ATOMIC HABITS", [])["status"] == "unidentified"