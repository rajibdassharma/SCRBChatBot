from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from models.case import Case
from models.arrest import Arrest
from models.accomplice import Accomplice
from models.accused_detail import AccusedDetail
from models.petition import Petition
from models.lien_account import LienAccount
from models.unfreeze_detail import UnfreezeDetail
from models.refund import Refund
from models.victim import Victim
from schemas.case import CaseCreate, CaseResponse, CaseListItem
from api.deps import get_current_user, require_admin, CurrentUser, check_record_access

router = APIRouter(prefix="/api/v1/cases", tags=["cases"])


# -- helpers ---------------------------------------------------------------

def _eager_options():
    """Return selectinload options for all Case children (and grandchildren)."""
    return [
        selectinload(Case.arrests).selectinload(Arrest.accomplices),
        selectinload(Case.arrests).selectinload(Arrest.accused_details),
        selectinload(Case.petitions),
        selectinload(Case.lien_accounts),
        selectinload(Case.unfreeze_details),
        selectinload(Case.refunds),
        selectinload(Case.victim),
    ]


def _ts(val) -> str | None:
    return str(val) if val else None


def _check_arrest_duplicates(body: CaseCreate) -> None:
    """Reject duplicate arrests within the same case.

    Two arrests are considered the same person if either signal matches:
      - Name        : whitespace-collapsed + lowercased
      - Aadhar      : exact match (only when BOTH rows have a value)

    Runs on both draft saves and submits — operators shouldn't be able
    to enter the same arrest twice regardless of workflow state. Cross-
    case dedup is not enforced (different cases can legitimately share
    accused — repeat offenders)."""
    seen_names: set[str] = set()
    seen_aadhar: set[str] = set()
    for i, arr in enumerate(body.arrests, start=1):
        key_name = " ".join((arr.name or "").split()).lower()
        key_aadhar = (arr.aadhar or "").strip()
        if key_name and key_name in seen_names:
            raise HTTPException(
                status_code=422,
                detail=f"Arrest #{i}: '{arr.name}' is already on this case.",
            )
        if key_aadhar and key_aadhar in seen_aadhar:
            raise HTTPException(
                status_code=422,
                detail=f"Arrest #{i}: an arrest with Aadhar {key_aadhar} is already on this case.",
            )
        if key_name:
            seen_names.add(key_name)
        if key_aadhar:
            seen_aadhar.add(key_aadhar)


def _validate_submitted_case(body: CaseCreate):
    """Raise 422 if a submitted case is missing required fields."""
    if body.status == "submitted":
        errors = []
        if not body.fir_no:
            errors.append("fir_no is required when submitting")
        if not body.registration_date:
            errors.append("registration_date is required when submitting")
        # Victim required fields — first_name, last_name, bank_account_no,
        # bank_name. amount_lost defaults to 0 which is acceptable
        # (some cases catch the fraud before money is lost).
        if body.victim is None:
            errors.append("victim details are required when submitting")
        else:
            v = body.victim
            if not (v.first_name or "").strip():
                errors.append("victim first_name is required when submitting")
            if not (v.last_name or "").strip():
                errors.append("victim last_name is required when submitting")
            if not (v.bank_account_no or "").strip():
                errors.append("victim bank_account_no is required when submitting")
            if not (v.bank_name or "").strip():
                errors.append("victim bank_name is required when submitting")
        if errors:
            raise HTTPException(status_code=422, detail="; ".join(errors))


def _case_to_response(c: Case) -> dict:
    """Convert ORM Case (with loaded relations) to a dict matching CaseResponse."""
    return {
        "id": c.id,
        "unit_id": c.unit_id,
        "fir_no": c.fir_no,
        "registration_date": c.registration_date,
        "petition_no": c.petition_no,
        "case_type": c.case_type,
        "crime_type": c.crime_type,
        "facts": c.facts,
        "status": c.status,
        "submitted_by": c.submitted_by,
        "created_at": _ts(c.created_at),
        "updated_at": _ts(c.updated_at),
        "arrests": [
            {
                "id": a.id,
                "case_id": a.case_id,
                "name": a.name,
                "address": a.address,
                "email": a.email,
                "aadhar": a.aadhar,
                "pan": a.pan,
                "date_of_arrest": a.date_of_arrest,
                "created_at": _ts(a.created_at),
                "accomplices": [
                    {
                        "id": ac.id,
                        "arrest_id": ac.arrest_id,
                        "where_met": ac.where_met,
                        "where_stayed": ac.where_stayed,
                        "interrogation_details": ac.interrogation_details,
                        "created_at": _ts(ac.created_at),
                    }
                    for ac in a.accomplices
                ],
                "accused_details": [
                    {
                        "id": ad.id,
                        "arrest_id": ad.arrest_id,
                        "photo_path": ad.photo_path,
                        "email": ad.email,
                        "mobile": ad.mobile,
                        "occupation": ad.occupation,
                        "remarks": ad.remarks,
                        "created_at": _ts(ad.created_at),
                    }
                    for ad in a.accused_details
                ],
            }
            for a in c.arrests
        ],
        "petitions": [
            {
                "id": p.id,
                "case_id": p.case_id,
                "fir_registered": p.fir_registered,
                "why_not": p.why_not,
                "nature": p.nature,
                "petition_type": p.petition_type,
                "amount": float(p.amount) if p.amount else 0,
                "created_at": _ts(p.created_at),
            }
            for p in c.petitions
        ],
        "lien_accounts": [
            {
                "id": la.id,
                "case_id": la.case_id,
                "case_type": la.case_type,
                "account_no": la.account_no,
                "amount_lien_marked": float(la.amount_lien_marked) if la.amount_lien_marked else 0,
                "layer": la.layer,
                "total_amount_in_account": float(la.total_amount_in_account) if la.total_amount_in_account else 0,
                "bank_name": la.bank_name,
                "created_at": _ts(la.created_at),
            }
            for la in c.lien_accounts
        ],
        "unfreeze_details": [
            {
                "id": ud.id,
                "case_id": ud.case_id,
                "unfreeze_type": ud.unfreeze_type,
                "crime_no": ud.crime_no,
                "bank_name": ud.bank_name,
                "account_no": ud.account_no,
                "amount": float(ud.amount) if ud.amount else 0,
                "created_at": _ts(ud.created_at),
            }
            for ud in c.unfreeze_details
        ],
        "refunds": [
            {
                "id": r.id,
                "case_id": r.case_id,
                "refunded": r.refunded,
                "victim_name": r.victim_name,
                "amount": float(r.amount) if r.amount else 0,
                "crime_no_or_petition_no": r.crime_no_or_petition_no,
                "created_at": _ts(r.created_at),
            }
            for r in c.refunds
        ],
        "victim": (
            {
                "id": c.victim.id,
                "case_id": c.victim.case_id,
                "first_name": c.victim.first_name,
                "last_name": c.victim.last_name,
                "age": c.victim.age,
                "gender": c.victim.gender,
                "phone": c.victim.phone,
                "email": c.victim.email,
                "house_no": c.victim.house_no,
                "street_name": c.victim.street_name,
                "city": c.victim.city,
                "state": c.victim.state,
                "country": c.victim.country,
                "pincode": c.victim.pincode,
                "amount_lost": float(c.victim.amount_lost) if c.victim.amount_lost else 0,
                "bank_account_no": c.victim.bank_account_no,
                "bank_name": c.victim.bank_name,
                "bank_branch_address": c.victim.bank_branch_address,
                "created_at": _ts(c.victim.created_at),
            }
            if c.victim else None
        ),
    }


def _case_to_list_item(c: Case) -> dict:
    """Convert ORM Case to a summary dict (no children, but with arrest_count)."""
    return {
        "id": c.id,
        "unit_id": c.unit_id,
        "fir_no": c.fir_no,
        "registration_date": c.registration_date,
        "petition_no": c.petition_no,
        "case_type": c.case_type,
        "crime_type": c.crime_type,
        "facts": c.facts,
        "status": c.status,
        "submitted_by": c.submitted_by,
        "created_at": _ts(c.created_at),
        "updated_at": _ts(c.updated_at),
        "arrest_count": len(c.arrests) if c.arrests else 0,
    }


async def _create_children_from_body(case: Case, body: CaseCreate, db: AsyncSession):
    """Create all child ORM objects from the CaseCreate payload."""
    # Direct children: petitions, lien_accounts, unfreeze_details, refunds
    for pet in body.petitions:
        db.add(Petition(
            case_id=case.id,
            fir_registered=pet.fir_registered,
            why_not=pet.why_not,
            nature=pet.nature,
            petition_type=pet.petition_type,
            amount=pet.amount,
        ))
    for la in body.lien_accounts:
        db.add(LienAccount(
            case_id=case.id,
            case_type=la.case_type,
            account_no=la.account_no,
            amount_lien_marked=la.amount_lien_marked,
            layer=la.layer,
            total_amount_in_account=la.total_amount_in_account,
            bank_name=la.bank_name,
        ))
    for ud in body.unfreeze_details:
        db.add(UnfreezeDetail(
            case_id=case.id,
            unfreeze_type=ud.unfreeze_type,
            crime_no=ud.crime_no,
            bank_name=ud.bank_name,
            account_no=ud.account_no,
            amount=ud.amount,
        ))
    for ref in body.refunds:
        db.add(Refund(
            case_id=case.id,
            refunded=ref.refunded,
            victim_name=ref.victim_name,
            amount=ref.amount,
            crime_no_or_petition_no=ref.crime_no_or_petition_no,
        ))

    # 1:1 victim — None on legacy cases until the operator fills it in.
    if body.victim is not None:
        db.add(Victim(
            case_id=case.id,
            first_name=body.victim.first_name,
            last_name=body.victim.last_name,
            age=body.victim.age,
            gender=body.victim.gender,
            phone=body.victim.phone,
            email=body.victim.email,
            house_no=body.victim.house_no,
            street_name=body.victim.street_name,
            city=body.victim.city,
            state=body.victim.state,
            country=body.victim.country,
            pincode=body.victim.pincode,
            amount_lost=body.victim.amount_lost,
            bank_account_no=body.victim.bank_account_no,
            bank_name=body.victim.bank_name,
            bank_branch_address=body.victim.bank_branch_address,
        ))

    # Arrests need flush for arrest.id before creating accomplices/accused
    arrests_with_children = []
    for arr in body.arrests:
        arrest = Arrest(
            case_id=case.id,
            name=arr.name,
            address=arr.address,
            email=arr.email,
            aadhar=arr.aadhar,
            pan=arr.pan,
            date_of_arrest=arr.date_of_arrest,
        )
        db.add(arrest)
        arrests_with_children.append((arrest, arr.accomplices, arr.accused_details))

    if arrests_with_children:
        await db.flush()  # get arrest.id values

        for arrest, accomplices, accused_details in arrests_with_children:
            for acc in accomplices:
                db.add(Accomplice(
                    arrest_id=arrest.id,
                    where_met=acc.where_met,
                    where_stayed=acc.where_stayed,
                    interrogation_details=acc.interrogation_details,
                ))
            for ad in accused_details:
                db.add(AccusedDetail(
                    arrest_id=arrest.id,
                    photo_path=ad.photo_path,
                    email=ad.email,
                    mobile=ad.mobile,
                    occupation=ad.occupation,
                    remarks=ad.remarks,
                ))


# -- POST /api/v1/cases/ ---------------------------------------------------

@router.post("/", response_model=CaseResponse)
async def create_case(
    body: CaseCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    unit_id = current_user.unit_id
    ps_id = current_user.ps_id
    if not unit_id:
        raise HTTPException(status_code=403, detail="No unit assigned to this account.")
    if not ps_id:
        raise HTTPException(status_code=403, detail="No police station assigned to this account.")

    _validate_submitted_case(body)
    _check_arrest_duplicates(body)

    # Pre-check the (unit_id, ps_id, fir_no) UNIQUE constraint and return a
    # clean 409 instead of letting the DB IntegrityError surface as 500
    # (Innspark VAPT exec summary, 2026-05-05). Scope is per-PS — FIRs are
    # independently numbered per PS in police operations (see migration 002).
    if body.fir_no:
        existing = (await db.execute(
            select(Case).where(
                Case.unit_id == unit_id,
                Case.ps_id == ps_id,
                Case.fir_no == body.fir_no,
            )
        )).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"A case with FIR No '{body.fir_no}' already exists in this PS.",
            )

    case = Case(
        unit_id=unit_id,
        ps_id=ps_id,
        fir_no=body.fir_no,
        petition_no=body.petition_no,
        registration_date=body.registration_date,
        case_type=body.case_type,
        crime_type=body.crime_type,
        facts=body.facts,
        status=body.status,
        submitted_by=current_user.user_id,
    )
    db.add(case)
    await db.flush()  # get case.id

    await _create_children_from_body(case, body, db)
    await db.commit()

    # Reload with all relations
    result = (await db.execute(
        select(Case).where(Case.id == case.id).options(*_eager_options())
    )).scalar_one()

    return _case_to_response(result)


# -- GET /api/v1/cases/all  (admin: all units) -----------------------------
# NOTE: This route MUST be declared BEFORE /{case_id} to avoid path conflict.

@router.get("/all", response_model=List[CaseListItem])
async def list_all_cases(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin view of all cases in the admin's PS (NOT cross-PS - VAPT 7.8).

    There is no global admin role - PS admins are scoped to their own unit_id.
    Equivalent to GET /cases/ when called by an admin; kept for backward
    compatibility with any frontend code that still hits /all.
    """
    if not admin.unit_id:
        raise HTTPException(status_code=403, detail="Admin account is not assigned to any PS.")

    cases = (await db.execute(
        select(Case)
        .where(Case.unit_id == admin.unit_id)
        .options(selectinload(Case.arrests))
        .order_by(Case.created_at.desc())
        .limit(limit)
        .offset(offset)
    )).scalars().all()

    return [_case_to_list_item(c) for c in cases]


# -- GET /api/v1/cases/ ----------------------------------------------------

@router.get("/", response_model=List[CaseListItem])
async def list_cases(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List cases scoped to the caller (VAPT 7.7 + 7.8).

    Scope is (unit_id, ps_id) since migration 002. Before that change, a
    single unit_id could represent multiple PSes within Bangalore City etc.

    - admin     : all cases in their PS
    - unit_user : only cases they personally submitted, in their PS
    """
    unit_id = current_user.unit_id
    ps_id = current_user.ps_id
    if not unit_id:
        raise HTTPException(status_code=403, detail="No unit assigned to this account.")
    if not ps_id:
        raise HTTPException(status_code=403, detail="No police station assigned to this account.")

    q = select(Case).where(Case.unit_id == unit_id, Case.ps_id == ps_id)
    if current_user.role != "admin":
        q = q.where(Case.submitted_by == current_user.user_id)

    cases = (await db.execute(
        q.options(selectinload(Case.arrests))
        .order_by(Case.created_at.desc())
        .limit(limit)
        .offset(offset)
    )).scalars().all()

    return [_case_to_list_item(c) for c in cases]


# -- GET /api/v1/cases/search (by FIR number) ------------------------------
# NOTE: This route MUST be declared BEFORE /{case_id} to avoid path conflict.

@router.get("/search", response_model=CaseResponse | None)
async def search_case_by_fir(
    fir_no: str = Query(...),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search for a case by FIR number within the caller's scope (VAPT 7.7+7.8).

    Scope is (unit_id, ps_id) — required for correctness now that the same
    FIR can legitimately exist for multiple PSes within one district
    (Bangalore City etc). See migration 002."""
    unit_id = current_user.unit_id
    ps_id = current_user.ps_id
    if not unit_id:
        raise HTTPException(status_code=403, detail="No unit assigned to this account.")
    if not ps_id:
        raise HTTPException(status_code=403, detail="No police station assigned to this account.")

    q = (
        select(Case)
        .where(
            Case.fir_no == fir_no,
            Case.unit_id == unit_id,
            Case.ps_id == ps_id,
        )
        .options(*_eager_options())
    )
    if current_user.role != "admin":
        q = q.where(Case.submitted_by == current_user.user_id)
    case = (await db.execute(q)).scalar_one_or_none()
    if not case:
        return None
    return _case_to_response(case)


# -- GET /api/v1/cases/search-petition (by petition number) ----------------

@router.get("/search-petition", response_model=CaseResponse | None)
async def search_case_by_petition(
    petition_no: str = Query(...),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search for a case by petition number within the caller's scope (VAPT 7.7+7.8).

    Scope is (unit_id, ps_id) — see migration 002."""
    unit_id = current_user.unit_id
    ps_id = current_user.ps_id
    if not unit_id:
        raise HTTPException(status_code=403, detail="No unit assigned to this account.")
    if not ps_id:
        raise HTTPException(status_code=403, detail="No police station assigned to this account.")

    q = (
        select(Case)
        .where(
            Case.petition_no == petition_no,
            Case.unit_id == unit_id,
            Case.ps_id == ps_id,
        )
        .options(*_eager_options())
    )
    if current_user.role != "admin":
        q = q.where(Case.submitted_by == current_user.user_id)
    case = (await db.execute(q)).scalar_one_or_none()
    if not case:
        return None
    return _case_to_response(case)


# -- GET /api/v1/cases/{case_id} -------------------------------------------

@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    case = (await db.execute(
        select(Case).where(Case.id == case_id).options(*_eager_options())
    )).scalar_one_or_none()

    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # VAPT 7.7 + 7.8: enforce per-record + per-PS authorization.
    check_record_access(case, current_user)

    return _case_to_response(case)


# -- PUT /api/v1/cases/{case_id} -------------------------------------------

@router.put("/{case_id}", response_model=CaseResponse)
async def update_case(
    case_id: str,
    body: CaseCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    case = (await db.execute(
        select(Case).where(Case.id == case_id).options(*_eager_options())
    )).scalar_one_or_none()

    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # VAPT 7.7 + 7.8: enforce per-record + per-PS authorization.
    check_record_access(case, current_user)

    _validate_submitted_case(body)
    _check_arrest_duplicates(body)

    # Update case fields.
    # NOTE: fir_no is intentionally NOT updated - per product decision,
    # the FIR number is immutable after creation. Sending a different
    # value in the body is silently ignored.
    case.petition_no = body.petition_no
    case.registration_date = body.registration_date
    case.case_type = body.case_type
    case.crime_type = body.crime_type
    case.facts = body.facts
    case.status = body.status
    # NOTE: submitted_by is intentionally NOT changed on update. The
    # original submitter remains the owner of the record (used by the
    # per-record authorization check).

    # Delete all existing children (cascade handles grandchildren)
    for arrest in list(case.arrests):
        await db.delete(arrest)
    for petition in list(case.petitions):
        await db.delete(petition)
    for la in list(case.lien_accounts):
        await db.delete(la)
    for ud in list(case.unfreeze_details):
        await db.delete(ud)
    for ref in list(case.refunds):
        await db.delete(ref)
    if case.victim is not None:
        await db.delete(case.victim)

    await db.flush()

    # Recreate children from payload
    await _create_children_from_body(case, body, db)
    await db.commit()

    # Reload with all relations
    result = (await db.execute(
        select(Case).where(Case.id == case.id).options(*_eager_options())
    )).scalar_one()

    return _case_to_response(result)


# -- DELETE /api/v1/cases/{case_id} ----------------------------------------

@router.delete("/{case_id}")
async def delete_case(
    case_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    case = (await db.execute(
        select(Case).where(Case.id == case_id)
    )).scalar_one_or_none()

    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # VAPT 7.7 + 7.8: enforce per-record + per-PS authorization.
    check_record_access(case, current_user)

    await db.delete(case)  # cascade deletes children
    await db.commit()
    return {"ok": True, "deleted": case_id}
