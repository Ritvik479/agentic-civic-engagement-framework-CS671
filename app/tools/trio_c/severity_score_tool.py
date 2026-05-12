from dotenv import load_dotenv
import os
from openai import OpenAI

load_dotenv()

nvidia_client = OpenAI(
    base_url=os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
    api_key=os.getenv("NVIDIA_API_KEY")
)


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
        response = nvidia_client.chat.completions.create(
            model=os.getenv("NVIDIA_MODEL", "nvidia/llama-3.1-nemotron-70b-instruct"),
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
            temperature=0.1,
            max_tokens=1024
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