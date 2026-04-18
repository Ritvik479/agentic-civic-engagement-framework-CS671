import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from dotenv import load_dotenv
from groq import Groq

# CORRECT
from app.tools.trio_c.smart_rag_tool import retrieve_laws
from app.tools.trio_c.authority_lookup_tool import lookup_authority
from app.tools.trio_c.severity_score_tool import calculate_severity

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
client = Groq(api_key=api_key)


def extract_location_parts(location: str):
    """
    Simple helper to split location into district and state
    """
    parts = [p.strip() for p in location.split(",")]

    if len(parts) >= 2:
        return parts[0], parts[1]
    return "Unknown", "Unknown"


def draft_complaint(issue: str, description: str, location: str) -> str:

    # -------------------------------
    # STEP 1 — Extract district/state
    # -------------------------------
    district, state = extract_location_parts(location)

    # -------------------------------
    # STEP 2 — Calculate severity
    # -------------------------------
    severity_result = calculate_severity(issue, description, location)
    severity = severity_result.get("severity", 2)

    # -------------------------------
    # STEP 3 — Retrieve laws
    # -------------------------------
    retrieved = retrieve_laws(f"{issue} {description}", top_k=3)
    laws_text = "\n".join(f"- {item['law']}" for item in retrieved)

    # -------------------------------
    # STEP 4 — Authority lookup
    # -------------------------------
    authority = lookup_authority(issue, state, district, severity)
    authority_name = authority.get("authority_name", "Concerned Authority")

    if authority_name == "Unknown Authority":
        return "Unable to determine correct authority for this issue."

    # -------------------------------
    # STEP 5 — Prompt
    # -------------------------------
    prompt = f"""
Write a concise and factual description of an environmental issue.

Issue: {issue}
Description: {description}
Location: {location}

authority : {authority_name}
Relevant Laws:
{laws_text}

Instructions:
- Write 1-2 clear paragraphs only
- Describe the issue in a factual, objective manner
- Include specific details like location, type of pollution, and visible impact
- DO NOT mention severity.
- Optionally reference one-two relevant law from above
- DO NOT add any irrelevent law
- Do NOT address anyone (no "Dear Sir")
- Mention authority name at the starting
- Do NOT write like a letter or complaint
- Do NOT include placeholders or extra formatting
- Keep it under 120 words
"""

    # -------------------------------
    # STEP 6 — LLM Call
    # -------------------------------
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You draft formal government complaints."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=300
        )

        return response.choices[0].message.content.strip()

    except Exception:
        return "Failed to generate complaint."