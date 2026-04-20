"""
scripts/test_trio_c.py
======================
Test suite for trio_c tools:
  - authority_lookup_tool.py  (pure logic, no external calls)
  - severity_score_tool.py    (live Groq LLM call)
  - complaint_draft_tool.py   (integration: severity + RAG + lookup + Groq)
  - smart_rag_tool.py         (embedding model, no external API)

Run from project root:
    python scripts/test_trio_c.py

Requires:
    - configs/authority_data.json  present
    - data/environmental_laws.txt  present
    - GROQ_API_KEY                 in .env or environment
    - pip packages: groq, sentence-transformers, python-dotenv, numpy
"""

import sys
import os
import json
import time
import traceback

# ---------------------------------------------------------------------------
# Path setup — run from project root
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
PASS  = "\033[92m[PASS]\033[0m"
FAIL  = "\033[91m[FAIL]\033[0m"
WARN  = "\033[93m[WARN]\033[0m"
INFO  = "\033[94m[INFO]\033[0m"
SKIP  = "\033[90m[SKIP]\033[0m"

results = []  # (tool, test_name, status, detail)

def record(tool, name, passed, detail=""):
    tag = PASS if passed else FAIL
    print(f"  {tag} {name}" + (f" — {detail}" if detail else ""))
    results.append((tool, name, passed, detail))

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def summary():
    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    total  = len(results)
    passed = sum(1 for _, _, ok, _ in results if ok)
    failed = total - passed
    for tool, name, ok, detail in results:
        tag = PASS if ok else FAIL
        print(f"  {tag}  [{tool}]  {name}")
        if not ok and detail:
            print(f"         {detail}")
    print(f"\n  {passed}/{total} passed", end="")
    if failed:
        print(f"  |  {failed} FAILED ← fix before integration", end="")
    print("\n")


# ===========================================================================
# 1. AUTHORITY LOOKUP TOOL
# ===========================================================================
section("1 · authority_lookup_tool")

try:
    from app.tools.trio_c.authority_lookup_tool import lookup_authority

    # --- 1.1 Known key, severity 1 → level1 ---
    try:
        res = lookup_authority("Air Pollution", "Punjab", "Amritsar", severity=1)
        ok = (
            res.get("authority_name") == "DC Office"
            and res.get("current_level") == "level1"
            and res.get("current_level_num") == 1
            and res.get("authority_email") == "dc-asr@punjab.gov.in"
        )
        record("authority_lookup", "severity=1 → level1, correct authority", ok,
               f"got: {res.get('authority_name')} / {res.get('current_level')}")
    except Exception as e:
        record("authority_lookup", "severity=1 → level1", False, str(e))

    # --- 1.2 severity 2 → level2 ---
    try:
        res = lookup_authority("Air Pollution", "Punjab", "Amritsar", severity=2)
        ok = (
            res.get("authority_name") == "Punjab Pollution Control Board"
            and res.get("current_level") == "level2"
            and res.get("current_level_num") == 2
        )
        record("authority_lookup", "severity=2 → level2", ok,
               f"got: {res.get('authority_name')}")
    except Exception as e:
        record("authority_lookup", "severity=2 → level2", False, str(e))

    # --- 1.3 severity 3 → level3 ---
    try:
        res = lookup_authority("Air Pollution", "Punjab", "Amritsar", severity=3)
        ok = (
            res.get("authority_name") == "Central Pollution Control Board"
            and res.get("current_level") == "level3"
            and res.get("current_level_num") == 3
        )
        record("authority_lookup", "severity=3 → level3", ok,
               f"got: {res.get('authority_name')}")
    except Exception as e:
        record("authority_lookup", "severity=3 → level3", False, str(e))

    # --- 1.4 severity 4 → level4 ---
    try:
        res = lookup_authority("Air Pollution", "Punjab", "Amritsar", severity=4)
        ok = (
            res.get("authority_name") == "CPGRAMS"
            and res.get("current_level") == "level4"
            and res.get("current_level_num") == 4
        )
        record("authority_lookup", "severity=4 → level4", ok,
               f"got: {res.get('authority_name')}")
    except Exception as e:
        record("authority_lookup", "severity=4 → level4", False, str(e))

    # --- 1.5 severity 5 → level4, level_num should be 4 ---
    try:
        res = lookup_authority("Air Pollution", "Punjab", "Amritsar", severity=5)
        ok = (
            res.get("current_level") == "level4"
            and res.get("current_level_num") == 4   # NOT 5
        )
        record("authority_lookup", "severity=5 central override → level4, level_num=4",
               ok, f"current_level_num={res.get('current_level_num')}")
    except Exception as e:
        record("authority_lookup", "severity=5 clamped (BUG-02)", False, str(e))

    # --- 1.5b severity=5 override → CPGRAMS (central authority) ---
    try:
        res = lookup_authority("Air Pollution", "Punjab", "Amritsar", severity=5)
        ok = res.get("authority_name") == "CPGRAMS"
        record("authority_lookup", "severity=5 override → CPGRAMS (central)", ok,
            f"got: {res.get('authority_name')}")
    except Exception as e:
        record("authority_lookup", "severity=5 → CPGRAMS", False, str(e))

    # --- 1.6 Unknown key → graceful fallback ---
    try:
        res = lookup_authority("Noise Pollution", "Mars", "Olympus", severity=1)
        ok = (
            res.get("authority_name") == "Unknown Authority"
            and res.get("authority_email") == ""
            and res.get("current_level") == "level1"
        )
        record("authority_lookup", "unknown key → Unknown Authority fallback", ok,
               f"got: {res.get('authority_name')}")
    except Exception as e:
        record("authority_lookup", "unknown key fallback", False, str(e))

    # --- 1.7 Case insensitivity ---
    try:
        res = lookup_authority("air pollution", "PUNJAB", "AMRITSAR", severity=1)
        ok = res.get("authority_name") != "Unknown Authority"
        record("authority_lookup", "case-insensitive key matching", ok,
               f"got: {res.get('authority_name')}")
    except Exception as e:
        record("authority_lookup", "case-insensitive matching", False, str(e))

    # --- 1.8 Return shape: all required keys present ---
    try:
        res = lookup_authority("Air Pollution", "Punjab", "Amritsar", severity=2)
        required_keys = {
            "authority_name", "authority_email", "authority_portal",
            "authority_phone", "current_level", "current_level_num"
        }
        missing = required_keys - res.keys()
        ok = len(missing) == 0
        record("authority_lookup", "return dict has all required keys", ok,
               f"missing: {missing}" if missing else "")
    except Exception as e:
        record("authority_lookup", "return shape", False, str(e))

    # --- 1.9 level_num is an int, not a string ---
    try:
        res = lookup_authority("Air Pollution", "Punjab", "Amritsar", severity=2)
        ok = isinstance(res.get("current_level_num"), int)
        record("authority_lookup", "current_level_num is int (not str)", ok,
               f"type: {type(res.get('current_level_num'))}")
    except Exception as e:
        record("authority_lookup", "current_level_num type", False, str(e))

except ImportError as e:
    print(f"  {WARN} Could not import authority_lookup_tool: {e}")
    print("        (Check BUG-03 — filename vs import path mismatch)")


# ===========================================================================
# 2. SMART RAG TOOL
# ===========================================================================
section("2 · smart_rag_tool")

try:
    from app.tools.trio_c.smart_rag_tool import retrieve_laws

    # --- 2.1 Returns a list ---
    try:
        res = retrieve_laws("air pollution factory emissions", top_k=3)
        ok = isinstance(res, list)
        record("smart_rag", "returns a list", ok, f"type: {type(res)}")
    except Exception as e:
        record("smart_rag", "returns a list", False, str(e))

    # --- 2.2 Respects top_k ---
    try:
        res = retrieve_laws("water pollution", top_k=3)
        ok = len(res) == 3
        record("smart_rag", "top_k=3 returns exactly 3 results", ok,
               f"got {len(res)}")
    except Exception as e:
        record("smart_rag", "top_k respected", False, str(e))

    # --- 2.3 top_k=1 ---
    try:
        res = retrieve_laws("noise pollution road traffic", top_k=1)
        ok = len(res) == 1
        record("smart_rag", "top_k=1 returns exactly 1 result", ok,
               f"got {len(res)}")
    except Exception as e:
        record("smart_rag", "top_k=1", False, str(e))

    # --- 2.4 Each item has 'law' and 'score' keys ---
    try:
        res = retrieve_laws("industrial waste dumping", top_k=2)
        ok = all("law" in item and "score" in item for item in res)
        record("smart_rag", "each result has 'law' and 'score' keys", ok)
    except Exception as e:
        record("smart_rag", "result shape", False, str(e))

    # --- 2.5 Score is a float in [0, 1] ---
    try:
        res = retrieve_laws("chemical effluents river", top_k=3)
        ok = all(isinstance(item["score"], float) and 0.0 <= item["score"] <= 1.0
                 for item in res)
        bad = [item["score"] for item in res if not (0.0 <= item["score"] <= 1.0)]
        record("smart_rag", "scores are float in [0, 1]", ok,
               f"out-of-range: {bad}" if bad else "")
    except Exception as e:
        record("smart_rag", "score range", False, str(e))

    # --- 2.6 Results are sorted descending by score ---
    try:
        res = retrieve_laws("air pollution factory", top_k=3)
        scores = [item["score"] for item in res]
        ok = scores == sorted(scores, reverse=True)
        record("smart_rag", "results sorted by score descending", ok,
               f"scores: {scores}")
    except Exception as e:
        record("smart_rag", "sorted order", False, str(e))

    # --- 2.7 Semantically relevant: 'air pollution' top hit mentions air/pollution ---
    try:
        res = retrieve_laws("air pollution smoke factory", top_k=1)
        law_text = res[0]["law"].lower()
        ok = any(kw in law_text for kw in ["air", "pollution", "emission", "smoke"])
        record("smart_rag", "top hit for 'air pollution' is semantically relevant",
               ok, f"got: {res[0]['law'][:80]}")
    except Exception as e:
        record("smart_rag", "semantic relevance", False, str(e))

    # --- 2.8 'law' value is a non-empty string ---
    try:
        res = retrieve_laws("illegal dumping", top_k=2)
        ok = all(isinstance(item["law"], str) and len(item["law"]) > 0 for item in res)
        record("smart_rag", "'law' is non-empty string", ok)
    except Exception as e:
        record("smart_rag", "law field type", False, str(e))

except ImportError as e:
    print(f"  {WARN} Could not import smart_rag_tool: {e}")
    print("        (Check BUG-03 — filename vs import path mismatch)")


# ===========================================================================
# 3. SEVERITY SCORE TOOL  (live Groq call)
# ===========================================================================
section("3 · severity_score_tool  [live LLM — may be slow]")

try:
    from app.tools.trio_c.severity_score_tool import calculate_severity

    # --- 3.1 Returns correct shape ---
    try:
        res = calculate_severity(
            issue="Air Pollution",
            description="Black smoke billowing from factory chimney all day.",
            location="Amritsar, Punjab"
        )
        ok = "severity" in res and "success" in res
        record("severity_score", "returns dict with 'severity' and 'success'", ok,
               f"got: {res}")
    except Exception as e:
        record("severity_score", "return shape", False, str(e))

    # --- 3.2 Severity is int in {1,2,3,4} ---
    try:
        res = calculate_severity(
            issue="Air Pollution",
            description="Thick black smoke from factory, residents coughing.",
            location="Amritsar, Punjab"
        )
        ok = isinstance(res.get("severity"), int) and res["severity"] in {1, 2, 3, 4}
        record("severity_score", "severity is int in {1,2,3,4}", ok,
               f"got: {res.get('severity')}")
    except Exception as e:
        record("severity_score", "severity valid range", False, str(e))

    # --- 3.3 Minor issue → severity 1 or 2 ---
    try:
        time.sleep(1)   # avoid rate limit
        res = calculate_severity(
            issue="Noise Pollution",
            description="Occasional construction noise during the day.",
            location="Amritsar, Punjab"
        )
        ok = res.get("severity") in {1, 2}
        record("severity_score", "minor issue → severity ≤ 2", ok,
               f"got: {res.get('severity')}")
    except Exception as e:
        record("severity_score", "minor issue low severity", False, str(e))

    # --- 3.4 Critical issue → severity 3 or 4 ---
    try:
        time.sleep(1)
        res = calculate_severity(
            issue="Water Pollution",
            description="Factory dumping untreated toxic chemical waste directly into the river, fish dying, residents falling ill.",
            location="Ludhiana, Punjab"
        )
        ok = res.get("severity") in {3, 4}
        record("severity_score", "critical issue → severity ≥ 3", ok,
               f"got: {res.get('severity')}")
    except Exception as e:
        record("severity_score", "critical issue high severity", False, str(e))

    # --- 3.5 success=True on a normal call ---
    try:
        res = calculate_severity(
            issue="Air Pollution",
            description="Visible smoke from factory.",
            location="Amritsar, Punjab"
        )
        ok = res.get("success") is True
        record("severity_score", "success=True on clean call", ok,
               f"got success={res.get('success')}")
    except Exception as e:
        record("severity_score", "success flag", False, str(e))

    # --- 3.6 Fallback on empty inputs (edge case — model should still return 1-4) ---
    try:
        time.sleep(1)
        res = calculate_severity(issue="", description="", location="")
        ok = res.get("severity") in {1, 2, 3, 4}
        record("severity_score", "empty inputs → still returns valid severity", ok,
               f"got: {res.get('severity')}")
    except Exception as e:
        record("severity_score", "empty inputs edge case", False, str(e))

except ImportError as e:
    print(f"  {WARN} Could not import severity_score_tool: {e}")
    print("        (Check BUG-03 — filename vs import path mismatch)")


# ===========================================================================
# 4. COMPLAINT DRAFT TOOL  (full integration)
# ===========================================================================
section("4 · complaint_draft_tool  [integration — slow]")

try:
    from app.tools.trio_c.complaint_draft_tool import draft_complaint

    # --- 4.1 Returns a non-empty string ---
    try:
        time.sleep(1)
        result = draft_complaint(
            issue="Air Pollution",
            description="Factory chimney emitting thick black smoke all day, residents reporting respiratory issues.",
            location="Amritsar, Punjab"
        )
        ok = isinstance(result, str) and len(result.strip()) > 0
        record("complaint_draft", "returns non-empty string", ok,
               f"length={len(result)}")
    except Exception as e:
        record("complaint_draft", "returns non-empty string", False, str(e))

    # --- 4.2 Does not return the failure sentinel ---
    try:
        time.sleep(1)
        result = draft_complaint(
            issue="Air Pollution",
            description="Dense smoke from cement plant affecting nearby village.",
            location="Amritsar, Punjab"
        )
        ok = result not in {
            "Failed to generate complaint.",
            "Unable to determine correct authority for this issue."
        }
        record("complaint_draft", "does not return failure sentinel", ok,
               f"got: {result[:80]!r}" if not ok else "")
    except Exception as e:
        record("complaint_draft", "not failure sentinel", False, str(e))

    # --- 4.3 Output is under 200 words (prompt says ≤120, give slack) ---
    try:
        time.sleep(1)
        result = draft_complaint(
            issue="Air Pollution",
            description="Black smoke from local brick kiln.",
            location="Amritsar, Punjab"
        )
        word_count = len(result.split())
        ok = word_count <= 200
        record("complaint_draft", "output ≤ 200 words", ok,
               f"word_count={word_count}")
    except Exception as e:
        record("complaint_draft", "output length", False, str(e))

    # --- 4.4 Does not contain "Dear Sir" / letter-style opener ---
    try:
        time.sleep(1)
        result = draft_complaint(
            issue="Water Pollution",
            description="Untreated effluent from paper mill discharged into canal.",
            location="Amritsar, Punjab"
        )
        bad_phrases = ["dear sir", "dear madam", "to whomsoever", "respected sir"]
        found = [p for p in bad_phrases if p in result.lower()]
        ok = len(found) == 0
        record("complaint_draft", "no letter-style opener (Dear Sir etc.)", ok,
               f"found: {found}" if found else "")
    except Exception as e:
        record("complaint_draft", "no letter opener", False, str(e))

    # --- 4.5 Mentions authority name in output ---
    try:
        time.sleep(1)
        result = draft_complaint(
            issue="Air Pollution",
            description="Industrial smoke from steel plant causing smog.",
            location="Amritsar, Punjab"
        )
        # At severity ≤2 we'd expect DC Office or PPCB
        ok = any(name in result for name in [
            "DC Office", "Punjab Pollution Control Board",
            "Central Pollution Control Board", "CPGRAMS"
        ])
        record("complaint_draft", "authority name present in output", ok,
               f"first 100 chars: {result[:100]!r}")
    except Exception as e:
        record("complaint_draft", "authority name in output", False, str(e))

    # --- 4.6 Unknown location → graceful string, no exception ---
    try:
        time.sleep(1)
        result = draft_complaint(
            issue="Noise Pollution",
            description="Loudspeakers at night.",
            location="Atlantis, Utopia"
        )
        ok = isinstance(result, str) and len(result.strip()) > 0
        record("complaint_draft", "unknown location → graceful string, no crash", ok,
               f"got: {result[:80]!r}")
    except Exception as e:
        record("complaint_draft", "unknown location graceful", False, str(e))

    # --- 4.7 location with extra whitespace parsed correctly ---
    try:
        time.sleep(1)
        result = draft_complaint(
            issue="Air Pollution",
            description="Factory smoke visible from highway.",
            location="  Amritsar ,  Punjab  "
        )
        ok = result not in {
            "Unable to determine correct authority for this issue.",
            "Failed to generate complaint."
        }
        record("complaint_draft", "whitespace-padded location parsed correctly", ok,
               f"got: {result[:80]!r}")
    except Exception as e:
        record("complaint_draft", "whitespace location", False, str(e))

except ImportError as e:
    print(f"  {WARN} Could not import complaint_draft_tool: {e}")
    print("        (Check BUG-03 — filename vs import path mismatch)")


# ===========================================================================
# 5. CONTEXT DATACLASS  (no external deps)
# ===========================================================================
section("5 · ComplaintContext (context.py)")

try:
    from app.context import ComplaintContext

    # --- 5.1 Valid construction ---
    try:
        ctx = ComplaintContext(tracking_id="T001", severity=3)
        ok = ctx.severity == 3 and ctx.submission_status == "pending"
        record("context", "valid construction succeeds", ok)
    except Exception as e:
        record("context", "valid construction", False, str(e))

    # --- 5.2 severity=0 is valid ---
    try:
        ctx = ComplaintContext(severity=0)
        ok = ctx.severity == 0
        record("context", "severity=0 accepted", ok)
    except Exception as e:
        record("context", "severity=0 accepted", False, str(e))

    # --- 5.3 severity=5 is valid ---
    try:
        ctx = ComplaintContext(severity=5)
        ok = ctx.severity == 5
        record("context", "severity=5 accepted", ok)
    except Exception as e:
        record("context", "severity=5 accepted", False, str(e))

    # --- 5.4 severity=-1 raises ValueError ---
    try:
        raised = False
        try:
            _ = ComplaintContext(severity=-1)
        except ValueError:
            raised = True
        record("context", "severity=-1 raises ValueError", raised)
    except Exception as e:
        record("context", "severity=-1 raises ValueError", False, str(e))

    # --- 5.5 severity=6 raises ValueError ---
    try:
        raised = False
        try:
            _ = ComplaintContext(severity=6)
        except ValueError:
            raised = True
        record("context", "severity=6 raises ValueError", raised)
    except Exception as e:
        record("context", "severity=6 raises ValueError", False, str(e))

    # --- 5.6 Default field values ---
    try:
        ctx = ComplaintContext()
        ok = (
            ctx.submission_status == "pending"
            and ctx.authority_level == "level1"
            and ctx.authority_level_num == 1
            and ctx.error is None
        )
        record("context", "default field values are correct", ok)
    except Exception as e:
        record("context", "default field values", False, str(e))

    # --- 5.7 New ADD fields exist ---
    try:
        ctx = ComplaintContext()
        ok = hasattr(ctx, "complaint_ref_id") and hasattr(ctx, "authority_phone")
        record("context", "new ADD fields (complaint_ref_id, authority_phone) exist", ok)
    except Exception as e:
        record("context", "ADD fields exist", False, str(e))

except ImportError as e:
    print(f"  {WARN} Could not import ComplaintContext: {e}")


# ===========================================================================
# Print final summary
# ===========================================================================
summary()