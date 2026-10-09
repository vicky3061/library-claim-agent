from app.stages.price import pick_canonical, reject_reason

# Real Amazon.in results for "Atomic Habits James Clear", fetched 2026-10-09: (title, price, reviews, rating)
REAL_AMAZON_IN = [
    ("Atomic Habits (Tamil)", 269, 1200, 4.6),
    ("Atomic Habits (Telugu)", 295, 586, 4.4),
    ("Atomic Habits: Tiny Changes, Remarkable Results", 472, 1.1, 4.6),
    ("Atomic Habits Book Practical Behaviour Guide To Better Routines Small Daily Changes", 299, None, None),
    ("Atomic Habits + The Science of Rapid Skill Acquisition | 2-Book Combo", 726, None, None),
    ("Atomic Habits – Simple Strategies for Building Better Routines and Lasting Change", 425, None, None),
    ("Atomic Habits Transform your life with tiny changes in behaviour, starting now.", 299, None, None),
    ("Atomic Habits (Marathi)", 277, 1500, 4.5),
    ("Atomic Habits: Chote Badlav, Asadharan Parinaam (Hindi)", 390.45, 5100, 4.5),
    ("Atomic Habits by James Clear, Paperback", 279, None, None),
    ("The Atomic Habits Workbook: Official Companion To Atomic Habits by James Clear", 589, 344, 4.6),
    ("Atomic Habits Tiny Changes, Remarkable Results Paperback", 349, None, None),
    ("Atomic Habits + The Psychology of Money | James Clear & Morgan Housel", 270, 4, 4.2),
]
LISTINGS = [{"title": t, "extracted_price": p, "reviews": r, "rating": g} for t, p, r, g in REAL_AMAZON_IN]


def test_real_amazon_results_pick_the_genuine_listing():
    best, rejected = pick_canonical(LISTINGS, "Atomic Habits")
    assert best["extracted_price"] == 472
    assert len(rejected) == len(LISTINGS) - 1


def test_only_other_languages_gives_no_price():
    only_hindi = [{"title": "Atomic Habits (Hindi)", "extracted_price": 300, "rating": 4.5, "reviews": 10}]
    best, rejected = pick_canonical(only_hindi, "Atomic Habits")
    assert best is None
    assert rejected[0]["reason"] == "other language"


def test_workbook_is_fine_when_the_book_is_the_workbook():
    assert reject_reason("The Atomic Habits Workbook", "The Atomic Habits Workbook") is None

def test_zero_price_audiobook_is_rejected():
    listings = [
        {"title": "Atomic Habits", "extracted_price": 0.0, "rating": 4.8, "reviews": 200000,
         "link": "https://www.amazon.com/Atomic-Habits-James-Clear-audiobook/dp/B07RFSSYBH/"},
        {"title": "Atomic Habits: An Easy & Proven Way to Build Good Habits", "extracted_price": 14.5,
         "rating": 4.8, "reviews": 150000, "link": "https://www.amazon.com/dp/0735211299/"},
    ]
    best, rejected = pick_canonical(listings, "Atomic Habits")
    assert best["extracted_price"] == 14.5
    assert rejected[0]["reason"] == "no physical-format price"