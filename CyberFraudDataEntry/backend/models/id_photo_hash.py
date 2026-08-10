"""Fingerprints of an uploaded ID photo (migration 019).

One row per image, written by analysis/hash_id_photos.py. Stores two
fingerprints of the pixels and NOTHING read out of the picture — no
name, no number, no date of birth.

The two signals are not equal, and the difference is the whole point:

  file_sha256  Byte-identical. Two accounts with the same SHA-256 have
               literally the same file attached. There is no room for
               interpretation — either it is the same upload re-used, or
               someone sent the identical image twice.

  dhash        Visually similar. Useful for a document re-photographed
               or re-saved, but on ID documents it is weak evidence on
               its own, because ID cards are near-identical by design.

Two accounts sharing a fingerprint are a lead worth checking; that is
not, on its own, evidence of anything.
"""
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func

from database import Base


class IdPhotoHash(Base):
    __tablename__ = "id_photo_hashes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id = Column(
        String(36), ForeignKey("all_accounts.id", ondelete="CASCADE"), nullable=False
    )
    file_path = Column(String(500), nullable=False, unique=True)
    #: SHA-256 of the file bytes, 64 hex chars. The primary duplicate signal.
    file_sha256 = Column(String(64), nullable=False)
    #: 576-bit difference hash (24x24), 144 hex chars. Secondary signal.
    #: NOT the textbook 8x8 — see the note in migration 019 for why 8x8
    #: merged 28 different documents into one false "cluster".
    dhash = Column(String(160), nullable=False)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    parser_version = Column(String(30), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
