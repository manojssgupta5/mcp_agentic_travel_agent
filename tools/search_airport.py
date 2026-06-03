# tools/airport_lookup_mcp.py

# pyrefly: ignore [missing-import]
from schemas import Traveler, AncillaryItem
from mcp.server.fastmcp import FastMCP
import sqlite3
import pandas as pd
import requests
import json
from pathlib import Path

mcp = FastMCP("airport_lookup")

DB_FILE = "./memory/iata_code_lookup.db"
CSV_FILE = "./data/IATACodeAirport.csv"


def init_db():
    Path("./memory").mkdir(
        parents=True,
        exist_ok=True
    )

    conn = sqlite3.connect(DB_FILE)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS airport_cache (
            iata_code TEXT PRIMARY KEY,
            payload TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


@mcp.tool()
def lookup_airport(iata_code: str) -> dict:

    conn = sqlite3.connect(DB_FILE)

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT payload
        FROM airport_cache
        WHERE iata_code = ?
        """,
        (iata_code.upper(),)
    )

    row = cursor.fetchone()

    if row:
        conn.close()

        return {
            "source": "cache",
            "data": json.loads(row[0])
        }

    df = pd.read_csv(CSV_FILE)

    result = df[
        df["iata_code"]
        .astype(str)
        .str.upper()
        == iata_code.upper()
    ]

    if not result.empty:

        data = result.iloc[0].to_dict()

        cursor.execute(
            """
            INSERT OR REPLACE
            INTO airport_cache
            VALUES (?,?)
            """,
            (
                iata_code.upper(),
                json.dumps(data)
            )
        )

        conn.commit()
        conn.close()

        return {
            "source": "csv",
            "data": data
        }

    response = requests.get(
        f"https://your-api-host/airport/{iata_code}",
        timeout=10
    )

    if response.status_code == 200:

        data = response.json()

        cursor.execute(
            """
            INSERT OR REPLACE
            INTO airport_cache
            VALUES (?,?)
            """,
            (
                iata_code.upper(),
                json.dumps(data)
            )
        )

        conn.commit()

        conn.close()

        return {
            "source": "api",
            "data": data
        }

    conn.close()

    return {
        "source": "not_found",
        "data": None
    }


if __name__ == "__main__":
    init_db()
    mcp.run(transport="stdio")