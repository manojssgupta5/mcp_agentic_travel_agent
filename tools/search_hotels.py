from contextlib import asynccontextmanager
import os
import uuid
import logging
import subprocess
from datetime import datetime
from typing import List, Dict, Any, Optional
import pandas as pd
import requests
from mcp.server.fastmcp import FastMCP

# 1. Server Initialization
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Hotel Operations")

# --- App Configuration Matrix Constants ---
HOTELS_CSV = "../resources/data/hotels.csv"

# --- Shared In-Memory State Pipeline Contexts ---
hotels_df: pd.DataFrame = pd.DataFrame()
_bookings: Dict[str, Dict[str, Any]] = {}

# ── Helper Functions ──────────────────────────────────────────
def _load_csv() -> pd.DataFrame:
    df = pd.read_csv(HOTELS_CSV)
    logging.info("Loaded %d records", len(df))
    return df

def _append_to_csv(records: list) -> None:
    try:
        pd.DataFrame(records).to_csv(HOTELS_CSV, mode="a", header=False, index=False)
        logging.info("Appended %d record(s) to %s", len(records), HOTELS_CSV)
    except Exception as e:
        logging.warning("Failed to append to %s: %s", HOTELS_CSV, e)

def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"

def _get_booking(booking_id: str) -> dict:
    if booking_id not in _bookings:
        raise ValueError(f"Booking '{booking_id}' not found")
    return _bookings[booking_id]

# ── 1. Create the Lifespan Function ──────────────────────────────────────────
@asynccontextmanager
async def server_lifespan(server: FastMCP):
    """
    This runs exactly ONCE when the server starts up before accepting queries.
    Anything before the `yield` statement acts as your initialization logic.
    """
    global hotels_df
    logging.info("Starting up hotel server... Initializing dataset assets.")
    
    # Run your initial CSV loading routine here
    hotels_df = _load_csv()
    
    try:
        # Hands control back over to the MCP server to begin serving tool requests
        yield 
    finally:
        # Optional: Code placed here runs right when the server shuts down
        logging.info("Shutting down hotel server... Cleaning up resources.")

mcp = FastMCP("Hotel Operations", lifespan=server_lifespan)

# ── 1. PROPERTY SEARCH & DISCOVERY ────────────────────────────────────────────

@mcp.tool()
def get_hotels(
    city: str,
    check_in: str = "",
    check_out: str = "",
    guests: int = 1,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Search and find available hotels, room configurations, and pricing arrays for a target destination.

    Args:
        city: Destination search location city (e.g., 'Paris', 'Dubai').
        check_in: Desired check-in window deadline date formatted as YYYY-MM-DD.
        check_out: Desired check-out window deadline date formatted as YYYY-MM-DD.
        guests: Total quantity count of lodging travelers.
        limit: Total item pagination limits to slice off from top results.
    """
    records = []
    
    # Tier 1: Search Local Synchronized CSV Datasets
    if not hotels_df.empty:
        filtered = hotels_df[hotels_df["city"].str.lower() == city.lower()]
        csv_records = filtered.head(limit).to_dict(orient="records")
        if csv_records:
            for h in csv_records:
                h["checkIn"] = check_in
                h["checkOut"] = check_out
            records = csv_records

    # Tier 2: Fetch Live External API Integration Sink
    api_key = os.getenv("HOTEL_EXTERNAL_KEY", "")
    api_url = os.getenv("HOTEL_EXTERNAL_URL", "")
    
    if not records and api_key and api_url:
        url = f"{api_url}?cityName={requests.utils.quote(city)}&limit={limit}"
        try:
            resp = requests.get(url, headers={"X-API-Key": api_key}, timeout=10)
            if resp.status_code == 200:
                for item in resp.json().get("data", []):
                    star = item.get("starRating", 3)
                    records.append({
                        "hotel_id": item.get("id", "H?"),
                        "name": item.get("name", "Hotel"),
                        "city": city,
                        "neighborhood": item.get("address", ""),
                        "distance_km": 1.0,
                        "price_per_night": star * 60.0,
                        "rating": min(5.0, star * 0.8 + 0.5),
                        "review_count": 0,
                        "amenities": "|".join(str(f) for f in item.get("hotelFacilities", ["Free WiFi"])[:6]),
                        "available_rooms": 10,
                        "checkIn": check_in,
                        "checkOut": check_out,
                    })
                if records:
                    _append_to_csv(records)
        except Exception as e:
            logger.warning("External fallback loop processing caught variance: %s", e)

    # Tier 3: Programmatic Static Mock Engine Fallback
    if not records:
        records = [
            {"hotel_id": "H1", "name": f"{city} Grand Hotel", "city": city, "neighborhood": "City Centre", "price_per_night": 280.0, "rating": 4.6, "amenities": "Free WiFi|Breakfast|Spa", "checkIn": check_in, "checkOut": check_out},
            {"hotel_id": "H2", "name": f"{city} Boutique Inn", "city": city, "neighborhood": "Old Town", "price_per_night": 150.0, "rating": 4.2, "amenities": "Free WiFi|Rooftop Bar", "checkIn": check_in, "checkOut": check_out},
            {"hotel_id": "H3", "name": f"{city} Budget Stay", "city": city, "neighborhood": "Near Station", "price_per_night": 90.0, "rating": 3.8, "amenities": "Free WiFi|24h Reception", "checkIn": check_in, "checkOut": check_out}
        ][:limit]

    return records


# ── 2. RESERVATION LIFECYCLE DIRECTIVES ───────────────────────────────────────

@mcp.tool()
def create_hotel_booking(
    hotel_id: str,
    room_type: str,
    check_in: str,
    check_out: str,
    contact_email: str,
    occupancy: int = 1,
    guests: Optional[List[Dict[str, Any]]] = None,
    contact_phone: str = "",
    board_basis: str = "room_only"
) -> Dict[str, Any]:
    """
    Construct a new pending hotel stay booking waiting execution for downstream clearing logs.
    """
    booking_id = "HBK-" + str(uuid.uuid4())[:8].upper()
    booking = {
        "booking_id":      booking_id,
        "type":            "hotel",
        "hotel_id":        hotel_id,
        "room_type":       room_type,
        "check_in":        check_in,
        "check_out":       check_out,
        "occupancy":       occupancy,
        "board_basis":     board_basis,
        "guests":          guests or [],
        "contact_email":   contact_email,
        "contact_phone":   contact_phone,
        "booking_status":  "pending",
        "ticket_status":   "not_issued",
        "payment_status":  "pending",
        "refund_status":   "none",
        "special_requests": [],
        "ancillaries":     [],
        "total_price":     0.0,
        "created_at":      _now(),
        "modified_at":     _now(),
    }
    _bookings[booking_id] = booking
    logger.info("Created hotel booking engine node allocation entry: %s", booking_id)
    return booking

@mcp.tool()
def issue_hotel_voucher(booking_id: str) -> Dict[str, Any]:
    """
    Issue final reservation confirmations and lock down digital voucher parameters post settlement.
    """
    booking = _get_booking(booking_id)
    if booking["payment_status"] != "paid":
        raise ValueError(f"Settle clearing balances for order '{booking_id}' prior to requesting voucher generation triggers.")
    if booking["ticket_status"] == "issued":
        raise ValueError(f"Active confirmation voucher metadata already dispatched for entry context '{booking_id}'.")

    voucher_number = "VCH-" + str(uuid.uuid4())[:10].upper()
    booking["ticket_status"]  = "issued"
    booking["booking_status"] = "confirmed"
    booking["voucher_number"] = voucher_number
    booking["issued_at"]      = _now()
    booking["modified_at"]    = _now()
    
    return {"booking_id": booking_id, "voucher_number": voucher_number, "ticket_status": "issued"}

@mcp.tool()
def handle_hotel_payment(
    booking_id: str,
    payment_method: str,
    amount: float,
    currency: str = "USD",
    transaction_reference: Optional[str] = None
) -> Dict[str, Any]:
    """
    Post clear balancing settlement fields to confirm credit ledger transactions for target orders.
    """
    booking = _get_booking(booking_id)
    if booking["payment_status"] == "paid":
        raise ValueError(f"Double-settlement intercept: Order allocation node '{booking_id}' flags paid state.")

    transaction_id = transaction_reference or ("TXN-" + str(uuid.uuid4())[:10].upper())
    booking["payment_status"]    = "paid"
    booking["booking_status"]    = "confirmed"
    booking["total_price"]       = amount
    booking["payment_method"]    = payment_method
    booking["payment_currency"]  = currency
    booking["transaction_id"]    = transaction_id
    booking["payment_timestamp"] = _now()
    booking["modified_at"]       = _now()
    
    return {
        "booking_id":     booking_id,
        "transaction_id": transaction_id,
        "payment_status": "paid",
        "amount":         amount,
        "currency":       currency,
    }


# ── 3. RESERVATION AMENDMENTS & GUEST LOGS ────────────────────────────────────

@mcp.tool()
def modify_hotel_booking(
    booking_id: str,
    change_type: str,
    new_check_in: Optional[str] = None,
    new_check_out: Optional[str] = None,
    new_room_type: Optional[str] = None,
    new_occupancy: Optional[int] = None
) -> Dict[str, Any]:
    """
    Alter and amend variables inside an allocated itinerary reservation record.

    Args:
        booking_id: Explicit target processing block reference tracker ID code.
        change_type: Struct identifier option key: 'change_dates', 'change_room_type', or 'change_occupancy'.
        new_check_in: Alternative altered stay arrival timeline date string (YYYY-MM-DD).
        new_check_out: Alternative altered stay checkout timeline date string (YYYY-MM-DD).
        new_room_type: Target category up-tier labels desired (e.g., 'Junior Suite').
        new_occupancy: Revised guest threshold count parameter values.
    """
    booking = _get_booking(booking_id)
    if booking["booking_status"] == "cancelled":
        raise ValueError(f"Modification sequence rejected: Target block '{booking_id}' has been permanently dropped.")

    if change_type == "change_dates":
        if not new_check_in and not new_check_out:
            raise ValueError("Supply at least one modification boundary parameter update for date realignment calls.")
        if new_check_in:
            booking["check_in"] = new_check_in
        if new_check_out:
            booking["check_out"] = new_check_out
        booking["ticket_status"] = "void"

    elif change_type == "change_room_type":
        if not new_room_type:
            raise ValueError("Target property tier parameter definition string is required for room changes.")
        booking["room_type"] = new_room_type
        booking["ticket_status"] = "void"

    elif change_type == "change_occupancy":
        if new_occupancy is None:
            raise ValueError("Invalid occupancy adjustment argument encountered.")
        booking["occupancy"] = new_occupancy
    else:
        raise ValueError(f"Encountered unrecognized action mapping modifier key code: '{change_type}'")

    booking["modified_at"] = _now()
    return {"booking_id": booking_id, "change_type": change_type, "booking": booking}

@mcp.tool()
def cancel_hotel_order(booking_id: str, reason: str = "") -> Dict[str, Any]:
    """Drop rooms matrix inventory allocations and flag target stay logs as cancelled."""
    booking = _get_booking(booking_id)
    if booking["booking_status"] == "cancelled":
        raise ValueError(f"Cancellation lifecycle processing failure: Order target record '{booking_id}' already terminated.")

    booking["booking_status"] = "cancelled"
    booking["ticket_status"]  = "void" if booking["ticket_status"] == "issued" else booking["ticket_status"]
    booking["cancel_reason"]  = reason
    booking["cancelled_at"]   = _now()
    booking["modified_at"]    = _now()
    
    return {"booking_id": booking_id, "booking_status": "cancelled", "cancelled_at": booking["cancelled_at"]}

@mcp.tool()
def hold_hotel_booking(booking_id: str, hold_until: str) -> Dict[str, Any]:
    """Apply an immutable inventory hold shelf lock tracking record across an active reservation block."""
    booking = _get_booking(booking_id)
    if booking["booking_status"] in ("cancelled", "confirmed"):
        raise ValueError(f"Hold process blocked: Order context tracking code '{booking_id}' flags terminal status state.")

    booking["booking_status"] = "on_hold"
    booking["hold_until"]     = hold_until
    booking["modified_at"]    = _now()
    return {"booking_id": booking_id, "booking_status": "on_hold", "hold_until": hold_until}

@mcp.tool()
def hotel_booking_status(booking_id: str) -> Dict[str, Any]:
    """Retrieve full matrix statuses, balancing profiles, and traveler records for an explicit booking identification."""
    booking = _get_booking(booking_id)
    return {
        "booking_id":      booking_id,
        "booking_status":  booking["booking_status"],
        "ticket_status":   booking["ticket_status"],
        "payment_status":  booking["payment_status"],
        "refund_status":   booking["refund_status"],
        "hotel_id":        booking["hotel_id"],
        "room_type":       booking["room_type"],
        "check_in":        booking["check_in"],
        "check_out":       booking["check_out"],
        "occupancy":       booking["occupancy"],
        "board_basis":     booking["board_basis"],
        "guests":          booking["guests"],
        "total_price":     booking["total_price"],
        "created_at":      booking["created_at"],
        "modified_at":     booking["modified_at"],
    }

@mcp.tool()
def update_hotel_guests(booking_id: str, guests: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Replace or append traveler credentials, profiles, and documentation details linked to a reservation."""
    booking = _get_booking(booking_id)
    booking["guests"]      = guests
    booking["occupancy"]   = len(guests)
    booking["modified_at"] = _now()
    return {"booking_id": booking_id, "guests": booking["guests"]}

@mcp.tool()
def add_hotel_special_requests(booking_id: str, requests: List[str]) -> Dict[str, Any]:
    """Log individual non-chargeable room requests like pillow preferences or floor alignments into stay notes."""
    booking = _get_booking(booking_id)
    booking["special_requests"].extend(requests)
    booking["modified_at"] = _now()
    return {"booking_id": booking_id, "special_requests": booking["special_requests"]}


# ── 4. ANCILLARIES & TARGET LOCAL EXPERIENCES ─────────────────────────────────
@mcp.tool()
def list_hotel_ancillaries(hotel_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Enumerate extra hotel options available like breakfast sets, rollaway cribs, or express pickup runs."""
    return [
        {"category": "breakfast",      "code": "BF_BUFFET",        "name": "Breakfast Buffet",        "price": 30.0,  "currency": "USD", "per": "guest/night"},
        {"category": "extra_bed",      "code": "BED_ROLLAWAY",     "name": "Rollaway Bed",            "price": 40.0,  "currency": "USD", "per": "night"},
        {"category": "late_checkout",  "code": "LCO_4H",          "name": "Late Checkout +4h",       "price": 60.0,  "currency": "USD", "per": "booking"},
        {"category": "airport_pickup", "code": "APT_SEDAN",        "name": "Airport Pickup — Sedan",  "price": 55.0,  "currency": "USD", "per": "trip"}
    ]

@mcp.tool()
def add_hotel_ancillaries(booking_id: str, ancillaries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Attach add-on option modules and increment structural pricing values tracking on a reservation log."""
    booking = _get_booking(booking_id)
    booking["ancillaries"].extend(ancillaries)
    ancillary_total = sum(float(a.get("price", 0.0)) for a in ancillaries)
    booking["total_price"] = round(booking["total_price"] + ancillary_total, 2)
    booking["modified_at"] = _now()
    return {"booking_id": booking_id, "ancillaries": booking["ancillaries"], "total_price": booking["total_price"]}

@mcp.tool()
def list_hotel_activities(city: str, category: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
    """Query available local excursions, tickets, guided museum passages, and travel experiences around a location."""
    all_activities = [
        {"activity_id": "ACT001", "name": f"{city} City Sightseeing Tour",    "category": "tours",     "price": 45.0, "currency": "USD"},
        {"activity_id": "ACT002", "name": f"{city} Food & Wine Walking Tour", "category": "food",      "price": 65.0, "currency": "USD"},
        {"activity_id": "ACT003", "name": f"{city} Museum Pass",              "category": "culture",   "price": 35.0, "currency": "USD"},
        {"activity_id": "ACT006", "name": f"{city} Bike Tour",               "category": "adventure", "price": 38.0, "currency": "USD"}
    ]
    result = all_activities
    if category:
        result = [a for a in all_activities if a["category"].lower() == category.lower()]
    return {"city": city, "total": len(result), "activities": result[:limit]}


# ── 5. FINANCIAL REVERSALS & OFFERS VALIDATION ────────────────────────────────
@mcp.tool()
def process_hotel_refund(booking_id: str, reason: str, amount: Optional[float] = None) -> Dict[str, Any]:
    """Initiate a full or customized balance reversal processing timeline sequence against verified orders."""
    booking = _get_booking(booking_id)
    if booking["payment_status"] != "paid":
        raise ValueError(f"No settled payment reference record is recorded to track under transaction: '{booking_id}'.")
    if booking["refund_status"] in ("processing", "processed"):
        raise ValueError(f"Active transaction lockout: A refund loop is locked at '{booking['refund_status']}' on target '{booking_id}'.")

    refund_amount = amount if amount is not None else booking["total_price"]
    refund_id     = "REF-" + str(uuid.uuid4())[:8].upper()
    
    booking["refund_status"]       = "processing"
    booking["refund_id"]           = refund_id
    booking["refund_amount"]       = refund_amount
    booking["refund_reason"]       = reason
    booking["refund_requested_at"] = _now()
    booking["payment_status"]      = "refunded"
    booking["ticket_status"]       = "void"
    booking["modified_at"]         = _now()
    
    return {
        "booking_id":    booking_id,
        "refund_id":     refund_id,
        "refund_status": "processing",
        "refund_amount": refund_amount,
        "message":       "Refund initiated. Funds will be returned within 5–7 business days.",
    }

@mcp.tool()
def list_hotel_discounts() -> List[Dict[str, Any]]:
    """Fetch active operational promo validation codes running across hotel supplier channels."""
    return [
        {"code": "HOTELDEAL15", "type": "percentage", "value": 15, "description": "15% off any hotel booking"},
        {"code": "LONGSTAY20",  "type": "percentage", "value": 20, "description": "20% off stays of 7 nights or more"},
        {"code": "WEEKEND50",   "type": "fixed",      "value": 50, "description": "USD 50 off weekend stays"}
    ]

@mcp.tool()
def validate_hotel_coupon(code: str, booking_id: Optional[str] = None) -> Dict[str, Any]:
    """Verify code authenticity configurations and evaluate absolute currency savings parameters."""
    valid_codes = {
        "HOTELDEAL15": {"type": "percentage", "value": 15},
        "LONGSTAY20":  {"type": "percentage", "value": 20},
        "WEEKEND50":   {"type": "fixed",      "value": 50},
    }
    target = code.upper()
    if target not in valid_codes:
        return {"valid": False, "code": target, "message": "Invalid or expired coupon token reference."}

    discount = valid_codes[target]
    booking_price = None
    if booking_id and booking_id in _bookings:
        booking_price = _bookings[booking_id]["total_price"]

    discount_amount = None
    if booking_price is not None:
        if discount["type"] == "percentage":
            discount_amount = round(booking_price * discount["value"] / 100, 2)
        else:
            discount_amount = discount["value"]

    return {
        "valid":           True,
        "code":            target,
        "discount_type":   discount["type"],
        "discount_value":  discount["value"],
        "discount_amount": discount_amount,
    }

# ── 6. COMPLIANCE & PROPERTY DIRECTORIES ──────────────────────────────────────
@mcp.tool()
def get_hotel_rate_rules(hotel_id: str, room_type: str = "Standard", board_basis: str = "room_only") -> Dict[str, Any]:
    """Query strict property penalties, timeline windows, and cancellation bounds applied to a room selection."""
    rules_by_board = {
        "room_only":     {"rate_name": "Room Only (RO)", "refundable": True, "free_cancellation_until": "48 hours before check-in"},
        "bed_breakfast": {"rate_name": "Bed & Breakfast (BB)", "refundable": True, "free_cancellation_until": "72 hours before check-in"},
        "all_inclusive": {"rate_name": "All Inclusive (AI)", "refundable": False, "free_cancellation_until": "14 days before check-in"},
    }
    rule = rules_by_board.get(board_basis.lower())
    if not rule:
        raise ValueError(f"Unrecognized lodging board metrics encountered: '{board_basis}'")
    return {"hotel_id": hotel_id, "room_type": room_type, "board_basis": board_basis, **rule}

@mcp.tool()
def get_hotel_inventory(hotel_id: str) -> Dict[str, Any]:
    """Fetch complete structural room layout maps, property features, location details, and multimedia configurations."""
    return {
        "hotel_id": hotel_id,
        "hotel_details": {
            "name": f"Hotel {hotel_id}",
            "star_rating": 4,
            "city": "Paris",
            "country": "France",
            "check_in_time": "15:00",
            "check_out_time": "12:00"
        },
        "room_details": [
            {"room_type": "Standard Twin", "max_occupancy": 2, "price_per_night": 120.0},
            {"room_type": "Deluxe Double", "max_occupancy": 2, "price_per_night": 175.0}
        ],
        "amenities": {
            "dining": ["The Grand Restaurant", "Rooftop Bar & Lounge"],
            "connectivity": ["Free WiFi throughout"]
        }
    }

if __name__ == "__main__":
    mcp.run(transport="stdio")