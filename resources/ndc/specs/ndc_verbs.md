# NDC API Verbs Reference — IATA NDC 21.3

## Supported Verbs

### AirShopping
- **Purpose**: Search for available flight offers
- **Request**: AirShoppingRQ
- **Response**: AirShoppingRS
- **Key Request Fields**:
  - `CoreQuery/OriginDestinations/OriginDestination/Departure/AirportCode` — origin IATA code
  - `CoreQuery/OriginDestinations/OriginDestination/Arrival/AirportCode` — destination IATA code
  - `CoreQuery/OriginDestinations/OriginDestination/Departure/Date` — departure date (YYYY-MM-DD)
  - `Travelers/Traveler/AnonymousTraveler/PTC[@Quantity]` — passenger count and type (ADT=adult)
  - `Preference/CabinPreferences/CabinType/Code` — cabin class (Y=Economy, C=Business, F=First)
- **Key Response Fields**:
  - `Offer[@OfferID]` — unique offer identifier
  - `TotalAmount/SimpleCurrencyPrice[@Code]` — total price and currency
  - `FlightSegment/Departure/AirportCode` — departure airport
  - `FlightSegment/Arrival/AirportCode` — arrival airport
  - `FlightSegment/MarketingCarrier/FlightNumber` — flight number
  - `FlightSegment/Departure/Date` — departure date
  - `FlightSegment/Departure/Time` — departure time

### OrderCreate (Booking)
- **Purpose**: Create a booking / place an order for a selected offer
- **Request**: OrderCreateRQ
- **Response**: OrderCreateRS
- **Key Request Fields**:
  - `Query/Offer/OfferID` — offer ID from AirShopping response
  - `Travelers/Traveler/Individual/GivenName` — first name
  - `Travelers/Traveler/Individual/Surname` — last name
  - `Travelers/Traveler/Individual/Birthdate` — date of birth (YYYY-MM-DD)
  - `Travelers/Traveler/Individual/IdentityDocument/IdentityDocumentNumber` — passport number
  - `Travelers/Traveler/Individual/IdentityDocument/ExpiryDate` — passport expiry
  - `Travelers/Traveler/Individual/IdentityDocument/IssuingCountryCode` — nationality
  - `Travelers/Traveler/Contacts/Contact/EmailContact/Address` — email
  - `Travelers/Traveler/Contacts/Contact/PhoneContact/Number` — phone
  - `Payments/Payment/Method/PaymentCard/CardCode` — card type (VI=Visa, CA=Mastercard, AX=Amex)
  - `Payments/Payment/Method/PaymentCard/CardHolderName` — cardholder name
  - `Payments/Payment/Amount` — total amount
- **Key Response Fields**:
  - `Order/OrderID` — airline order reference
  - `Order/BookingReference/ID` — PNR / booking reference
  - `Order/OrderStatus` — CONFIRMED, TICKETED, ON_HOLD, PENDING_TICKETING
  - `Order/TicketingDeadline` — ticketing time limit (ISO-8601)
  - `Order/TotalAmount` — confirmed total price
  - `Order/TicketDocInfos/TicketDocInfo/TicketDocument/Number` — ticket number(s)

## Cabin Codes
| Code | Description |
|------|-------------|
| Y    | Economy     |
| W    | Premium Economy |
| C    | Business    |
| F    | First       |

## Passenger Type Codes (PTC)
| Code | Description |
|------|-------------|
| ADT  | Adult       |
| CHD  | Child       |
| INF  | Infant      |

## XML Namespace
All NDC 21.3 requests/responses use:
```
xmlns="http://www.iata.org/IATA/EDIST/2017.2"
```
