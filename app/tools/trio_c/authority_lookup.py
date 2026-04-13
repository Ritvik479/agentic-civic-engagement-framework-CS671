import json

# Load authority dataset
with open("configs/authority_data.json") as f:
    authority_data = json.load(f)["data"]

# Build index at load time for O(1) lookups
authority_index = {
    (
        entry["state"].lower(),
        entry["district"].lower(),
        entry["issue"].lower()
    ): entry
    for entry in authority_data
}

def get_authorities(state: str, district: str, issue: str) -> dict:
    """
    Retrieve authority levels for a given state, district, and issue.

    Args:
        state: State name (case-insensitive)
        district: District name (case-insensitive)
        issue: Issue type (case-insensitive)

    Returns:
        Dict with level1–level4 authority info, or an error dict if not found.
    """
    key = (state.strip().lower(), district.strip().lower(), issue.strip().lower())
    entry = authority_index.get(key)

    if entry:
        return {
            "level1": entry["level1"],
            "level2": entry["level2"],
            "level3": entry["level3"],
            "level4": entry["level4"],
        }

    return {"error": f"No authority found for state='{state}', district='{district}', issue='{issue}'"}