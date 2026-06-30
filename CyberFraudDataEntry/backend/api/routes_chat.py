"""
POST /api/v1/chat/ask — single endpoint for the natural-language chat.

Two LLM calls per request:
  1. Question + schema → SQL.
  2. Question + result rows → 1-3 sentence summary.

Between them: safety validation + execution with a 5s server-side timeout.
Every request is logged into chat_messages — question, SQL, row_count,
error, latency — for traceability.

NB. Per product decision (2026-06-15), the chat has WIDER scope than the
dashboard: all authenticated users see all PS data. The dashboard's
per-PS isolation does not apply here.
"""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.chat_message import ChatMessage
from schemas.chat import ChatRequest, ChatResponse
from api.deps import get_current_user, CurrentUser
from chat import sql_generator, safe_executor
from chat.ollama_client import OllamaUnreachable, OllamaError

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


@router.post("/ask", response_model=ChatResponse)
async def ask(
    body: ChatRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    started = time.time()
    audit = ChatMessage(
        user_id=current_user.user_id,
        unit_id=current_user.unit_id,
        ps_id=current_user.ps_id,
        question=body.question.strip(),
    )
    try:
        # 1. Question → SQL
        try:
            raw = await sql_generator.generate_sql(body.question)
        except OllamaUnreachable as e:
            raise HTTPException(status_code=503, detail=str(e))
        except OllamaError as e:
            raise HTTPException(status_code=502, detail=str(e))

        if raw.strip().upper().startswith("NO_SQL"):
            audit.error = "model declined to generate SQL"
            audit.latency_ms = int((time.time() - started) * 1000)
            db.add(audit)
            await db.commit()
            return ChatResponse(
                answer=(
                    "I don't have enough information in the database schema "
                    "to answer that. Try rephrasing or ask about cases, arrests, "
                    "victims, petitions, lien accounts, or refunds."
                ),
                row_count=0,
                latency_ms=audit.latency_ms,
            )

        sql = safe_executor.extract_sql(raw)
        try:
            sql_validated = safe_executor.validate(sql)
        except safe_executor.SqlRejected as e:
            audit.generated_sql = sql
            audit.error = f"sql rejected: {e}"
            audit.latency_ms = int((time.time() - started) * 1000)
            db.add(audit)
            await db.commit()
            raise HTTPException(
                status_code=422,
                detail=f"Generated query was not safe to run: {e}",
            )

        audit.generated_sql = sql_validated

        # 2. Execute
        try:
            rows, total = await safe_executor.execute(db, sql_validated)
        except Exception as e:  # noqa: BLE001
            audit.error = f"execute error: {type(e).__name__}: {e}"[:500]
            audit.latency_ms = int((time.time() - started) * 1000)
            db.add(audit)
            await db.commit()
            raise HTTPException(
                status_code=500,
                detail="Database error while running the generated query. "
                       "Try rephrasing your question.",
            )

        audit.row_count = total
        safe_rows = safe_executor.safe_serialise_rows(rows)

        # 3. Rows → natural-language summary
        try:
            answer = await sql_generator.summarise(
                body.question, sql_validated, safe_rows, total,
            )
        except (OllamaUnreachable, OllamaError):
            # Don't fail the whole request — return rows with a generic
            # answer, since the data is the valuable part.
            answer = (
                "Found {n} matching record(s)."
                if total != 1 else "Found 1 matching record."
            ).format(n=total)

        # 4. (Q + A) → follow-up suggestions. Best-effort: if Ollama
        # is unreachable, slow, or returns garbage we just hand back
        # an empty list — the UI hides the chip row when it's empty.
        # Skip entirely when there are zero rows (nothing to drill into).
        followups: list[str] = []
        if total > 0:
            try:
                followups = await sql_generator.suggest_followups(
                    body.question, answer, total,
                )
            except (OllamaUnreachable, OllamaError):
                pass
            except Exception:  # noqa: BLE001
                log.exception("Follow-up generation failed")

        audit.latency_ms = int((time.time() - started) * 1000)
        db.add(audit)
        await db.commit()

        return ChatResponse(
            answer=answer.strip() or f"Found {total} matching record(s).",
            sql=sql_validated,
            rows=safe_rows,
            row_count=total,
            latency_ms=audit.latency_ms,
            followups=followups,
        )

    except HTTPException:
        # Already audited above if applicable. Re-raise.
        raise
    except Exception as e:  # noqa: BLE001
        log.exception("Unhandled chat error")
        audit.error = f"unhandled: {type(e).__name__}: {e}"[:500]
        audit.latency_ms = int((time.time() - started) * 1000)
        try:
            db.add(audit)
            await db.commit()
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(status_code=500, detail="Chat failed. Please try again.")
