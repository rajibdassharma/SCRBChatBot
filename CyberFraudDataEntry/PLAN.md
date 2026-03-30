# Implementation Plan — Cyber Fraud Data Entry

## Project Status: Active Development

This document tracks the implementation roadmap, completed milestones, and
planned features for the Cyber Fraud Data Entry platform.

---

## Completed Milestones

### Phase 1: Foundation
- [x] FastAPI backend with async MySQL (SQLAlchemy 2.0 + asyncmy)
- [x] React 19 + TypeScript + Vite frontend
- [x] Tailwind CSS styling
- [x] JWT authentication (bcrypt + HS256)
- [x] Role-based access control (admin, unit_user)
- [x] Unit-based data isolation
- [x] Database schema — all 20 tables with relationships
- [x] Seed script for units, police stations, admin user

### Phase 2: Case Management
- [x] Case CRUD with nested children (arrests, petitions, lien accounts, unfreeze, refunds)
- [x] Arrest entry with accomplice and accused detail sub-forms
- [x] Petition entry and tracking
- [x] Lien account tracking with layer support
- [x] Unfreeze detail recording
- [x] Refund tracking
- [x] Search by FIR number and petition number
- [x] Case list with pagination
- [x] Draft/submitted status workflow
- [x] CASCADE delete for all nested records

### Phase 3: Mule Reports
- [x] Mule report CRUD with 6 transaction table types
- [x] Money transfers, other transactions, transactions on hold
- [x] Others < 500, AEPS transactions, ATM withdrawals
- [x] Excel file upload and parsing (openpyxl)
- [x] Excel preview before saving
- [x] Search by acknowledgement number
- [x] Mule report list with pagination

### Phase 4: Daily Reports
- [x] DSR (Daily Status Report) upsert by unit + date
- [x] Mule intelligence entry upsert by unit + date
- [x] History view for past entries
- [x] Admin view: all units' entries for a given date

### Phase 5: Dashboard & Analytics
- [x] Admin KPI summary (total cases, arrests, lien amount, refunds)
- [x] Unit comparison chart (Recharts)
- [x] Units submitted vs total count

### Phase 6: Deployment
- [x] Nginx reverse proxy configuration
- [x] Gunicorn + Uvicorn ASGI setup
- [x] systemd service configuration
- [x] SSL/TLS with Let's Encrypt
- [x] Production deployment documentation

---

## Planned Features

### Near-Term

| Feature | Priority | Description |
|---------|----------|-------------|
| Bulk case import | High | Upload Excel/CSV with multiple cases at once |
| Audit trail | High | Track who created/modified each record with timestamps |
| Report export | Medium | Export DSR, case list, mule reports as PDF/Excel |
| Password reset | Medium | Admin-initiated password reset for unit users |
| User management UI | Medium | Admin page to create/deactivate users |

### Medium-Term

| Feature | Priority | Description |
|---------|----------|-------------|
| Date range reports | Medium | DSR/mule aggregates over a date range |
| Advanced search | Medium | Multi-field search across cases (crime type, date range, status) |
| Notification system | Low | Alert admin when units haven't submitted daily reports |
| Mobile responsive | Low | Optimize forms for mobile devices |
| Data validation | Medium | Aadhar/PAN format validation, duplicate account detection |

### Long-Term

| Feature | Priority | Description |
|---------|----------|-------------|
| Cross-unit analytics | Low | Identify mule accounts appearing across multiple units |
| Integration with NCRP | Low | Auto-pull NCRP complaints via API |
| Geo mapping | Low | Map ATM locations and fraud hotspots |
| Role expansion | Low | District-level supervisor role with read-only access |

---

## Technical Debt

| Item | Impact | Description |
|------|--------|-------------|
| JWT expiry handling | Low | `decode_token` uses `verify_exp=False` — should enforce server-side |
| Error handling | Medium | Standardize error responses across all routes |
| Test coverage | High | No automated tests — add pytest + httpx for API tests |
| Frontend form validation | Medium | Client-side validation is minimal — add Zod schemas |
| Database migrations | Medium | No migration tool — using auto-create; should add Alembic |
| Photo storage | Low | Files stored on local filesystem — should move to object storage for scaling |

---

## Development Guidelines

### Adding a New Feature

1. **Model:** Create SQLAlchemy model in `backend/models/`, add to `__init__.py`
2. **Schema:** Create Pydantic schemas in `backend/schemas/`
3. **Route:** Create route handler in `backend/api/`, mount in `main.py`
4. **Types:** Add TypeScript interfaces in `frontend/src/types/index.ts`
5. **API client:** Add typed fetch functions in `frontend/src/lib/api/`
6. **Page:** Create page component in `frontend/src/pages/`
7. **Route:** Add React Router route in `frontend/src/App.tsx`
8. **Sidebar:** Add navigation link in `frontend/src/components/layout/Sidebar.tsx`

### Adding a New Transaction Table (Mule Reports)

1. Create SQLAlchemy model with `report_id` FK to `mule_reports` (CASCADE)
2. Add relationship to `MuleReport` model
3. Add Pydantic create/response schema in `schemas/mule.py`
4. Add to `MuleReportCreate` and `MuleReportResponse` schemas
5. Handle in create/update route logic in `routes_mule_report.py`
6. Add TypeScript type in `types/index.ts`
7. Add form section in `MuleReportEntryPage.tsx`
8. Add Excel sheet mapping in upload handler (if applicable)
