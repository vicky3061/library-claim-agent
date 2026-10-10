from app.voice import parse


def test_corrections_from_the_brief():
    assert parse("Skip that shelf, those are not mine")["cmd"] == "skip_shelf"
    assert parse("that is a first edition") == {"cmd": "book_note", "note": "first edition"}
    assert parse("This one is signed by the author") == {"cmd": "book_note", "note": "signed"}
    assert parse("It's a print")["cmd"] == "art_print"
    assert parse("No, it's an original")["cmd"] == "art_original"
    assert parse("The country is the United States") == {"cmd": "locale", "country": "US", "currency": "USD"}
    assert parse("yes")["cmd"] == "yes"


def test_unrelated_speech_changes_nothing():
    assert parse("hmm let me move the chair")["cmd"] == "unknown"
    assert parse("")["cmd"] == "unknown"



def test_finish_by_voice():
    from app.voice import parse
    for said in ("finish", "okay finish the sweep", "wind it up", "that's all", "I'm done"):
        assert parse(said)["cmd"] == "finish", said
    assert parse("Finnish edition")["cmd"] != "finish"