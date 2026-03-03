"""
Location Extractor — extracts addresses/locations from IR document chunks,
geocodes them using a bundled India geocoding dictionary, and stores in SQL Server.

Provides geographic map data for the Connections Map tab (Location Map view).
"""

from typing import List, Dict, Any, Optional, Tuple

import pyodbc

from ollama_client import ollama_chat
from config import PDF_MODEL
from entity_graph import _find_balanced_json_object
from mssql_db import get_conn, _fetchone, _fetchall


# ---------------------------------------------------------------------------
# MSSQL Schema Setup
# ---------------------------------------------------------------------------
def _get_conn() -> pyodbc.Connection:
    return get_conn()


def init_db():
    conn = _get_conn()

    conn.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'doc_locations'
        )
        CREATE TABLE doc_locations (
            id            INT IDENTITY(1,1) PRIMARY KEY,
            doc_id        NVARCHAR(500)  NOT NULL,
            doc_name      NVARCHAR(500)  NOT NULL,
            person_name   NVARCHAR(300)  NOT NULL DEFAULT '',
            address_text  NVARCHAR(MAX)  NOT NULL DEFAULT '',
            city          NVARCHAR(200)  NOT NULL DEFAULT '',
            locality      NVARCHAR(200)  NOT NULL DEFAULT '',
            lat           FLOAT          NULL,
            lng           FLOAT          NULL,
            address_type  NVARCHAR(50)   NOT NULL DEFAULT 'OTHER',
            case_id       INT            NULL,
            CONSTRAINT uq_doc_locations UNIQUE (doc_id, person_name, address_type)
        )
    """)
    conn.execute("""
        IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_loc_doc_id' AND object_id = OBJECT_ID('doc_locations'))
            CREATE INDEX idx_loc_doc_id ON doc_locations(doc_id)
    """)
    conn.execute("""
        IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_loc_city' AND object_id = OBJECT_ID('doc_locations'))
            CREATE INDEX idx_loc_city ON doc_locations(city)
    """)
    conn.execute("""
        IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_loc_lat' AND object_id = OBJECT_ID('doc_locations'))
            CREATE INDEX idx_loc_lat ON doc_locations(lat)
    """)

    # Schema migration: add case_id column to doc_locations if absent
    conn.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'doc_locations' AND COLUMN_NAME = 'case_id'
        )
        ALTER TABLE doc_locations ADD case_id INT NULL
    """)

    conn.commit()
    conn.close()


init_db()


# ---------------------------------------------------------------------------
# India Geocoding Dictionary (offline — no external API)
# Format: lowercase name -> (lat, lng)
# Covers: Karnataka districts, Bangalore localities, major Indian cities
# ---------------------------------------------------------------------------
INDIA_GEOCODING: Dict[str, Tuple[float, float]] = {
    # ── Karnataka Districts / Cities ─────────────────────────────────────────
    "bangalore": (12.9716, 77.5946),
    "bengaluru": (12.9716, 77.5946),
    "mysore": (12.2958, 76.6394),
    "mysuru": (12.2958, 76.6394),
    "hubli": (15.3647, 75.1240),
    "dharwad": (15.4589, 75.0078),
    "mangalore": (12.8654, 74.8422),
    "mangaluru": (12.8654, 74.8422),
    "belgaum": (15.8497, 74.4977),
    "belagavi": (15.8497, 74.4977),
    "gulbarga": (17.3297, 76.8343),
    "kalaburagi": (17.3297, 76.8343),
    "davangere": (14.4644, 75.9218),
    "davanagere": (14.4644, 75.9218),
    "bellary": (15.1394, 76.9214),
    "ballari": (15.1394, 76.9214),
    "bidar": (17.9104, 77.5199),
    "tumkur": (13.3379, 77.1173),
    "tumakuru": (13.3379, 77.1173),
    "shimoga": (13.9299, 75.5681),
    "shivamogga": (13.9299, 75.5681),
    "raichur": (16.2120, 77.3566),
    "bijapur": (16.8302, 75.7100),
    "vijayapura": (16.8302, 75.7100),
    "hassan": (13.0068, 76.1002),
    "chikmagalur": (13.3161, 75.7720),
    "chikkamagaluru": (13.3161, 75.7720),
    "chitradurga": (14.2251, 76.3974),
    "kolar": (13.1360, 78.1294),
    "mandya": (12.5218, 76.8950),
    "udupi": (13.3409, 74.7421),
    "gadag": (15.4161, 75.6247),
    "koppal": (15.3512, 76.1551),
    "yadgir": (16.7710, 77.1383),
    "chamarajanagar": (11.9218, 76.9427),
    "kodagu": (12.4195, 75.7398),
    "coorg": (12.4195, 75.7398),
    "dakshina kannada": (12.8654, 74.8422),
    "uttara kannada": (14.7901, 74.6910),
    "chikkaballapur": (13.4322, 77.7286),
    "ramanagara": (12.7148, 77.2847),
    "ramnagara": (12.7148, 77.2847),
    "bagalkot": (16.1694, 75.6961),
    "hospet": (15.2690, 76.3870),
    "robertsonpet": (12.9600, 78.2700),
    "robertsunpet": (12.9600, 78.2700),
    "gangavathi": (15.4296, 76.5360),
    "sirsi": (14.6218, 74.8347),
    "karwar": (14.8137, 74.1236),
    "bhatkal": (13.9718, 74.5583),
    "puttur": (12.7614, 75.2025),
    "sullia": (12.5614, 75.3877),
    "madikeri": (12.4225, 75.7382),
    "kushalnagar": (12.4605, 75.9646),
    "tiptur": (13.2577, 76.4793),
    "arsikere": (13.3124, 76.2567),
    "channarayapatna": (12.9025, 76.3876),
    "holenarasipur": (12.7876, 76.2388),
    "sakleshpur": (12.9385, 75.7887),
    # ── Bangalore Localities ─────────────────────────────────────────────────
    "frazer town": (12.9819, 77.6108),
    "fraser town": (12.9819, 77.6108),
    "sultan palya": (13.0174, 77.5939),
    "sultanpalya": (13.0174, 77.5939),
    "rt nagar": (13.0236, 77.5914),
    "r.t. nagar": (13.0236, 77.5914),
    "r.t nagar": (13.0236, 77.5914),
    "rtnagar": (13.0236, 77.5914),
    "jc nagar": (13.0055, 77.6021),
    "j.c. nagar": (13.0055, 77.6021),
    "hebbal": (13.0354, 77.5970),
    "yelahanka": (13.1004, 77.5963),
    "malleshwaram": (12.9994, 77.5693),
    "malleswaram": (12.9994, 77.5693),
    "rajajinagar": (12.9862, 77.5568),
    "rajaji nagar": (12.9862, 77.5568),
    "shivajinagar": (12.9846, 77.5995),
    "shivaji nagar": (12.9846, 77.5995),
    "indiranagar": (12.9784, 77.6408),
    "indira nagar": (12.9784, 77.6408),
    "koramangala": (12.9279, 77.6271),
    "hsr layout": (12.9116, 77.6474),
    "electronic city": (12.8458, 77.6624),
    "whitefield": (12.9698, 77.7500),
    "marathahalli": (12.9591, 77.6971),
    "kr puram": (13.0061, 77.6939),
    "k.r. puram": (13.0061, 77.6939),
    "banaswadi": (13.0134, 77.6449),
    "banasawadi": (13.0134, 77.6449),
    "cv raman nagar": (12.9880, 77.6603),
    "hennur": (13.0413, 77.6398),
    "thanisandra": (13.0530, 77.6283),
    "sahakarnagar": (13.0553, 77.5877),
    "sahakar nagar": (13.0553, 77.5877),
    "byappanahalli": (12.9919, 77.6470),
    "domlur": (12.9603, 77.6392),
    "hal": (12.9606, 77.6677),
    "hal 2nd stage": (12.9606, 77.6677),
    "jp nagar": (12.9077, 77.5857),
    "j.p. nagar": (12.9077, 77.5857),
    "btm layout": (12.9165, 77.6101),
    "btm": (12.9165, 77.6101),
    "jayanagar": (12.9308, 77.5838),
    "basavanagudi": (12.9472, 77.5752),
    "gandhinagar": (12.9751, 77.5706),
    "yeshwanthpur": (13.0270, 77.5518),
    "jalahalli": (13.0490, 77.5334),
    "peenya": (13.0282, 77.5187),
    "kengeri": (12.9078, 77.4824),
    "banashankari": (12.9249, 77.5571),
    "kr market": (12.9613, 77.5771),
    "city market": (12.9632, 77.5768),
    "halasuru": (12.9726, 77.6218),
    "ulsoor": (12.9762, 77.6218),
    "cantonment": (12.9975, 77.6043),
    "nagavara": (13.0397, 77.6130),
    "kalyan nagar": (13.0409, 77.6481),
    "hrbr layout": (13.0244, 77.6465),
    "horamavu": (13.0312, 77.6604),
    "kadugodi": (12.9915, 77.7452),
    "mahadevapura": (12.9957, 77.7119),
    "brookefield": (12.9755, 77.7196),
    "mathikere": (13.0084, 77.5531),
    "mahalakshmi layout": (13.0082, 77.5474),
    "padmanabhanagar": (12.9292, 77.5452),
    "uttarahalli": (12.9085, 77.5255),
    "mg road": (12.9755, 77.6076),
    "cox town": (12.9924, 77.6126),
    "richmond town": (12.9671, 77.5981),
    "commercial street": (12.9810, 77.6103),
    "lingarajapuram": (13.0022, 77.6327),
    "pulikeshinagar": (12.9970, 77.6120),
    "nagasandra": (13.0560, 77.5126),
    "dasarahalli": (13.0541, 77.5046),
    "bagalagunte": (13.0641, 77.5304),
    "kumaraswamy layout": (12.9029, 77.5665),
    "chamrajpet": (12.9587, 77.5648),
    "cottonpet": (12.9655, 77.5684),
    "chickpet": (12.9655, 77.5756),
    "avenue road": (12.9711, 77.5716),
    "sarjapur road": (12.9034, 77.6752),
    "bellandur": (12.9270, 77.6771),
    "sarjapur": (12.8608, 77.7859),
    "bannerghatta road": (12.8843, 77.5977),
    "hosur road": (12.9073, 77.6068),
    "magadi road": (12.9808, 77.5352),
    "tumkur road": (13.0533, 77.5205),
    "shampura": (12.9936, 77.6283),
    # ── Major Indian Cities ───────────────────────────────────────────────────
    "mumbai": (19.0760, 72.8777),
    "delhi": (28.6139, 77.2090),
    "new delhi": (28.6139, 77.2090),
    "chennai": (13.0827, 80.2707),
    "kolkata": (22.5726, 88.3639),
    "hyderabad": (17.3850, 78.4867),
    "pune": (18.5204, 73.8567),
    "ahmedabad": (23.0225, 72.5714),
    "surat": (21.1702, 72.8311),
    "jaipur": (26.9124, 75.7873),
    "lucknow": (26.8467, 80.9462),
    "kanpur": (26.4499, 80.3319),
    "nagpur": (21.1458, 79.0882),
    "indore": (22.7196, 75.8577),
    "thane": (19.2183, 72.9781),
    "bhopal": (23.2599, 77.4126),
    "visakhapatnam": (17.6868, 83.2185),
    "vizag": (17.6868, 83.2185),
    "patna": (25.5941, 85.1376),
    "vadodara": (22.3072, 73.1812),
    "agra": (27.1767, 78.0081),
    "varanasi": (25.3176, 82.9739),
    "amritsar": (31.6340, 74.8723),
    "coimbatore": (11.0168, 76.9558),
    "madurai": (9.9252, 78.1198),
    "thiruvananthapuram": (8.5241, 76.9366),
    "trivandrum": (8.5241, 76.9366),
    "kochi": (9.9312, 76.2673),
    "cochin": (9.9312, 76.2673),
    "ernakulam": (9.9816, 76.2999),
    "kozhikode": (11.2588, 75.7804),
    "calicut": (11.2588, 75.7804),
    "kannur": (11.8745, 75.3704),
    "thrissur": (10.5276, 76.2144),
    "goa": (15.2993, 74.1240),
    "panaji": (15.4909, 73.8278),
    "nashik": (19.9975, 73.7898),
    "aurangabad": (19.8762, 75.3433),
    "solapur": (17.6870, 75.9064),
    "rajkot": (22.3039, 70.8022),
    "faridabad": (28.4089, 77.3178),
    "ghaziabad": (28.6692, 77.4538),
    "noida": (28.5355, 77.3910),
    "meerut": (28.9845, 77.7064),
    "chandigarh": (30.7333, 76.7794),
    "ludhiana": (30.9010, 75.8573),
    "bhubaneswar": (20.2961, 85.8245),
    "cuttack": (20.4625, 85.8830),
    "guwahati": (26.1445, 91.7362),
    "ranchi": (23.3441, 85.3096),
    "raipur": (21.2514, 81.6296),
    "dehradun": (30.3165, 78.0322),
    "shimla": (31.1048, 77.1734),
    "jammu": (32.7266, 74.8570),
    "srinagar": (34.0837, 74.7973),
}


def geocode(city: str, locality: str = "") -> Optional[Tuple[float, float]]:
    """
    Look up coordinates using the bundled India geocoding dict.
    Tries locality first (more specific), then city.
    """
    if locality:
        key = locality.strip().lower()
        if key in INDIA_GEOCODING:
            return INDIA_GEOCODING[key]
        if len(key) >= 5:
            for k, v in INDIA_GEOCODING.items():
                if key in k or k in key:
                    return v

    if city:
        key = city.strip().lower()
        if key in INDIA_GEOCODING:
            return INDIA_GEOCODING[key]
        if len(key) >= 4:
            for k, v in INDIA_GEOCODING.items():
                if key in k or k in key:
                    return v

    return None


# ---------------------------------------------------------------------------
# LLM Location Extraction
# ---------------------------------------------------------------------------
def extract_locations_from_chunks(
    chunks: List[str], batch_size: int = 3
) -> List[Dict[str, Any]]:
    """
    Extract address data from IR document chunks using the local LLM.
    Processes chunks in batches of `batch_size`.
    """
    all_locations: List[Dict[str, Any]] = []

    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        combined = "\n\n---\n\n".join(
            f"[CHUNK {start + i}]\n{chunk[:2000]}" for i, chunk in enumerate(batch)
        )

        prompt = (
            "Extract ALL addresses and locations from the following Interrogation Report text.\n\n"
            "For each address found, return:\n"
            "- person_name: the subject's name linked to this address (empty string if not mentioned)\n"
            "- address_text: full address as it appears in the document\n"
            "- city: city, town, or district name (e.g., Bangalore, Mysore, Hubli, Delhi)\n"
            "- locality: specific area or locality in the city (e.g., Frazer Town, RT Nagar, Hebbal)\n"
            "- address_type: PERMANENT (permanent residence), PRESENT (current/present address), "
            "PREVIOUS (past address), or OTHER\n\n"
            "Return ONLY a JSON object:\n"
            '{"locations": [{"person_name": "...", "address_text": "...", "city": "...", '
            '"locality": "...", "address_type": "..."}]}\n\n'
            "Rules:\n"
            "- Only include addresses that contain a city, area, or recognizable place name.\n"
            "- Use PERMANENT for 'permanent address' fields, PRESENT for 'present/current address'.\n"
            '- If no addresses are found, return {"locations": []}\n\n'
            f"TEXT:\n{combined}"
        )

        try:
            response = ollama_chat(
                [{"role": "user", "content": prompt}],
                temperature=0.0,
                model=PDF_MODEL,
            )
            parsed = _find_balanced_json_object(response)
            if parsed and "locations" in parsed:
                batch_locs = parsed["locations"]
                print(f"[Locations] Batch {start}: {len(batch_locs)} location(s) found")
                for loc in batch_locs:
                    if not isinstance(loc, dict):
                        continue
                    city = (loc.get("city") or "").strip()
                    locality = (loc.get("locality") or "").strip()
                    if not city and not locality:
                        continue
                    atype = (loc.get("address_type") or "OTHER").upper().strip()
                    if atype not in ("PERMANENT", "PRESENT", "PREVIOUS", "OTHER"):
                        atype = "OTHER"
                    all_locations.append({
                        "person_name": (loc.get("person_name") or "")[:150].strip(),
                        "address_text": (loc.get("address_text") or "")[:500].strip(),
                        "city": city,
                        "locality": locality,
                        "address_type": atype,
                    })
        except Exception as ex:
            print(f"[Locations] Extraction error at batch {start}: {ex}")

    return all_locations


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
def store_locations(
    doc_id: str, doc_name: str, locations: List[Dict[str, Any]], case_id: Optional[int] = None
) -> Dict[str, Any]:
    """Geocode and store location records in SQL Server."""
    conn = _get_conn()
    stored = 0
    skipped_no_geo = 0

    for loc in locations:
        coords = geocode(loc["city"], loc["locality"])
        lat, lng = coords if coords else (None, None)
        if not coords:
            skipped_no_geo += 1

        try:
            conn.execute(
                """
                IF NOT EXISTS (
                    SELECT 1 FROM doc_locations
                    WHERE doc_id = ? AND person_name = ? AND address_type = ?
                )
                INSERT INTO doc_locations
                    (doc_id, doc_name, person_name, address_text, city, locality,
                     lat, lng, address_type, case_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id, loc["person_name"], loc["address_type"],
                    doc_id, doc_name,
                    loc["person_name"], loc["address_text"],
                    loc["city"], loc["locality"],
                    lat, lng, loc["address_type"], case_id,
                ),
            )
            stored += 1
        except Exception as ex:
            print(f"[Locations] Store error: {ex}")

    conn.commit()
    conn.close()
    print(
        f"[Locations] Stored {stored} locations for {doc_name} "
        f"({skipped_no_geo} could not be geocoded)"
    )
    return {"stored": stored, "doc_id": doc_id}


def extract_and_store_locations(
    doc_id: str, doc_name: str, chunks: List[str], case_id: Optional[int] = None
) -> Dict[str, Any]:
    """Full pipeline: LLM extraction → dedup → geocoding → SQL Server storage."""
    print(f"[Locations] Starting for '{doc_name}' ({len(chunks)} chunks)")
    locations = extract_locations_from_chunks(chunks)

    # Deduplicate by (person_name_lower, address_type)
    seen: set = set()
    unique: List[Dict[str, Any]] = []
    for loc in locations:
        key = (loc["person_name"].lower().strip(), loc["address_type"])
        if key not in seen:
            seen.add(key)
            unique.append(loc)

    print(f"[Locations] Deduped to {len(unique)} unique locations")
    return store_locations(doc_id, doc_name, unique, case_id=case_id)


# ---------------------------------------------------------------------------
# Query Functions (for API endpoints)
# ---------------------------------------------------------------------------
def get_all_locations(case_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Return all geocoded locations (those with lat/lng)."""
    conn = _get_conn()
    if case_id is not None:
        cur = conn.execute(
            "SELECT id, doc_id, doc_name, person_name, address_text, city, locality, "
            "lat, lng, address_type "
            "FROM doc_locations "
            "WHERE lat IS NOT NULL AND case_id = ? "
            "ORDER BY doc_name, person_name",
            (case_id,),
        )
    else:
        cur = conn.execute(
            "SELECT id, doc_id, doc_name, person_name, address_text, city, locality, "
            "lat, lng, address_type "
            "FROM doc_locations "
            "WHERE lat IS NOT NULL "
            "ORDER BY doc_name, person_name"
        )
    rows = _fetchall(cur)
    conn.close()
    return rows


def get_extracted_doc_ids_for_locations(case_id: Optional[int] = None) -> set:
    """Return set of doc_ids that already have location records stored."""
    conn = _get_conn()
    if case_id is not None:
        cur = conn.execute("SELECT DISTINCT doc_id FROM doc_locations WHERE case_id = ?", (case_id,))
    else:
        cur = conn.execute("SELECT DISTINCT doc_id FROM doc_locations")
    ids = {r[0] for r in cur.fetchall()}
    conn.close()
    return ids


def clear_locations_data(case_id: Optional[int] = None) -> Dict[str, Any]:
    """Delete location records. If case_id is given, only delete for that case."""
    conn = _get_conn()
    if case_id is not None:
        conn.execute("DELETE FROM doc_locations WHERE case_id = ?", (case_id,))
    else:
        conn.execute("DELETE FROM doc_locations")
    conn.commit()
    conn.close()
    return {"ok": True, "message": "Location data cleared."}
