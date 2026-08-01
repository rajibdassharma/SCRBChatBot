#!/usr/bin/env bash
# CyberFraud — READ-ONLY diagnostic: how much location data do the
# All Accounts rows actually carry?
#
# Written to settle two open design questions with numbers instead of
# assumptions, before any map drill-down work starts:
#
#   1. Can we plot accounts below state level at all? Every location
#      field on all_accounts is OPTIONAL (branch_district, ifsc_code,
#      kyc_address), so the answer is a fill rate, not a yes/no.
#
#   2. How should the 5 city commissionerates be handled on a Karnataka
#      district map? They are police units, not revenue districts, so no
#      boundary geometry exists for them. If they hold a large share of
#      the rows, "shade revenue districts only" would silently drop that
#      share off the map. Section 4 measures exactly that.
#
# SAFETY: every statement is a SELECT. This script creates nothing,
# alters nothing, and deletes nothing. Safe to run on production at any
# time, including during business hours — the tables involved are small
# and the queries are unindexed scans at worst.
#
# Usage on the server:
#   cd /opt/scrb && git pull && \
#     sudo bash CyberFraudDataEntry/deploy/check-account-location-coverage.sh

set -euo pipefail

ENV_FILE=/opt/cyberfraud/backend/.env

# Same credential-reading idiom as update.sh. The `|| true` on each grep
# is CRITICAL: under `set -euo pipefail` a grep that matches nothing
# returns 1 and would kill the script with no error message.
DB_USER=$( (grep -E '^CFDSR_DB_USER='     "$ENV_FILE" 2>/dev/null || true) | tail -1 | cut -d'=' -f2- )
DB_PASS=$( (grep -E '^CFDSR_DB_PASSWORD=' "$ENV_FILE" 2>/dev/null || true) | tail -1 | cut -d'=' -f2- )
DB_NAME=$( (grep -E '^CFDSR_DB_NAME='     "$ENV_FILE" 2>/dev/null || true) | tail -1 | cut -d'=' -f2- )
: "${DB_USER:=root}"; : "${DB_NAME:=cyber_fraud_dsr}"

# `|| echo` keeps a single failing section from aborting the whole
# diagnostic under `set -e` — you still get the other numbers.
q() { MYSQL_PWD="$DB_PASS" mysql --table --user="$DB_USER" "$DB_NAME" -e "$1" || echo "  (this query failed — check CFDSR_DB_* in $ENV_FILE)"; }

echo "================================================================"
echo "  All Accounts — location data coverage  (READ ONLY)"
echo "  db: $DB_NAME    $(date '+%Y-%m-%d %H:%M:%S')"
echo "================================================================"

echo
echo "=== 1. Overall fill rates ======================================"
echo "    Which location fields are actually being captured."
q "
SELECT
  COUNT(*)                                                        AS total_rows,
  SUM(account_type = 'Mule')                                      AS mule_rows,
  CONCAT(ROUND(100*AVG(branch_state    IS NOT NULL AND branch_state    <> ''),1),'%') AS has_branch_state,
  CONCAT(ROUND(100*AVG(branch_district IS NOT NULL AND branch_district <> ''),1),'%') AS has_branch_district,
  CONCAT(ROUND(100*AVG(ifsc_code       IS NOT NULL AND ifsc_code       <> ''),1),'%') AS has_ifsc,
  CONCAT(ROUND(100*AVG(kyc_address     IS NOT NULL AND kyc_address     <> ''),1),'%') AS has_kyc_address
FROM all_accounts;"

echo
echo "=== 2. Same, Mule accounts only ================================"
echo "    The map defaults to Mule, so this is the number that matters."
q "
SELECT
  COUNT(*)                                                        AS mule_rows,
  CONCAT(ROUND(100*AVG(branch_state    IS NOT NULL AND branch_state    <> ''),1),'%') AS has_branch_state,
  CONCAT(ROUND(100*AVG(branch_district IS NOT NULL AND branch_district <> ''),1),'%') AS has_branch_district,
  CONCAT(ROUND(100*AVG(ifsc_code       IS NOT NULL AND ifsc_code       <> ''),1),'%') AS has_ifsc,
  CONCAT(ROUND(100*AVG(kyc_address     IS NOT NULL AND kyc_address     <> ''),1),'%') AS has_kyc_address
FROM all_accounts
WHERE account_type = 'Mule';"

echo
echo "=== 3. Karnataka rows: district fill ==========================="
echo "    branch_district is Karnataka-only by design (the entry form"
echo "    nulls it for every other state), so a district drill-down can"
echo "    only ever cover these rows."
q "
SELECT
  COUNT(*)                                                        AS karnataka_rows,
  SUM(branch_district IS NULL OR branch_district = '')            AS district_blank,
  CONCAT(ROUND(100*AVG(branch_district IS NOT NULL AND branch_district <> ''),1),'%') AS district_filled
FROM all_accounts
WHERE TRIM(branch_state) = 'Karnataka';"

echo
echo "=== 4. Commissionerate vs revenue district ====================="
echo "    THE decision input. The 5 city commissionerates have no"
echo "    boundary geometry. If their share is large, shading revenue"
echo "    districts only would drop that share off the map entirely."
echo "    Vijayanagara is listed separately: a real district (created"
echo "    2021) that the current boundary file predates."
q "
SELECT
  COUNT(*) AS ka_rows_with_district,
  SUM(TRIM(branch_district) IN ('Bengaluru City','Mysuru City','Hubli-Dharwad','Mangaluru City','Belagavi City')) AS commissionerate_rows,
  CONCAT(ROUND(100*AVG(TRIM(branch_district) IN ('Bengaluru City','Mysuru City','Hubli-Dharwad','Mangaluru City','Belagavi City')),1),'%') AS commissionerate_pct,
  SUM(TRIM(branch_district) = 'Vijayanagara') AS vijayanagara_rows
FROM all_accounts
WHERE TRIM(branch_state) = 'Karnataka'
  AND branch_district IS NOT NULL AND branch_district <> '';"

echo
echo "=== 5. Full district distribution =============================="
echo "    'geometry' = NO means the map has no shape for that value,"
echo "    so those rows need a rule (merge into parent / marker / omit)."
q "
SELECT
  TRIM(branch_district) AS district,
  COUNT(*)              AS total,
  SUM(account_type = 'Mule') AS mules,
  CASE WHEN TRIM(branch_district) IN
       ('Bengaluru City','Mysuru City','Hubli-Dharwad','Mangaluru City','Belagavi City','Vijayanagara')
       THEN 'NO' ELSE 'yes' END AS has_geometry
FROM all_accounts
WHERE TRIM(branch_state) = 'Karnataka'
  AND branch_district IS NOT NULL AND branch_district <> ''
GROUP BY TRIM(branch_district)
ORDER BY total DESC;"

echo
echo "=== 6. Unrecognised district values ============================"
echo "    Anything here is a typo or a legacy value: it will render as"
echo "    'unmapped' on the map rather than being silently dropped."
q "
SELECT TRIM(branch_district) AS unrecognised_value, COUNT(*) AS rows_affected
FROM all_accounts
WHERE TRIM(branch_state) = 'Karnataka'
  AND branch_district IS NOT NULL AND branch_district <> ''
  AND TRIM(branch_district) NOT IN (
    'Bagalkot','Ballari','Belagavi','Bengaluru Rural','Bengaluru Urban','Bidar',
    'Chamarajanagar','Chikkaballapur','Chikkamagaluru','Chitradurga','Dakshina Kannada',
    'Davanagere','Dharwad','Gadag','Hassan','Haveri','Kalaburagi','Kodagu','Kolar',
    'Koppal','Mandya','Mysuru','Raichur','Ramanagara','Shivamogga','Tumakuru','Udupi',
    'Uttara Kannada','Vijayanagara','Vijayapura','Yadgir',
    'Bengaluru City','Mysuru City','Hubli-Dharwad','Mangaluru City','Belagavi City')
GROUP BY TRIM(branch_district)
ORDER BY rows_affected DESC;"

echo
echo "=== 7. IFSC usability (for a possible future pin map) =========="
echo "    A well-formed IFSC is 11 chars: 4 letters, a '0', then 6"
echo "    alphanumerics. Only well-formed codes could be joined against"
echo "    an offline branch-coordinate table."
q "
SELECT
  COUNT(*) AS rows_with_ifsc,
  SUM(TRIM(ifsc_code) REGEXP '^[A-Za-z]{4}0[A-Za-z0-9]{6}\$') AS well_formed,
  CONCAT(ROUND(100*AVG(TRIM(ifsc_code) REGEXP '^[A-Za-z]{4}0[A-Za-z0-9]{6}\$'),1),'%') AS well_formed_pct
FROM all_accounts
WHERE ifsc_code IS NOT NULL AND ifsc_code <> '';"

echo
echo "================================================================"
echo "  Done. Nothing was modified."
echo
echo "  How to read section 4:"
echo "    commissionerate_pct near 0   -> shade revenue districts only;"
echo "                                    the gap is negligible."
echo "    commissionerate_pct moderate -> draw them as markers on the"
echo "                                    parent district, so both"
echo "                                    numbers stay visible."
echo "    commissionerate_pct large    -> merging into the parent is the"
echo "                                    only option that keeps the map"
echo "                                    representative."
echo
echo "  Section 3 gates the whole feature: if district_filled is low,"
echo "  a district map would show a small and possibly unrepresentative"
echo "  slice, and the coverage banner will say so on screen."
echo "================================================================"
