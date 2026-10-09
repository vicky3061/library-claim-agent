from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class BookStatus(str, Enum):
    identified = "identified"
    unidentified = "unidentified"
    needs_appraisal = "needs_appraisal"


class ItemStatus(str, Enum):
    priced = "priced"
    range = "range"
    needs_appraisal = "needs_appraisal"


class Sweep(BaseModel):
    id: str
    captured_at: str                    # ISO time, e.g. 2026-10-10T18:30:00+05:30
    device: Optional[str] = None
    duration_s: Optional[float] = None
    country: str                        # e.g. "IN"
    currency: str                       # e.g. "INR"


class Room(BaseModel):
    length_m: Optional[float] = None
    width_m: Optional[float] = None
    height_m: Optional[float] = None
    floor_area_m2: Optional[float] = None
    wall_area_m2: Optional[float] = None
    shelved_wall_area_m2: Optional[float] = None
    scale_method: Optional[str] = None  # e.g. "webxr_arcore" or "aruco_marker"
    confidence: Optional[float] = None
    # added fields
    floor_area_ft2: Optional[float] = None
    wall_area_ft2: Optional[float] = None
    shape_note: Optional[str] = None    # how a non-rectangular room was handled

class BookPrice(BaseModel):
    amount: Optional[float] = None
    source: Optional[str] = None          # e.g. "Google Books API"
    url: Optional[str] = None             # link an adjuster can open
    retrieved_at: Optional[str] = None    # when we looked it up
    converted: bool = False               # True if from another market's currency
    # added fields
    currency: Optional[str] = None
    original_amount: Optional[float] = None
    original_currency: Optional[str] = None
    fx_rate: Optional[float] = None       # exchange rate used for conversion


class UsedPrice(BookPrice):
    condition_assumed: Optional[str] = None


class Book(BaseModel):
    id: str
    shelf: Optional[str] = None
    position: Optional[int] = None
    frame_ref: str                        # required: every book must point to a saved frame
    status: BookStatus
    title: Optional[str] = None
    author: Optional[str] = None
    edition: Optional[str] = None
    isbn: Optional[str] = None
    spine_height_cm: Optional[float] = None
    spine_thickness_cm: Optional[float] = None
    id_confidence: Optional[float] = None
    replacement_cost: BookPrice = Field(default_factory=BookPrice)
    used_value: UsedPrice = Field(default_factory=UsedPrice)
    # added fields
    spine_text_raw: Optional[str] = None  # exact letters read: the evidence for the title
    orientation: Optional[str] = None     # "upright" or "flat"
    excluded_by_user: bool = False        # "skip that shelf, those are not mine"


class Dimensions(BaseModel):
    w: Optional[float] = None
    h: Optional[float] = None
    d: Optional[float] = None


class ItemPrice(BaseModel):
    low: Optional[float] = None
    high: Optional[float] = None
    source: Optional[str] = None
    url: Optional[str] = None
    retrieved_at: Optional[str] = None
    # added
    currency: Optional[str] = None


class Item(BaseModel):
    id: str
    category: str
    description: Optional[str] = None
    brand_model: Optional[str] = None
    frame_ref: str
    dimensions_cm: Dimensions = Field(default_factory=Dimensions)
    status: ItemStatus
    replacement_cost: ItemPrice = Field(default_factory=ItemPrice)
    confidence: Optional[float] = None
    # added
    material: Optional[str] = None
    excluded_by_user: bool = False


class Totals(BaseModel):
    book_count: int = 0
    books_identified: int = 0
    books_unidentified: int = 0
    shelf_run_m: float = 0.0
    books_replacement_cost: float = 0.0
    books_used_value: float = 0.0
    items_replacement_cost_low: float = 0.0
    items_replacement_cost_high: float = 0.0
    excluded_from_totals: int = 0
    # added
    books_needs_appraisal: int = 0


class ReviewEntry(BaseModel):
    ref_id: str
    reason: str


class ClaimPacket(BaseModel):
    sweep: Sweep
    room: Room = Field(default_factory=Room)
    books: list[Book] = Field(default_factory=list)
    items: list[Item] = Field(default_factory=list)
    totals: Totals = Field(default_factory=Totals)
    review_queue: list[ReviewEntry] = Field(default_factory=list)
    # added: cost and latency per stage, needed for the failure log
    telemetry: dict = Field(default_factory=dict)