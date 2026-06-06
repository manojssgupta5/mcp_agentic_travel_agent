# Autonomous Multi-Agent Travel Planner Platform

An enterprise-grade, agentic orchestration ecosystem powered by the **Model Context Protocol (MCP)**. This platform utilizes a multi-agent framework paired with specialized micro-servers to autonomously resolve complex, non-deterministic natural language travel requests into concrete domain operations—handling airport entity resolution, real-time inventory queries (flights and lodging), pricing rule verification, schema-validated booking contracts, and multi-channel transactional notifications.

---

## 1. Core Architectural Framework

The platform transitions away from brittle, hardcoded integration loops to an event-driven, autonomous tool-discovery topology. By leveraging the Model Context Protocol (MCP), individual domain domains are completely decoupled into self-contained, stateless micro-servers that expose their capabilities, data validation schemas, and physical data resources dynamically to an intelligent central coordinator.

### System Topography

```
                    ┌──────────────────────────────────────────┐
                    │       User Interaction / Orchestrator    │
                    │      (Jupyter Loop / Runner Execution)   │
                    └────────────────────┬─────────────────────┘
                                         │
                                         ▼
                    ┌──────────────────────────────────────────┐
                    │      Central AI Agent Coordinator        │
                    │   (Llama-3.3-70B via Groq Inference)     │
                    └────────────────────┬─────────────────────┘
                                         │
                 ┌───────────────────────┴───────────────────────┐
                 ▼ (Model Context Protocol - Stdio Transport Layer)  ▼
    ┌───────────────────────────┐                   ┌───────────────────────────┐
    │    Airport Lookup MCP     │                   │   Flight Operations MCP   │
    │  (Multi-Tier Cache/API)   │                   │  (Inventory & Rule Core)  │
    └────────────┬──────────────┘                   └────────────┬──────────────┘
                 │                                               │
                 ├─ SQLite DB (Local Cache)                      ├─ flights.csv Data Pool
                 └─ IATACodeAirport.csv Backend                  └─ Pydantic Rule Engine
                                                                 
    ┌───────────────────────────┐                   ┌───────────────────────────┐
    │   Hotel Operations MCP    │                   │   Push Notification MCP   │
    │ (Inventory/Board Metrics) │                   │  (External Gateway Hub)   │
    └────────────┬──────────────┘                   └────────────┬──────────────┘
                 │                                               │
                 ├─ hotels.csv Data Pool                         └─ Pushover REST API
                 └─ Room Layout Matrices                            (Token/User Scoped)
```

### Strategic Component Design

1. **Central Intelligence Coordinator (`agentic_travel_agent.ipynb`)**: Actively manages the goal-seeking loop. Utilizing the `openai-agents` orchestration framework and `llama-3.3-70b-versatile`, it breaks down complex user prompts into multi-step execution graphs. It uses runtime protocol reflection to inspect available tools across all active MCP connections, executing tool-calls, parsing responses, and maintaining historical memory.
2. **Decoupled Domain Micro-Servers (FastMCP Framework)**: Each micro-server functions as an independent bounded context. Communication takes place across standard input/output (`stdio`) transport channels using the standardized MCP JSON-RPC protocol specification, which isolates data storage methods and external dependencies.

---

## 2. Detailed Component Deep-Dive

### A. Airport Entity Resolution Server (`search_airport.py`)
This micro-server manages the translation of natural language city names or airport indicators into compliant 3-letter IATA codes. It implements a robust, three-tiered read-allocation strategy designed to protect external API rate limits while maintaining data accuracy:

* **Tier 1: Local Persistent Cache**: Queries a local SQLite implementation (`./memory/iata_code_lookup.db:airport_cache`). If an active cache match exists, the serialized payload is returned instantaneously with a source attribution header.
* **Tier 2: Embedded Vector/Relational Fallback**: On a cache miss, the execution drops back to parse a local file-system collection (`./data/IATACodeAirport.csv`) via Pandas, isolating correct string representations using explicit token filters.
* **Tier 3: Remote Network Fallback**: If local datasets fail to resolve the entity, the server initiates an outbound HTTPS call to an upstream authoritative airport directory API, caching the result in SQLite upon return.

### B. Flight Operations Engine (`flight_operations_tools.py`)
Exposes inventory metrics and legal-fare parameters for airlines worldwide. Rather than performing basic CRUD modifications against the underlying file system (`flights.csv`), it provides semantic data resolution tools:
* `get_flight_rules`: Extracts change penalties, baggage restrictions, and cancellation metrics filtered by explicit cabin tier designations (`Economy`, `Business`, `First`).
* `get_inventory`: Pulls aircraft configuration records (e.g., Boeing 777-300ER), active registration markers, and onboard asset metadata (e.g., Wi-Fi availability maps).
* `health`: Exposes operational readiness states to the central orchestration manager.

### C. Lodging & Board Operations Server (`search_hotels.py`)
Provides access to global hospitality resources using the `hotels.csv` dataset. Key components include:
* **Polymorphic Rate Resolution**: Resolves pricing variations dynamically based on the requested board basis (e.g., *Bed & Breakfast (BB)*, *All Inclusive (AI)*), embedding cancellation penalty logic directly into the returned payloads.
* **Structural Layout Inventory Maps**: Translates structural configurations (e.g., standard occupancy bounds, room layout pricing matrices) to ensure the planning agent cannot construct invalid booking proposals.

### D. System Notification Gateway (`push_server.py`)
An outbound transactional communication gateway integrated with the Pushover REST infrastructure. It acts as an isolation barrier between the core planning agents and external communication links:
* Replaces loose text formatting with structured data models built on Pydantic (`PushModelArgs`).
* Handles environment-scoped authentications (`PUSHOVER_USER`, `PUSHOVER_TOKEN`) to safely deliver multi-device notifications upon successful workflow completion.

---

## 3. Data Models & Validation Contracts

All domain structures use strict compile-time or runtime Pydantic validation boundaries defined in `schemas.py`. This ensures that all data moving between autonomous agents and core databases is structurally sound and free from injection risks.

### Core Domain Schema Mappings

#### 1. Traveler Identity Record (`Traveler`)
Keeps track of mandatory international transport verification metrics.
| Field Name | Data Type | Validation / Constraints | Description |
| :--- | :--- | :--- | :--- |
| `first_name` | `str` | Non-Empty | Given names matching passport exactly. |
| `last_name` | `str` | Non-Empty | Surname matching passport exactly. |
| `dob` | `str` | ISO Format (`YYYY-MM-DD`) | Date of birth. |
| `passport_number` | `str` | Alphanumeric String | International travel passport identifier. |
| `nationality` | `str` | ISO Country / Text | Issuing state nationality. |
| `gender` | `str` | Default: `"unspecified"` | `male` \| `female` \| `unspecified` |

#### 2. Booking Generation Intent (`CreateBookingRequest`)
Represents the transactional state when creating a flight itinerary reservation.
| Field Name | Data Type | Validation / Constraints | Description |
| :--- | :--- | :--- | :--- |
| `flight_id` | `str` | Primary Key Reference | Links to target record in `flights.csv`. |
| `date` | `str` | ISO Format (`YYYY-MM-DD`) | Flight departure schedule. |
| `from_airport` | `str` | 3-Char Alpha (`IATA`) | Origin location airport code. |
| `to_airport` | `str` | 3-Char Alpha (`IATA`) | Destination location airport code. |
| `cabin` | `str` | Default: `"Economy"` | `Economy` \| `Business` \| `First` |
| `travelers` | `list[Traveler]`| Size $\ge 1$ | Array of traveler identity references. |
| `contact_email`| `str` | Valid Email Pattern | Principal contact email address. |
| `contact_phone`| `str` | Optional String | Phone number for real-time notifications. |

#### 3. Payment Settlement Request (`PaymentRequest`)
Defines processing terms before routing variables to external financial gateways.
| Field Name | Data Type | Validation / Constraints | Description |
| :--- | :--- | :--- | :--- |
| `payment_method`| `str` | Explicit Set Constraints | `credit_card` \| `debit_card` \| `wallet` |
| `amount` | `float` | Value $> 0.00$ | Absolute financial processing cost. |
| `currency` | `str` | Default: `"USD"` (3-Char) | ISO currency code specification. |
| `card_last4` | `Optional[str]`| Length == 4 | Last four digits of card for ledger trails. |
| `transaction_reference` | `Optional[str]` | Unique String | Tracking identifier from external processor. |

---

## 4. End-to-End Operational Lifecycle

The flow below details how the platform handles an unformatted natural language request, coordinates across multiple specialized MCP micro-servers, and executes the complete travel planning workflow:

```
[User Request Ingress]
"Plan travel from Dubai to London for 2 adults on 20-May..."
          │
          ▼
┌────────────────────────────────────────────────────────┐
│ Central Orchestrator Loop                              │
│ 1. Invokes Llama-3.3-70B on Groq Base Engine           │
│ 2. Parses query for missing constraints                │
└─────────┬──────────────────────────────────────────────┘
          │
          ├─► [Tool Call 1: Airport Lookup MCP] ──► Resolves 'Dubai' to DXB, 'London' to LHR
          ├─► [Tool Call 2: Flight Operations MCP] ─► Queries flights.csv for optimal routes
          ├─► [Tool Call 3: Hotel Operations MCP] ──► Extracts lodging options from hotels.csv
          │
          ▼
┌────────────────────────────────────────────────────────┐
│ Constraint Aggregator & Validation                     │
│ 1. Evaluates flight/hotel prices and available seats   │
│ 2. Validates payloads against Pydantic definitions     │
└─────────┬──────────────────────────────────────────────┘
          │
          ▼
┌────────────────────────────────────────────────────────┐
│ Workflow Finalization                                  │
│ 1. Generates structured markdown itinerary response    │
│ 2. Triggers Push Notification MCP (Pushover Gateway)   │
└────────────────────────────────────────────────────────┘
```

### Process Sequence Breakdown

1. **Ingress and Parsing**: The customer inputs a target request: *"Plan travel from Dubai to London, for 2 adults, starting from Dubai on 20-May, returning from London on 25-May, find the hotel, push notification with result"*.
2. **Entity Resolution Engine**: The agent realizes it lacks structured destination codes. It triggers `lookup_airport` for both "Dubai" and "London", receiving verified IATA structures (`DXB` and `LHR`) from the Airport Lookup MCP server.
3. **Inventory Evaluation**: The agent queries the Flight Operations MCP using the resolved location markers to filter matching options in `flights.csv`. Concurrently, it invokes `get_hotel_inventory` on the Hotel Operations server to isolate available hotel rooms in the target destination.
4. **Validation and Mapping**: The model aggregates the raw responses, filters out operations that fail structural constraints (e.g., cabins with zero available seats or non-matching dates), and validates the variables against the schemas defined in `schemas.py`.
5. **Output Delivery**: The system maps out a clear, reader-friendly Markdown summary detailing all selected transit and accommodation paths. Finally, it formats a transactional alert, invoking the Push Notification MCP server to deliver a push notification to the user's mobile device via the Pushover REST gateway.

---

## 5. Deployment & Configuration Manual

### System Requirements
* **Runtime**: Python $\ge 3.12$
* **Dependency Management**: UV or Pipenv (Utilizes native inline `pyproject.toml` configurations)

### Step 1: Environment Variables Setup
Create a `.env` file in the root directory of the project to configure your access keys and API endpoints:

```bash
# Core LLM Provider (Groq Cloud Platform API Services)
GROQ_API_KEY="gsk_yX..."

# Multi-Channel Alert Gateway (Pushover Service Parameters)
PUSHOVER_USER="u8b3..."
PUSHOVER_TOKEN="az92..."
```

### Step 2: System Installation & Dependencies
Using `uv` to install the package constraints specified inside `pyproject.toml`:

```bash
# Install package dependencies and build the virtual environment
uv sync

# Activate the virtual environment
source .venv/bin/activate
```

### Step 3: Preparing Database Resources
Initialize the airport lookup SQLite table structure by running the internal migration function:

```python
import sqlite3
from pathlib import Path

DB_FILE = "./memory/iata_code_lookup.db"
Path("./memory").mkdir(parents=True, exist_ok=True)
conn = sqlite3.connect(DB_FILE)
conn.execute("""
    CREATE TABLE IF NOT EXISTS airport_cache (
        iata_code TEXT PRIMARY KEY,
        payload TEXT NOT NULL
    )
""")
conn.commit()
conn.close()
print("Database initialized successfully.")
```

### Step 4: Executing the Autonomous Agent Loop
Run the central multi-agent execution script via the command line or within an interactive Jupyter notebook:

```bash
# Run using the interactive Jupyter console loop
uv run jupyter notebook agentic_travel_agent.ipynb
```

---

## 6. Strategic Enhancements Roadmap

### A. Workflow Gateway & Deterministic Orchestration
Current architecture allows the AI agent to directly decide and invoke MCP tools. While this works well for prototyping, production systems require stronger control over workflow execution, security validation, compliance, and operational reliability.
Future versions of the platform will introduce a centralized workflow gateway and orchestration layer between the AI agent and MCP services. 

This gateway will function as a deterministic policy broker: inspecting LLM tool-calls against structural rule graphs, checking runtime permissions, enforcing strict data compliance boundaries, and mapping non-deterministic agent outputs into reproducible state workflows managed by an enterprise engine like Temporal.io.

### B. Additional Production Improvements
* **Distributed Opentelemetry (OTel) Tracing Triggers**: Instrumenting the system with OpenTelemetry to track execution traces across the LLM runner loop and all connected stdio/HTTP MCP micro-servers, enabling clear visibility into latency and performance bottlenecks.
* **Vector-Driven Semantic Search**: Upgrading the airport lookup and hotel filtering services from simple text matching to semantic similarity searches by storing dense data embeddings in a vector database like Qdrant.
* **Resilient Outbox Event Dispatching**: Implementing a Transactional Outbox pattern backed by Kafka within the booking workflow. This ensures that any status mutations to local file stores or databases are reliably broadcast to downstream fulfillment systems, avoiding data sync issues during network drops.
* **Multi-Layer Caching & Predictive TTL Management**: Establish a strict, multi-tiered caching strategy to intercept redundant requests before they strain system
