import json

# Load authority dataset
with open("configs/authority_data.json") as f:
    authority_data = json.load(f)["data"]

# Build lookup index
authority_index = {
    (
        entry["state"].strip().lower(),
        entry["district"].strip().lower(),
        entry["issue"].strip().lower()
    ): entry
    for entry in authority_data
}

def lookup_authority(issue: str, state: str, district: str, severity: int) -> dict:
    """
    Selects authority based on issue, location, and severity.

    Severity Routing:
        1 -> level1
        2 -> level2
        3 -> level3
        4 -> level4
        5 -> level4 (central override)

    Returns:
        {
            "authority_name": str,
            "authority_email": str,
            "authority_portal": str
        }
    """

    key = (
        state.strip().lower(),
        district.strip().lower(),
        issue.strip().lower()
    )

    key = (
        state.strip().lower(),
        district.strip().lower(),
        issue.strip().lower()
    )

    entry = authority_index.get(key)

    # Fallback: Find ANY issue for this district if the specific issue fails
    if not entry:
        print(f"[Lookup] No district match for '{district}'. Trying state-level fallback...")
        search_state = state.strip().lower()

        for (s, d, i), val in authority_index.items():
            # If we can't find the district, find the first entry for this STATE
            # This ensures we at least get a Punjab-level authority
            if s == search_state:
                print(f"[Lookup] State fallback found: Mapping to {d} (first available in {state})")
                entry = val
                break

    # Final fallback if even the fuzzy match fails
    if not entry:
        return {
            "authority_name":     "Unknown Authority",
            "authority_email":    "",
            "authority_portal":   "",
            "authority_phone":    "",
            "current_level":      "level1",
            "current_level_num": 1
        }

    # Severity → authority level mapping
    level_num_map = {1: 1, 2: 2, 3: 3, 4: 4, 5: 4}
    level_num = level_num_map.get(severity, 4)

    if severity == 1:
        selected_level = "level1"
    elif severity == 2:
        selected_level = "level2"
    elif severity == 3:
        selected_level = "level3"
    else:
        selected_level = "level4"   # covers 4 AND 5

    authority = entry[selected_level]

    return {
        "authority_name":     authority.get("authority", ""),
        "authority_email":    authority.get("email", ""),
        "authority_portal":   authority.get("portal", ""),
        "authority_phone":    authority.get("phone", ""),   # ADD
        "current_level":      selected_level,
        "current_level_num":  level_num
    }