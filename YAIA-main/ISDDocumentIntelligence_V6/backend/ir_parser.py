"""
IR Document Parser — extracts structured fields from IR Form-16 DOCX/PDF files.

No LLM, no Docling. Pure Python table parsing.
Handles 3-column tables: [Serial No | Field Name | Value]
Skips free-form text sections after tables.

Returns a list of {serial_no, field_key, field_value} dicts.
"""

import re
import os
from typing import List, Dict, Tuple
from docx import Document as DocxDocument


# Values considered empty/nil
_NIL_VALUES = frozenset({
    "", "-", "–", "—", "nil", "-nil-", "n/a", "none",
    "not available", "not applicable", "na", ".", "..", "---",
})


def _fix_encoding(text: str) -> str:
    """Fix common encoding artifacts."""
    if not text:
        return ""
    t = text.replace("\u2019", "'").replace("\u2018", "'")
    t = t.replace("\u201c", '"').replace("\u201d", '"')
    t = t.replace("\u2013", "-").replace("\u2014", "-")
    t = t.replace("\ufffd", "'")
    return t


def _clean_label(text: str) -> str:
    """Clean field key/label: single line, collapsed whitespace."""
    t = _fix_encoding(text)
    t = t.replace("\r", " ").replace("\n", " ")
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()


def _clean_value(text: str) -> str:
    """Clean field value: preserve line breaks for multi-value fields."""
    t = _fix_encoding(text)
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse multiple blank lines but keep single line breaks
    t = re.sub(r"\n{3,}", "\n\n", t)
    # Clean up each line
    lines = [re.sub(r"\s{2,}", " ", ln).strip() for ln in t.split("\n")]
    # Remove empty lines at start/end
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def _get_row_cells(row) -> List[str]:
    """Extract and deduplicate adjacent identical cells (merged cells in DOCX).
    Returns raw text with encoding fixed but line breaks preserved."""
    raw = [_fix_encoding(c.text) for c in row.cells]
    return [raw[i].strip() for i in range(len(raw)) if i == 0 or raw[i].strip() != raw[i - 1].strip()]


def _is_serial(text: str) -> bool:
    """Check if text looks like a serial number (e.g., '1', '25', '130.')."""
    return bool(re.match(r"^\d{1,3}\.?\s*$", text.strip()))


def _extract_serial(text: str) -> str:
    """Extract numeric part from serial number."""
    m = re.match(r"^(\d{1,3})", text.strip())
    return m.group(1) if m else ""


def _is_nil(value: str) -> bool:
    """Check if a value is considered nil/empty."""
    return value.lower().strip(".- ") in _NIL_VALUES


def parse_ir_docx(docx_path: str) -> Tuple[List[Dict[str, str]], str]:
    """
    Parse an IR Form-16 DOCX file.

    Returns:
        (fields, accused_name)
        - fields: List of {serial_no, field_key, field_value}
        - accused_name: Name extracted from the document
    """
    try:
        doc = DocxDocument(docx_path)
    except Exception as e:
        print(f"[IR-Parser] Cannot open DOCX '{docx_path}': {e}")
        return [], ""

    if not doc.tables:
        print(f"[IR-Parser] No tables found in {os.path.basename(docx_path)}")
        return [], ""

    fields: List[Dict[str, str]] = []
    accused_name = ""
    row_counter = 0
    _header_words = {"sl no", "sl no.", "description", "particulars", "serial no", "serial no."}

    for table in doc.tables:
        for row in table.rows:
            cells = _get_row_cells(row)

            if not cells or not any(c for c in cells):
                continue

            first = cells[0].strip()

            if _is_serial(first) and len(cells) >= 2:
                # Row with serial number: ['27.', 'Field Name', 'Value']
                serial = _extract_serial(first)
                field_key = _clean_label(cells[1])
                field_value = _clean_value(cells[2]) if len(cells) > 2 else ""

                if not field_key:
                    continue
                if _is_nil(field_value):
                    field_value = ""

                row_counter += 1
                fields.append({
                    "serial_no": serial,
                    "field_key": field_key,
                    "field_value": field_value,
                })

            elif len(cells) >= 2 and not first and cells[1].strip():
                # Empty serial number: ['', 'Field Name', 'Value']
                field_key = _clean_label(cells[1])

                if not field_key:
                    continue
                if field_key.lower().strip(".") in _header_words:
                    continue

                field_value = _clean_value(cells[2]) if len(cells) > 2 else ""
                if _is_nil(field_value):
                    field_value = ""

                row_counter += 1
                fields.append({
                    "serial_no": str(row_counter),
                    "field_key": field_key,
                    "field_value": field_value,
                })

            elif len(cells) >= 2 and not _is_serial(first) and first:
                # Non-serial, non-empty first cell (header table or label row)
                key = cells[0].lower()
                val = _clean_value(cells[1]) if len(cells) > 1 else ""
                if "name" in key and "accused" in key and val:
                    accused_name = val
                    fields.append({
                        "serial_no": "0",
                        "field_key": _clean_label(cells[0]),
                        "field_value": val,
                    })

    # Extract accused name from fields if not found in header
    if not accused_name:
        for f in fields:
            fk = f["field_key"].lower()
            if "name" in fk and "accused" in fk and f["field_value"]:
                accused_name = f["field_value"]
                break

    print(f"[IR-Parser] Extracted {len(fields)} fields from {len(doc.tables)} tables in {os.path.basename(docx_path)}")
    return fields, accused_name


def parse_ir_document(file_path: str, filename: str) -> Tuple[List[Dict[str, str]], str]:
    """
    Parse any IR document (DOCX or PDF).

    Returns:
        (fields, accused_name)
    """
    ext = os.path.splitext(filename)[1].lower()

    if ext == ".docx":
        return parse_ir_docx(file_path)
    elif ext == ".doc":
        # Try Word COM conversion on Windows
        try:
            docx_path = _convert_doc_to_docx(file_path)
            if docx_path:
                result = parse_ir_docx(docx_path)
                import shutil
                shutil.rmtree(os.path.dirname(docx_path), ignore_errors=True)
                return result
        except Exception as e:
            print(f"[IR-Parser] .doc conversion failed: {e}")
        return [], ""
    elif ext == ".pdf":
        print(f"[IR-Parser] PDF parsing not yet implemented for IR. Use DOCX format.")
        return [], ""
    else:
        print(f"[IR-Parser] Unsupported format: {ext}")
        return [], ""


def _convert_doc_to_docx(doc_path: str):
    """Convert .doc to .docx using Word COM (Windows only)."""
    try:
        import win32com.client
        import pythoncom
        import tempfile

        pythoncom.CoInitialize()
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        abs_path = os.path.abspath(doc_path)
        doc = word.Documents.Open(abs_path)
        tmp_dir = tempfile.mkdtemp()
        base = os.path.splitext(os.path.basename(doc_path))[0]
        docx_path = os.path.join(tmp_dir, base + ".docx")
        doc.SaveAs2(docx_path, FileFormat=12)
        doc.Close(False)
        word.Quit()
        pythoncom.CoUninitialize()
        if os.path.exists(docx_path):
            return docx_path
    except Exception as e:
        print(f"[IR-Parser] Word COM conversion failed: {e}")
    return None


# --- Test utility ---
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python ir_parser.py <path_to_ir_file>")
        sys.exit(1)

    fpath = sys.argv[1]
    fname = os.path.basename(fpath)
    fields, name = parse_ir_document(fpath, fname)

    print(f"\nAccused: {name}")
    print(f"Fields: {len(fields)}\n")
    for f in fields:
        val_display = f["field_value"][:60] if f["field_value"] else "(empty)"
        print(f"  {f['serial_no']:>4} | {f['field_key'][:50]:50s} | {val_display}")
