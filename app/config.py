import os

from dotenv import load_dotenv

load_dotenv()  # reads .env into environment variables

# locale (a setting, not hardcoded: proves the second-country requirement)
COUNTRY = os.getenv("COUNTRY", "IN")
CURRENCY = os.getenv("CURRENCY", "INR")

# identification: matches below this confidence go to the review queue
ID_REVIEW_THRESHOLD = 0.90

SQFT_PER_SQM = 10.7639

SHELF_MARKER_CM = 10.0
WALL_MARKER_CM = 18.0

# identification
ID_ACCEPT_THRESHOLD = 0.80   # below this: unidentified, title left blank
ID_REVIEW_THRESHOLD = 0.90   # accepted, but below this: also flagged for review
ID_AMBIGUITY_MARGIN = 0.05   # two different titles this close: ambiguous, refuse to pick