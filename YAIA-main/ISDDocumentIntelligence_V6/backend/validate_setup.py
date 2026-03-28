"""Quick validation of V6 imports and configuration."""
import sys

errors = []

# Test 1: Config
try:
    from config import CHROMA_PATH_SMAC, CHROMA_PATH_IR, USE_LLM_PARSER_SMAC, USE_LLM_PARSER_IR, EMBED_MODEL, PDF_MODEL
    print(f"[OK] config: SMAC_PATH={CHROMA_PATH_SMAC}, IR_PATH={CHROMA_PATH_IR}")
    print(f"     LLM_SMAC={USE_LLM_PARSER_SMAC}, LLM_IR={USE_LLM_PARSER_IR}")
except Exception as e:
    errors.append(f"config: {e}")
    print(f"[FAIL] config: {e}")

# Test 2: ir_parser
try:
    from ir_parser import parse_ir_document, parse_ir_docx
    print("[OK] ir_parser imports")
except Exception as e:
    errors.append(f"ir_parser: {e}")
    print(f"[FAIL] ir_parser: {e}")

# Test 3: rag_ir
try:
    from rag_ir import index_ir, ask, get_indexed_doc_list, clear_all, _collection_name
    print(f"[OK] rag_ir: collection={_collection_name}")
except Exception as e:
    errors.append(f"rag_ir: {e}")
    print(f"[FAIL] rag_ir: {e}")

# Test 4: rag_smac
try:
    from rag_smac import index_document, ask_pdf, clear_all_documents, get_indexed_doc_list
    print("[OK] rag_smac imports")
except Exception as e:
    errors.append(f"rag_smac: {e}")
    print(f"[FAIL] rag_smac: {e}")

# Test 5: structured_tables
try:
    from structured_tables import find_ir_docs_by_name, store_ir_report, store_smac_report
    print("[OK] structured_tables imports")
except Exception as e:
    errors.append(f"structured_tables: {e}")
    print(f"[FAIL] structured_tables: {e}")

# Test 6: app imports
try:
    from rag_smac import index_document as index_document_smac, ask_pdf, ask_docs_agent, clear_all_documents, clear_documents_by_source, get_all_doc_chunks, get_indexed_doc_list as get_indexed_doc_list_smac
    import rag_ir
    print("[OK] app imports (rag_smac + rag_ir)")
except Exception as e:
    errors.append(f"app imports: {e}")
    print(f"[FAIL] app imports: {e}")

# Test 7: Parse sample IR
try:
    import os
    sample = os.path.join(os.path.dirname(__file__), "..", "Sample IR John Doe.docx")
    if os.path.exists(sample):
        fields, name = parse_ir_docx(sample)
        print(f"[OK] IR parser: {len(fields)} fields, accused='{name}'")
        if len(fields) < 100:
            errors.append(f"IR parser: only {len(fields)} fields (expected 100+)")
            print(f"[WARN] Expected 100+ fields, got {len(fields)}")
    else:
        print(f"[SKIP] Sample file not found: {sample}")
except Exception as e:
    errors.append(f"IR parser test: {e}")
    print(f"[FAIL] IR parser test: {e}")

# Summary
print(f"\n{'='*50}")
if errors:
    print(f"FAILED: {len(errors)} error(s)")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("ALL TESTS PASSED")
    sys.exit(0)
