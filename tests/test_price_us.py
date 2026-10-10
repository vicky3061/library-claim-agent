from app.stages.price import pick_canonical, reject_reason

# Real amazon.com results for "Atomic Habits James Clear", fetched 2026-10-09 (subset)
US_REAL = [
    ("Atomic Habits: An Easy & Proven Way to Build Good Habits & Break Bad Ones", 0.0, 150000, 4.8,
     "https://www.amazon.com/Atomic-Habits-James-Clear-audiobook/dp/B07RFSSYBH/",
     [{"type": "Audiobook", "extracted_primary_price": 0.0},
      {"type": "Hardcover", "extracted_primary_price": 18.88, "extracted_old_primary_price": 27.0,
       "more_buying_choices_link": "https://www.amazon.com/gp/offer-listing/0735211299/ref=sr_1_1_olp"},
      {"type": "Kindle", "extracted_primary_price": 12.99}]),
    ("Hábitos atómicos en acción: Ejercicios sencillos para construir la vida que quieres", 17.5, 107, 4.6, "", None),
    ("Atomic Habits (Chinese Edition)", 18.29, 5, 5.0, "", None),
    ("아주 작은 습관의 힘 ATOMIC HABITS Korean Text 제임스 클리어 James Clear", 28.73, 14, 4.6, "", None),
    ("Atomic Habits Poster James Clear Motivational Quotes Wall Art Canvas", 21.67, None, None, "", None),
    ("The Atomic Habits Daily Calendar: 365 Powerful Ideas for a Better Year", 18.63, 30, 4.5, "", None),
    ("Hábitos atómicos (Edición especial): Incluye curso inédito 30 días para mejorar tus hábitos "
     "/ Atomic Habits (Spanish Edition)", 25.8, 24000, 4.8, "https://www.amazon.com/dp/6075696148/", None),
]
LISTINGS = [{"title": t, "extracted_price": p, "reviews": r, "rating": g, "link": l, "purchase_options": o}
            for t, p, r, g, l, o in US_REAL]


def test_us_picks_the_hardcover_inside_the_genuine_listing():
    best, rejected = pick_canonical(LISTINGS, "Atomic Habits")
    assert best["_offer"]["format"] == "hardcover"
    assert best["_offer"]["price"] == 18.88
    assert best["_offer"]["url"] == "https://www.amazon.com/dp/0735211299"


def test_spanish_korean_chinese_are_other_languages():
    for t in ["Hábitos atómicos en acción: Ejercicios sencillos para construir la vida que quieres",
              "Atomic Habits (Chinese Edition)",
              "아주 작은 습관의 힘 ATOMIC HABITS Korean Text"]:
        assert reject_reason(t, "Atomic Habits") == "other language"


def test_english_titles_still_pass():
    assert reject_reason("Atomic Habits: Tiny Changes, Remarkable Results", "Atomic Habits") is None
    assert reject_reason("La La Land and Other Stories", "La La Land") is None


def test_poster_and_calendar_are_not_the_book():
    assert reject_reason("Atomic Habits Poster Wall Art Canvas", "Atomic Habits") == "not the book itself"
    assert reject_reason("The Atomic Habits Daily Calendar", "Atomic Habits") == "not the book itself"

def test_paperback_option_on_a_kindle_page_without_its_own_link_is_not_used():
    from app.stages.price import physical_offer
    kindle = {"title": "Secret Star: A classic story of romance", "link": "https://www.amazon.in/Secret-Star-ebook/dp/B006LAOIP6/",
              "extracted_price": 199.0,
              "purchase_options": [{"type": "Paperback", "extracted_primary_price": 4000.0}]}
    assert physical_offer(kindle, "www.amazon.in") is None


def test_paperback_option_with_its_own_link_is_still_used():
    from app.stages.price import physical_offer
    kindle = {"title": "Secret Star", "link": "https://www.amazon.in/Secret-Star-ebook/dp/B006LAOIP6/",
              "purchase_options": [{"type": "Paperback", "extracted_primary_price": 799.0,
                                    "more_buying_choices_link": "https://www.amazon.in/gp/offer-listing/0373484623/"}]}
    o = physical_offer(kindle, "www.amazon.in")
    assert o["price"] == 799.0 and o["url"] == "https://www.amazon.in/dp/0373484623"
