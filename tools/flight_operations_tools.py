
# pyrefly: ignore [missing-import]
from schemas import Traveler, AncillaryItem
from typing import Optional, List, Dict, Any
from datetime import datetime
# pyrefly: ignore [missing-import]
from openai.types.beta.realtime import conversation_item_input_audio_transcription_completed_event
from mcp.server.fastmcp import FastMCP
import pandas as pd
import logging
import os
import requests
from contextlib import asynccontextmanager
import uuid

# Configure standard Python logging 
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("search_flights")

flights_df: pd.DataFrame = pd.DataFrame()
FLIGHTS_CSV = "../resources/data/flights.csv"

# In-memory booking store  {booking_id: booking_dict}
_bookings: dict = {}

# ── Helper Functions ──────────────────────────────────────────
def _load_csv() -> pd.DataFrame:
    df = pd.read_csv(FLIGHTS_CSV)
    logging.info("Loaded %d records", len(df))
    return df

def _append_to_csv(records: list) -> None:
    try:
        pd.DataFrame(records).to_csv(FLIGHTS_CSV, mode="a", header=False, index=False)
        logging.info("Appended %d record(s) to %s", len(records), FLIGHTS_CSV)
    except Exception as e:
        logging.warning("Failed to append to %s: %s", FLIGHTS_CSV, e)

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
    global flights_df
    logging.info("Starting up flight server... Initializing dataset assets.")
    
    # Run your initial CSV loading routine here
    flights_df = _load_csv()
    
    try:
        # Hands control back over to the MCP server to begin serving tool requests
        yield 
    finally:
        # Optional: Code placed here runs right when the server shuts down
        logging.info("Shutting down flight server... Cleaning up resources.")

mcp = FastMCP("Flight Service", lifespan=server_lifespan)

# ------------------------------------------------------------------
# Airport Resolution
# ------------------------------------------------------------------

AIRPORTS = {
    "dubai": "DXB",
    "paris": "CDG",
    "london": "LHR",
    "new york": "JFK",
    "frankfurt": "FRA",
    "singapore": "SIN",
    "tokyo": "HND",
}
@mcp.tool()
def resolve_airport_code(city: str) -> dict:
    """
    Resolve city name to airport IATA code.
    """
    code = AIRPORTS.get(city.lower())

    if not code:
        return {
            "success": False,
            "message": f"No airport found for {city}"
        }

    return {
        "success": True,
        "city": city,
        "iata": code
    }

# ── External API ──────────────────────────────────────────────────────────────
def _fetch_external(from_airport: str, to: str, date: str,
                    direction: str, limit: int) -> list:
    """Calls Aviationstack-compatible API. Returns [] if not configured or on error."""
    api_key = os.getenv("FLIGHT_EXTERNAL_KEY", "")
    api_url = os.getenv("FLIGHT_EXTERNAL_URL", "")
    if not api_key or not api_url:
        logging.debug("FLIGHT_EXTERNAL_KEY/URL not set — skipping external flight API")
        return []

    url = (f"{api_url}?access_key={api_key}"
           f"&dep_iata={from_airport}&arr_iata={to}&flight_date={date}&limit={limit}")
    logging.info("Calling external flight API: %s→%s  date=%s", from_airport, to, date)
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            logging.warning("External flight API returned HTTP %d", resp.status_code)
            return []
        records = []
        for item in resp.json().get("data", []):
            dep_sched = item.get("departure", {}).get("scheduled", "")
            arr_sched = item.get("arrival",   {}).get("scheduled", "")
            records.append({
                "flight_id":        item.get("flight", {}).get("iata", "FL?"),
                "airline":          item.get("airline", {}).get("name", "Unknown"),
                "from_airport":     from_airport,
                "to_airport":       to,
                "departure_time":   dep_sched[11:16] if len(dep_sched) >= 16 else "00:00",
                "arrival_time":     arr_sched[11:16] if len(arr_sched) >= 16 else "00:00",
                "duration_minutes": 360,
                "price":            500,
                "cabin":            "Economy",
                "stops":            0,
                "available_seats":  50,
                "date":             date,
                "direction":        direction,
            })
            if len(records) >= limit:
                break
        logging.info("External flight API returned %d flight(s) for %s→%s", len(records), from_airport, to)
        if records:
            _append_to_csv(records)
        return records
    except Exception as e:
        logging.warning("External flight API call failed: %s", e)
        return []

# ── 1. FLIGHT SEARCH & INVENTORY ─────────────────────────────────────────────
@mcp.tool()
def get_flights(
    from_airport: str,
    to: str,
    date: str,
    passengers: int = 1,
    direction: str = "OUTBOUND",
    limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Search available flights through loaded CSV files, external supplier APIs, or fallback mock parameters.

    Args:
        from_airport: Origin IATA airport code, e.g. 'DXB'
        to: Destination IATA airport code, e.g. 'CDG'
        date: Scheduled departure date in format YYYY-MM-DD
        passengers: Number of traveling passengers. Defaults to 1.
        direction: Voyage flight path categorization ('OUTBOUND' or 'RETURN'). Defaults to 'OUTBOUND'.
    """
    logging.info("→ MCP TOOL  get_flights  %s→%s  date=%s  pax=%d  direction=%s",
             from_airport, to, date, passengers, direction)

    source = "mock"
    records = []

    # 1. Search locally loaded CSV Dataframe
    if not flights_df.empty:
        filtered = flights_df[
            (flights_df["from_airport"].str.upper() == from_airport.upper()) &
            (flights_df["to_airport"].str.upper()   == to.upper())
        ].head(limit)
        if not filtered.empty:
            records = filtered.to_dict(orient="records")
            for f in records:
                f["date"]      = date
                f["direction"] = direction
            source = "csv"
        else:
            logging.warning("  CSV miss for %s→%s — trying external API", from_airport, to)

    # 2. Fallback to live External API
    if not records:
        records = _fetch_external(from_airport, to, date, direction, limit)
        if records:
            source = "external"

    # 3. Last fallback to built-in Mock arrays
    if not records:
        logging.warning("  No data from CSV or external API — using mock data")
        records = [
            {"flight_id": "EK073", "airline": "Emirates",      "from_airport": from_airport, "to_airport": to, "departure_time": "08:30", "arrival_time": "13:45", "duration_minutes": 375, "price": 850, "cabin": "Economy", "stops": 0, "available_seats": 42, "date": date, "direction": direction},
            {"flight_id": "QR039", "airline": "Qatar Airways", "from_airport": from_airport, "to_airport": to, "departure_time": "10:00", "arrival_time": "16:30", "duration_minutes": 450, "price": 720, "cabin": "Economy", "stops": 1, "available_seats": 18, "date": date, "direction": direction},
            {"flight_id": "AF568", "airline": "Air France",    "from_airport": from_airport, "to_airport": to, "departure_time": "14:15", "arrival_time": "19:00", "duration_minutes": 405, "price": 680, "cabin": "Economy", "stops": 0, "available_seats": 55, "date": date, "direction": direction},
            {"flight_id": "LH632", "airline": "Lufthansa",     "from_airport": from_airport, "to_airport": to, "departure_time": "11:00", "arrival_time": "17:30", "duration_minutes": 450, "price": 640, "cabin": "Economy", "stops": 1, "available_seats": 30, "date": date, "direction": direction},
            {"flight_id": "FZ551", "airline": "flydubai",      "from_airport": from_airport, "to_airport": to, "departure_time": "22:00", "arrival_time": "07:00", "duration_minutes": 480, "price": 490, "cabin": "Economy", "stops": 0, "available_seats": 67, "date": date, "direction": direction},
        ][:limit]

    logging.info("← MCP TOOL get_flights  %s→%s  source=%-8s  returned=%d flight(s)",
             from_airport, to, source, len(records))
    return records

# ── 2. BOOKING & Issue Tickets ─────────────────────────────────────────────
@mcp.tool()
def create_booking(
    flight_id: str,
    date: str,
    from_airport: str,
    to_airport: str,
    contact_email: str,
    cabin: str = "Economy",
    travelers: List[Traveler] = [],
    contact_phone: str = ""
) -> Dict[str, Any]:
    """
    Create a new flight booking allocation (initial status is set to 'pending' until a payment is settled).

    Args:
        flight_id: The identifier code of the target flight (e.g., 'EK073').
        date: Departure date formatted as YYYY-MM-DD.
        from_airport: Origin IATA airport code (e.g., 'DXB').
        to_airport: Destination IATA airport code (e.g., 'CDG').
        contact_email: Primary contact email address for booking updates.
        cabin: The class of service ('Economy', 'Business', or 'First'). Defaults to 'Economy'.
        travelers: A structured list containing information for each traveling passenger.
        contact_phone: Optional phone number for customer contact alerts.
    """
    booking_id = "FBK-" + str(uuid.uuid4())[:8].upper()
    
    booking = {
        "booking_id":      booking_id,
        "type":            "flight",
        "flight_id":       flight_id,
        "date":            date,
        "from_airport":    from_airport,
        "to_airport":      to_airport,
        "cabin":           cabin,
        "travelers":       [t.model_dump() for t in travelers],
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
    logger.info("Created booking %s for flight %s via MCP Tool", booking_id, flight_id)
    return booking

@mcp.tool()
def issue_ticket(booking_id: str) -> Dict[str, Any]:
    """
    Issue official ticket numbers and finalize a confirmed (fully paid) booking.

    Args:
        booking_id: The unique flight booking reference code (e.g., 'FBK-A1B2C3D4').
    """
    booking = _get_booking(booking_id)
    
    # In MCP, raise native exceptions instead of HTTPExceptions
    if booking["payment_status"] != "paid":
        raise ValueError(f"Payment must be completed before issuing ticket for booking '{booking_id}'")
        
    if booking["ticket_status"] == "issued":
        raise ValueError(f"Ticket has already been issued for booking '{booking_id}'")

    ticket_number = "TKT-" + str(uuid.uuid4())[:10].upper()
    
    booking["ticket_status"]  = "issued"
    booking["booking_status"] = "confirmed"
    booking["ticket_number"]  = ticket_number
    booking["issued_at"]      = _now()
    booking["modified_at"]    = _now()
    
    logger.info("Ticket issued for booking %s — ticket %s via MCP Tool", booking_id, ticket_number)
    
    return {
        "booking_id": booking_id, 
        "ticket_number": ticket_number, 
        "ticket_status": "issued"
    }

# ── 3. PAYMENT PROCESSING & VALIDATION ──────────────────────────────────────────────
@mcp.tool()
def handle_payment(
    booking_id: str,
    payment_method: str,
    amount: float,
    currency: str = "USD",
    transaction_reference: Optional[str] = None
) -> Dict[str, Any]:
    """
    Process and settle a pending payment transaction for a flight booking.

    Args:
        booking_id: The unique target booking reference (e.g., 'FBK-A1B2C3D4').
        payment_method: Accepted method ('credit_card', 'debit_card', 'bank_transfer', 'wallet').
        amount: Price to charge matching the total reservation value.
        currency: Three-letter ISO currency code. Defaults to 'USD'.
        transaction_reference: Optional pre-generated clearing network identifier.
    """
    booking = _get_booking(booking_id)
    if booking["payment_status"] == "paid":
        raise ValueError(f"Booking '{booking_id}' is already settled and paid.")

    transaction_id = transaction_reference or ("TXN-" + str(uuid.uuid4())[:10].upper())
    
    booking["payment_status"]    = "paid"
    booking["booking_status"]    = "confirmed"
    booking["total_price"]       = amount
    booking["payment_method"]    = payment_method
    booking["payment_currency"]  = currency
    booking["transaction_id"]    = transaction_id
    booking["payment_timestamp"] = _now()
    booking["modified_at"]       = _now()
    
    logger.info("Payment processed for booking %s — txn %s", booking_id, transaction_id)
    return {
        "booking_id":     booking_id,
        "transaction_id": transaction_id,
        "payment_status": "paid",
        "amount":         amount,
        "currency":       currency,
    }

# ── 4. ORDER AMENDMENTS & STATUS ──────────────────────────────────────────────
@mcp.tool()
def modify_order(
    booking_id: str,
    change_type: str,
    new_date: Optional[str] = None,
    new_from_airport: Optional[str] = None,
    new_to_airport: Optional[str] = None,
    passenger: Optional[Traveler] = None
) -> Dict[str, Any]:
    """
    Modify an existing flight itinerary, date routing, or passenger manifestation metrics.

    Args:
        booking_id: The unique target booking reference (e.g., 'FBK-A1B2C3D4').
        change_type: Specific alteration: 'change_date', 'change_route', 'add_passenger', 'reissue_ticket'.
        new_date: Updated departure window formatted as YYYY-MM-DD (Required for 'change_date').
        new_from_airport: New origin IATA airport code (Used in 'change_route').
        new_to_airport: New destination IATA airport code (Used in 'change_route').
        passenger: Structured dataset object profile representing the extra traveler.
    """
    booking = _get_booking(booking_id)
    if booking["booking_status"] == "cancelled":
        raise ValueError(f"Cannot modify a permanently cancelled booking context: '{booking_id}'")

    if change_type == "change_date":
        if not new_date:
            raise ValueError("Parameter 'new_date' is explicitly required for 'change_date' operations.")
        booking["date"] = new_date
        booking["ticket_status"] = "void"

    elif change_type == "change_route":
        if new_from_airport:
            booking["from_airport"] = new_from_airport
        if new_to_airport:
            booking["to_airport"] = new_to_airport
        booking["ticket_status"] = "void"

    elif change_type == "add_passenger":
        if not passenger:
            raise ValueError("Structured 'passenger' profile is required for 'add_passenger' operations.")
        booking["travelers"].append(passenger.model_dump())

    elif change_type == "reissue_ticket":
        if booking["ticket_status"] not in ("issued", "void"):
            raise ValueError(f"No active or voided ticket instance available to reissue on order '{booking_id}'.")
        new_ticket = "TKT-" + str(uuid.uuid4())[:10].upper()
        booking["ticket_status"] = "issued"
        booking["ticket_number"] = new_ticket
        booking["reissued_at"]   = _now()

    else:
        raise ValueError(f"Unknown change_type parameter action code encountered: '{change_type}'")

    booking["modified_at"] = _now()
    logger.info("Order %s modified: change_type=%s", booking_id, change_type)
    return {"booking_id": booking_id, "change_type": change_type, "booking": booking}

@mcp.tool()
def cancel_order(booking_id: str, reason: str = "") -> Dict[str, Any]:
    """
    Cancel an active booking slot and clear downstream tracking references.

    Args:
        booking_id: Unique target booking reference.
        reason: Explanatory context string detailing why the cancel transaction was requested.
    """
    booking = _get_booking(booking_id)
    if booking["booking_status"] == "cancelled":
        raise ValueError(f"Booking allocation entry '{booking_id}' has already been marked cancelled.")

    booking["booking_status"] = "cancelled"
    booking["ticket_status"]  = "void" if booking["ticket_status"] == "issued" else booking["ticket_status"]
    booking["cancel_reason"]  = reason
    booking["cancelled_at"]   = _now()
    booking["modified_at"]    = _now()
    
    logger.info("Booking %s cancelled via tool directive.", booking_id)
    return {
        "booking_id": booking_id, 
        "booking_status": "cancelled", 
        "cancelled_at": booking["cancelled_at"]
    }

@mcp.tool()
def hold_order(booking_id: str, hold_until: str) -> Dict[str, Any]:
    """
    Place a temporary runtime reservation hold block on an existing booking allocation.

    Args:
        booking_id: Unique target booking reference.
        hold_until: Absolute expiration date-time metric schema string formatted as YYYY-MM-DDTHH:MM:SSZ.
    """
    booking = _get_booking(booking_id)
    if booking["booking_status"] in ("cancelled", "confirmed"):
        raise ValueError(f"Cannot request retention lock hold state for a '{booking['booking_status']}' booking order.")

    booking["booking_status"] = "on_hold"
    booking["hold_until"]     = hold_until
    booking["modified_at"]    = _now()
    
    logger.info("Booking %s placed on freeze lock state until %s", booking_id, hold_until)
    return {"booking_id": booking_id, "booking_status": "on_hold", "hold_until": hold_until}


@mcp.tool()
def order_status(booking_id: str) -> Dict[str, Any]:
    """
    Query the active processing state matrix parameters for an explicit order record.
    Returns: booking_status (confirmed|pending|cancelled|on_hold), ticket_status, and payment metrics.
    """
    booking = _get_booking(booking_id)
    return {
        "booking_id":     booking_id,
        "booking_status": booking["booking_status"],
        "ticket_status":  booking["ticket_status"],
        "payment_status": booking["payment_status"],
        "refund_status":  booking["refund_status"],
        "flight_id":      booking["flight_id"],
        "date":           booking["date"],
        "from_airport":   booking["from_airport"],
        "to_airport":     booking["to_airport"],
        "cabin":          booking["cabin"],
        "travelers":      booking["travelers"],
        "total_price":    booking["total_price"],
        "created_at":     booking["created_at"],
        "modified_at":    booking["modified_at"],
    }

# ── 5. ANCILLARY SERVICES MANAGEMENT ──────────────────────────────────────────
@mcp.tool()
def list_ancillaries(cabin: str = "Economy", flight_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Enumerate catalog records of optional ancillary products available for a given travel cabin tier.
    """
    ancillaries = [
        {"category": "seat",             "code": "SEAT_WINDOW",     "name": "Window Seat",            "price": 15.0,  "currency": "USD"},
        {"category": "seat",             "code": "SEAT_AISLE",      "name": "Aisle Seat",             "price": 12.0,  "currency": "USD"},
        {"category": "seat",             "code": "SEAT_EXIT_ROW",   "name": "Exit Row Seat",          "price": 35.0,  "currency": "USD"},
        {"category": "baggage",          "code": "BAG_15KG",        "name": "Extra Bag 15kg",         "price": 40.0,  "currency": "USD"},
        {"category": "baggage",          "code": "BAG_23KG",        "name": "Extra Bag 23kg",         "price": 60.0,  "currency": "USD"},
        {"category": "meal",             "code": "MEAL_VEGETARIAN", "name": "Vegetarian Meal",        "price": 12.0,  "currency": "USD"},
        {"category": "meal",             "code": "MEAL_HALAL",      "name": "Halal Meal",             "price": 12.0,  "currency": "USD"},
        {"category": "priority_boarding","code": "PB_STANDARD",     "name": "Priority Boarding",      "price": 18.0,  "currency": "USD"},
    ]
    return {"flight_id": flight_id, "cabin": cabin, "ancillaries": ancillaries}

@mcp.tool()
def add_ancillaries(booking_id: str, ancillaries: List[AncillaryItem]) -> Dict[str, Any]:
    """
    Attach structural ancillary items (e.g. seats, meal kits, heavy bags) to a reservation itinerary.

    Args:
        booking_id: Unique target booking reference.
        ancillaries: A collection array containing typed AncillaryItem structures.
    """
    booking = _get_booking(booking_id)
    items = [a.model_dump() for a in ancillaries]
    
    booking["ancillaries"].extend(items)
    ancillary_total = sum(a["price"] for a in items)
    booking["total_price"] = round(booking["total_price"] + ancillary_total, 2)
    booking["modified_at"] = _now()
    
    logger.info("Added %d ancillary line items to booking reference %s", len(items), booking_id)
    return {"booking_id": booking_id, "ancillaries": booking["ancillaries"], "total_price": booking["total_price"]}

@mcp.tool()
def add_special_requests(booking_id: str, requests: List[str]) -> Dict[str, Any]:
    """
    Register non-chargeable special requests like wheelchair transit assistance or cabin requirements.
    """
    booking = _get_booking(booking_id)
    booking["special_requests"].extend(requests)
    booking["modified_at"] = _now()
    return {"booking_id": booking_id, "special_requests": booking["special_requests"]}

@mcp.tool()
def update_travelers(booking_id: str, travelers: List[Traveler]) -> Dict[str, Any]:
    """
    Overwrite or replace the traveler documentation logs linked with an active target booking.
    """
    booking = _get_booking(booking_id)
    booking["travelers"] = [t.model_dump() for t in travelers]
    booking["modified_at"] = _now()
    return {"booking_id": booking_id, "travelers": booking["travelers"]}

# ── 6. FINANCIAL ADJUSTMENTS & VALIDATION ─────────────────────────────────────
@mcp.tool()
def process_refund(booking_id: str, reason: str, amount: Optional[float] = None) -> Dict[str, Any]:
    """
    Trigger partial or full payment reversal processing workflows against settled orders.

    Args:
        booking_id: Unique target booking reference.
        reason: Operational logging documentation detailing context behind payment forfeiture.
        amount: Explicit transaction value to credit back. If not passed, defaults to full ticket balance.
    """
    booking = _get_booking(booking_id)
    if booking["payment_status"] != "paid":
        raise ValueError(f"No authenticated, cleared payment ledger row discovered to reverse for tracking entry '{booking_id}'.")
    if booking["refund_status"] in ("processing", "processed"):
        raise ValueError(f"Refund pipeline sequence has already been locked for reference '{booking_id}'. Status context: {booking['refund_status']}")

    refund_amount = amount if amount is not None else booking["total_price"]
    refund_id     = "REF-" + str(uuid.uuid4())[:8].upper()
    
    booking["refund_status"]       = "processing"
    booking["refund_id"]           = refund_id
    booking["refund_amount"]       = refund_amount
    booking["refund_reason"]       = reason
    booking["refund_requested_at"] = _now()
    booking["payment_status"]      = "refunded"
    booking["ticket_status"]       = "refunded"
    booking["modified_at"]         = _now()
    
    logger.info("Refund tracking code %s cleared for allocation reference %s", refund_id, booking_id)
    return {
        "booking_id":    booking_id,
        "refund_id":     refund_id,
        "refund_status": "processing",
        "refund_amount": refund_amount,
        "message":       "Refund initiated. Funds will be returned within 5–7 business days.",
    }

@mcp.tool()
def list_discounts(cabin: Optional[str] = None, flight_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Enumerate active campaign discount code promotions matching available constraints.
    """
    discounts = [
        {"code": "EARLYBIRD10",  "type": "percentage", "value": 10,  "applicable_cabins": ["Economy"]},
        {"code": "BUSINESS20",   "type": "percentage", "value": 20,  "applicable_cabins": ["Business"]},
        {"code": "SUMMER50",     "type": "fixed",      "value": 50,  "applicable_cabins": ["Economy", "Business", "First"]},
        {"code": "LOYALFLY",     "type": "percentage", "value": 15,  "applicable_cabins": ["Economy", "Business", "First"]},
    ]
    if cabin:
        discounts = [d for d in discounts if cabin in d["applicable_cabins"]]
    return {"discounts": discounts}

@mcp.tool()
def validate_coupon(code: str, booking_id: Optional[str] = None, flight_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Validate standard marketing voucher codes against pricing balances to assess eligibility rules.
    """
    valid_codes = {
        "EARLYBIRD10":  {"type": "percentage", "value": 10},
        "BUSINESS20":   {"type": "percentage", "value": 20},
        "SUMMER50":     {"type": "fixed",      "value": 50},
        "LOYALFLY":     {"type": "percentage", "value": 15},
    }
    target_code = code.upper()
    if target_code not in valid_codes:
        return {"valid": False, "code": target_code, "message": "Invalid or expired coupon code tag."}

    discount = valid_codes[target_code]
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
        "code":            target_code,
        "discount_type":   discount["type"],
        "discount_value":  discount["value"],
        "discount_amount": discount_amount,
    }

# ── 7. METADATA & COMPLIANCE RULES ────────────────────────────────────────────
@mcp.tool()
def get_fare_rules(flight_id: str, cabin: str = "Economy") -> Dict[str, Any]:
    """
    Query legal rules, change penalties, baggage caps, and cancellation fees for a specified cabin tier.
    """
    rules_by_cabin = {
        "Economy": {"refundable": False, "changeable": True,  "change_fee": 75.0,  "cancel_fee": 150.0},
        "Business": {"refundable": True,  "changeable": True,  "change_fee": 0.0,   "cancel_fee": 0.0},
        "First":    {"refundable": True,  "changeable": True,  "change_fee": 0.0,   "cancel_fee": 0.0}
    }
    rule = rules_by_cabin.get(cabin)
    if not rule:
        raise ValueError(f"Unknown destination service cabin profile classification requested: '{cabin}'")
    return {"flight_id": flight_id, "cabin": cabin, **rule}

@mcp.tool()
def get_inventory(flight_id: str) -> Dict[str, Any]:
    """
    Fetch structural technical aircraft logs, configuration matrices, and baggage boundaries for a flight.
    """
    return {
        "flight_id": flight_id,
        "aircraft_info": {
            "aircraft_type": "Boeing 777-300ER",
            "registration":  "A6-EBP",
            "total_seats":   360,
            "wifi_available": True
        }
    }

# ── Health Check ─────────────────────────────────────────────────────────────
@mcp.tool()
def health() -> dict:
    """
    Health check.
    """
    return {
        "status": "ok",
        "service": "travel-mcp"
    }

# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run(transport="stdio")