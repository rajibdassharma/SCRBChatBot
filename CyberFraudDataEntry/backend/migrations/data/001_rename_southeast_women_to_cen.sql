-- ============================================================================
-- DATA FIX 001 — rename "South East Women PS" → "South East CEN PS"
-- ============================================================================
-- Why:
--   The Bengaluru South East PS was registered in the DB with an outdated
--   station name ("Women PS"). It should be "CEN PS" (Cyber Economic and
--   Narcotic — current naming). Both the police_stations row and any
--   user accounts derived from it are renamed in a single transaction.
--
-- Affected rows (run the SELECTs first to verify exact spelling matches):
--   - police_stations: 1 row
--   - users:           2 rows (admin + unit_user). If user2/user3 exist
--                      for this PS, they're caught by the LIKE clause.
--
-- Idempotent: re-running after the fix is a no-op (the WHERE clauses
-- target the OLD name, which will no longer exist).
--
-- Knock-on effects:
--   * cases / petitions / mule_reports etc. reference users.id (not
--     username) and units.id (district, not PS) — UNAFFECTED.
--   * Anyone currently logged in keeps their JWT; the next login will
--     pick "South East CEN PS" on the dropdown (the login form derives
--     the username from station_name via toCode()).
--
-- Usage (on the production server):
--   mysql -u root -p cyber_fraud_dsr \
--     < /opt/cyberfraud/backend/migrations/data/001_rename_southeast_women_to_cen.sql
--
-- Apply later to local dev:
--   mysql -u root -p cyber_fraud_dsr < backend/migrations/data/001_rename_southeast_women_to_cen.sql
-- ============================================================================

-- ── 0. Pre-flight: confirm what's about to change ──
SELECT '── BEFORE ─────────────────────────────────────────────' AS info;
SELECT id, station_name, district_name FROM police_stations WHERE station_name = 'South East Women PS';
SELECT id, username, role, ps_id, is_active FROM users WHERE username LIKE 'south_east_women_ps_%';

-- ── 1. Rename, in one transaction ──
START TRANSACTION;

UPDATE police_stations
SET station_name = 'South East CEN PS'
WHERE station_name = 'South East Women PS';

UPDATE users
SET username = REPLACE(username, 'south_east_women_ps_', 'south_east_cen_ps_')
WHERE username LIKE 'south_east_women_ps_%';

COMMIT;

-- ── 2. Post-flight: confirm the new state ──
SELECT '── AFTER ──────────────────────────────────────────────' AS info;
SELECT id, station_name, district_name FROM police_stations WHERE station_name = 'South East CEN PS';
SELECT id, username, role, ps_id, is_active FROM users WHERE username LIKE 'south_east_cen_ps_%';

-- Final sanity — the OLD name should now be gone everywhere
SELECT '── ORPHANS (should be empty) ──────────────────────────' AS info;
SELECT id, station_name FROM police_stations WHERE station_name = 'South East Women PS';
SELECT id, username    FROM users           WHERE username LIKE 'south_east_women_ps_%';
