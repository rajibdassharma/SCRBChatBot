"""
reset_progress.py — Reset the bulk indexing progress DB so all files are re-queued.

The progress DB lives in the same folder as this script (dbscripts/).

Run from the dbscripts folder:
    python reset_progress.py
"""
import os
import sqlite3

db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".smac_bulk_progress.db")
db = sqlite3.connect(db_path)
db.execute("UPDATE progress SET status='pending' WHERE status='done'")
db.commit()
pending = db.execute("SELECT COUNT(*) FROM progress WHERE status='pending'").fetchone()[0]
failed  = db.execute("SELECT COUNT(*) FROM progress WHERE status='failed'").fetchone()[0]
print(f"Reset complete: {pending} files pending, {failed} files failed (will also retry)")
db.close()
