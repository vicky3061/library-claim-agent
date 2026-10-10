import re

COUNTRIES = {"india": ("IN", "INR"), "indian": ("IN", "INR"), "us": ("US", "USD"), "usa": ("US", "USD"),
             "united states": ("US", "USD"), "america": ("US", "USD"), "american": ("US", "USD")}
APPRAISAL_PHRASES = ("first edition", "1st edition", "signed", "autographed", "limited edition", "rare", "antique")


def parse(text):
    """Returns one command dict: skip_shelf | book_note | art_print | art_original | locale | yes | unknown."""
    t = " " + re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()) + " "
    t = re.sub(r"\s+", " ", t)
    if re.search(r" (finish|finished|wind up|wind it up|that s all|i m done|we re done|stop the sweep|end the sweep) ", t):
        return {"cmd": "finish"}
    if re.search(r" (skip|ignore|exclude|don t count|do not count)\b.*\b(shelf|shelves|these|those|this|that)\b", t) \
            or " not mine " in t:
        return {"cmd": "skip_shelf"}
    for phrase in APPRAISAL_PHRASES:
        if f" {phrase} " in t:
            return {"cmd": "book_note", "note": phrase}
    if re.search(r"\b(it s|its|it is|that s|that is|just) a? ?(print|poster|copy|reproduction)\b", t) or t.strip() == "print":
        return {"cmd": "art_print"}
    if re.search(r"\b(original|real painting|hand painted)\b", t):
        return {"cmd": "art_original"}
    for name, (country, currency) in COUNTRIES.items():
        if re.search(rf"\b(country|currency|in|i m in|we re in|switch to|use|prices in)\b.*\b{name}\b", t) \
                or t.strip() == name:
            return {"cmd": "locale", "country": country, "currency": currency}
    if t.strip() in ("yes", "yeah", "yep", "correct", "that s right", "right", "ok", "okay"):
        return {"cmd": "yes"}
    return {"cmd": "unknown"}