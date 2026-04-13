from dotenv import load_dotenv
import os
from groq import Groq

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise ValueError("GROQ_API_KEY not found in environment variables")

client = Groq(api_key=api_key)

VALID_SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

def calculate_severity(issue: str, description: str, location: str) -> dict:
    """
    Calculates severity of a civic complaint issue.
    
    Returns:
        {
            "severity": "HIGH",
            "success": True
        }
    """

    prompt = f"""
You are an environmental violation analyst.

Issue: {issue}
Description: {description}
Location: {location}

Classify the severity into exactly one of these:
LOW, MEDIUM, HIGH, CRITICAL

Rules:
- LOW    → Minor issue, no immediate danger
- MEDIUM → Affects quality of life, needs attention
- HIGH   → Serious violation, health risk
- CRITICAL → Immediate danger, urgent action needed

Return ONLY the single severity word. Nothing else.
"""

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": "You are a severity classifier. Reply with ONE word only: LOW, MEDIUM, HIGH, or CRITICAL."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.1  # low temperature = more consistent output
        )

        raw_output = response.choices[0].message.content.strip().upper()

        # Extract valid severity even if LLM adds extra text
        severity = None
        for valid in VALID_SEVERITIES:
            if valid in raw_output:
                severity = valid
                break

        # Fallback if nothing matched
        if not severity:
            severity = "MEDIUM"

        return {
            "severity": severity,
            "success": True
        }

    except Exception as e:
        print(f"Severity scoring failed: {e}")
        return {
            "severity": "MEDIUM",  # safe default
            "success": False
        }