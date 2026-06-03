from typing import Optional
from pydantic import BaseModel

class Traveler(BaseModel):
    first_name: str
    last_name: str
    dob: str                        # YYYY-MM-DD
    passport_number: str
    nationality: str
    gender: str = "unspecified"     # male | female | unspecified

class CreateBookingRequest(BaseModel):
    flight_id: str
    date: str                       # YYYY-MM-DD
    from_airport: str
    to_airport: str
    cabin: str = "Economy"          # Economy | Business | First
    travelers: list[Traveler] = []
    contact_email: str
    contact_phone: str = ""

class ModifyOrderRequest(BaseModel):
    change_type: str                # change_date | change_route | add_passenger | reissue_ticket
    new_date: Optional[str] = None
    new_from_airport: Optional[str] = None
    new_to_airport: Optional[str] = None
    passenger: Optional[Traveler] = None
    reason: str = ""

class PaymentRequest(BaseModel):
    payment_method: str             # credit_card | debit_card | bank_transfer | wallet
    amount: float
    currency: str = "USD"
    card_last4: Optional[str] = None
    transaction_reference: Optional[str] = None

class SpecialRequestBody(BaseModel):
    requests: list[str]             # e.g. ["wheelchair assistance", "vegetarian meal"]

class AncillaryItem(BaseModel):
    type: str                       # seat | baggage | meal | priority_boarding
    detail: str                     # e.g. "12A window seat" | "23kg extra bag" | "vegetarian"
    price: float = 0.0

class AncillaryRequest(BaseModel):
    ancillaries: list[AncillaryItem]

class RefundRequest(BaseModel):
    reason: str
    amount: Optional[float] = None  # partial refund amount; None = full refund

class CouponValidateRequest(BaseModel):
    code: str
    booking_id: Optional[str] = None
    flight_id: Optional[str] = None