"""
Hand-curated schema description fed to the LLM. This is the SECURITY
BOUNDARY for what the chat can ever query — only tables/columns listed
here are visible. Anything not described is unknown to the LLM.

Phase 1 tables: cases + the 5 child tables most operators ask about.
Excluded: users, revoked_tokens, chat_messages (auth + meta tables),
mule_reports + transaction tables (phase 2), dsr_entries (phase 2),
audit columns (created_at on children we don't need).

Keep this file PRECISE. Vague schema → bad SQL.
"""

SCHEMA_TEXT = """\
You are generating MySQL SELECT queries for the cyber_fraud_dsr database.
This is a Karnataka State Police cyber-fraud case tracking system.

## Tables

### units
36 districts (e.g. 'Bangalore City', 'Mysuru', 'Kolar'). One row per
organisational unit.
  id            INT PRIMARY KEY
  name          VARCHAR(100)  -- district name
  is_active     TINYINT

### police_stations
44 cyber police stations across the 36 districts. Most districts have one
Cyber Crime PS, Bangalore City has several.
  id            INT PRIMARY KEY
  district_name VARCHAR(100)  -- matches units.name
  station_name  VARCHAR(200)  -- e.g. 'South East Cyber PS'

### cases
The core record — one row per cyber fraud case (FIR / Walk-In / NCRP).
  id                VARCHAR(36) PRIMARY KEY   -- UUID
  unit_id           INT NOT NULL              -- FK to units.id (district)
  ps_id             INT NOT NULL              -- FK to police_stations.id
  fir_no            VARCHAR(50)               -- e.g. '45/2026'
  petition_no       VARCHAR(50)
  registration_date DATE
  case_type         VARCHAR(20)               -- 'NCRP' | 'Walk-In' | 'Petition'
  crime_type        VARCHAR(30)               -- 'Internet' | 'Digital' | 'Crypto'
  facts             TEXT                      -- free-text description
  status            VARCHAR(20)               -- 'draft' | 'submitted'
  submitted_by      INT                       -- FK to users.id (DO NOT JOIN to users)
  created_at        DATETIME
  updated_at        DATETIME
  Unique key (unit_id, ps_id, fir_no).

### arrests
Persons arrested in connection with a case. One case can have many arrests.
  id              VARCHAR(36) PRIMARY KEY
  case_id         VARCHAR(36) NOT NULL        -- FK to cases.id
  name            VARCHAR(200) NOT NULL
  address         TEXT
  email           VARCHAR(200)
  aadhar          VARCHAR(12)
  pan             VARCHAR(10)
  date_of_arrest  DATE
  statement       TEXT
  created_at      DATETIME

### victims
Victim profile per case (1:1). Created since 2026-06; many older cases
have no victim row yet.
  id                   VARCHAR(36) PRIMARY KEY
  case_id              VARCHAR(36) NOT NULL UNIQUE  -- FK to cases.id
  first_name           VARCHAR(100) NOT NULL
  last_name            VARCHAR(100) NOT NULL
  age                  INT
  gender               VARCHAR(30)               -- 'Male' | 'Female' | 'Other' | 'Prefer not to say'
  phone                VARCHAR(20)
  email                VARCHAR(200)
  house_no             VARCHAR(50)
  street_name          VARCHAR(200)
  city                 VARCHAR(100)
  state                VARCHAR(100)              -- Indian state name or 'Other'
  country              VARCHAR(100)              -- default 'India'
  pincode              VARCHAR(10)
  amount_lost          DECIMAL(18,2) NOT NULL    -- in INR
  bank_account_no      VARCHAR(50) NOT NULL
  bank_name            VARCHAR(200) NOT NULL
  bank_branch_address  TEXT

### petitions
Petitions filed against a case.
  id              VARCHAR(36) PRIMARY KEY
  case_id         VARCHAR(36) NOT NULL          -- FK to cases.id
  petition_no     VARCHAR(50)
  fir_registered  VARCHAR(20)                   -- 'yes' | 'no' | 'transferred'
  nature          VARCHAR(100)
  petition_type   VARCHAR(30)                   -- 'amount_lost' | 'fraud_case'
  amount          DECIMAL(18,2)
  created_at      DATETIME

### lien_accounts
Frozen bank accounts. layer = depth in the laundering chain (1 = direct
mule, 2 = next hop, etc.).
  id                      VARCHAR(36) PRIMARY KEY
  case_id                 VARCHAR(36) NOT NULL  -- FK to cases.id
  case_type               VARCHAR(20)           -- 'FIR' | 'NCRP' | 'Petition'
  account_no              VARCHAR(50) NOT NULL
  amount_lien_marked      DECIMAL(18,2)
  layer                   INT                   -- 1..N
  total_amount_in_account DECIMAL(18,2)
  bank_name               VARCHAR(200)
  created_at              DATETIME

### refunds
Victim refunds.
  id                       VARCHAR(36) PRIMARY KEY
  case_id                  VARCHAR(36) NOT NULL  -- FK to cases.id
  refunded                 VARCHAR(20)           -- 'yes' | 'no'
  victim_name              VARCHAR(200)
  amount                   DECIMAL(18,2)
  crime_no_or_petition_no  VARCHAR(50)
  created_at               DATETIME

## Common joins
- District + PS context for a case:
    cases c JOIN units u ON u.id = c.unit_id
            JOIN police_stations ps ON ps.id = c.ps_id
- Arrest names with their case FIR:
    arrests a JOIN cases c ON c.id = a.case_id
- Aggregating amount lost per district:
    victims v JOIN cases c ON c.id = v.case_id
              JOIN units u ON u.id = c.unit_id

## Conventions and gotchas
- All amounts are INR (rupees). DO NOT divide for "lakhs" or "crores" —
  show the raw rupee amount; the UI formats it.
- `cases.fir_no` is text, not numeric — sort it as text.
- `cases.status` filter: most users want 'submitted' cases unless they
  explicitly ask about drafts. When in doubt, do NOT filter on status.
- District = units.name. PS = police_stations.station_name. Operators
  often say 'PS' when they mean a district + PS combination — pick the
  more specific match if you can.
- 'Cyber' in PS names marks a Cyber Crime station (KSP cyber wing).
  Historical rows and free-text may still say 'CEN' (the old acronym
  standing for Cyber Economic and Narcotic) -- treat 'CEN' and 'Cyber'
  as interchangeable when matching PS names in user questions.
- Dates are MySQL DATE/DATETIME. Use NOW(), CURDATE(), DATE_SUB, INTERVAL.
- 'this month' = WHERE YEAR(created_at) = YEAR(NOW()) AND MONTH(created_at) = MONTH(NOW())
- 'last 7 days' = WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
- IMPORTANT: NEVER JOIN to `users`, `revoked_tokens`, or any table not
  listed above. These tables don't exist for you.
"""


def get_schema_text() -> str:
    """Return the schema description fed to the LLM. A function so we can
    parameterise later (e.g. trim by user role) without touching callers."""
    return SCHEMA_TEXT
