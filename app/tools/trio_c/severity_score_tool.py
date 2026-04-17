from dotenv import load_dotenv
import os
from groq import Groq

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise ValueError("GROQ_API_KEY not found in environment variables")

client = Groq(api_key=api_key)


def calculate_severity(issue: str, description: str, location: str) -> dict:
    """
    Calculates severity of a civic complaint issue.

    Severity Scale:
        1 = Minor issue, no immediate danger
        2 = Moderate issue, affects quality of life
        3 = Serious violation, health/environment risk
        4 = Critical danger, urgent action needed
        5 = Reserved for system escalation override only

    Returns:
        {
            "severity": int,
            "success": bool
        }
    """

    prompt = f"""
You are an environmental violation analyst.

Issue: {issue}
Description: {description}
Location: {location}

Classify severity into exactly one integer:

1 = Minor issue, no immediate danger
2 = Moderate issue, affects quality of life
3 = Serious violation, health/environment risk
4 = Critical danger, urgent action needed

Return ONLY one digit: 1, 2, 3, or 4.
Nothing else.
"""

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a severity classifier. "
                        "Reply with ONLY one digit: 1, 2, 3, or 4."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.1
        )

        raw_output = response.choices[0].message.content.strip()

        # Extract first valid digit
        severity = None
        for ch in raw_output:
            if ch in {"1", "2", "3", "4"}:
                severity = int(ch)
                break

        # Safe fallback
        if severity is None:
            severity = 2

        return {
            "severity": severity,
            "success": True
        }

    except Exception as e:
        print(f"Severity scoring failed: {e}")

        return {
            "severity": 2,   # moderate fallback
            "success": False
        }