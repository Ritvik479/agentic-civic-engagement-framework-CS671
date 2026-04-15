import json
import os

# Pointing to the file you uploaded
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "../../../configs/authority_data.json")

def load_authority_data():
    """Helper function to load the JSON data."""
    try:
        with open(CONFIG_PATH, 'r') as file:
            return json.load(file).get("data", [])
    except FileNotFoundError:
        return []

def get_escalation_mapping(state: str, district: str, issue: str, severity_score: int, days_unresolved: int = 0) -> dict:
    """
    Calculates the correct escalation level based on issue severity and age, 
    then returns the target authority and any necessary CCs.
    """
    mapping_data = load_authority_data()
    
    # 1. Find the specific record for this location and issue
    matched_record = next(
        (item for item in mapping_data 
         if item["state"].lower() == state.lower() 
         and item["district"].lower() == district.lower() 
         and item["issue"].lower() == issue.lower()), 
        None
    )

    if not matched_record:
        return {"error": f"No authority mapping found for {issue} in {district}, {state}."}

    # 2. Determine Base Level from Severity Score (1-10)
    # Low (1-3) starts at Level 1
    # Medium (4-6) starts at Level 1
    # High (7-8) starts at Level 2 directly
    # Critical (9-10) starts at Level 3 directly
    if severity_score >= 9:
        base_level = 3
    elif severity_score >= 7:
        base_level = 2
    else:
        base_level = 1

    # 3. Apply Time-Based Escalation (Aging)
    # Example logic: Bump up 1 level for every 7 days the issue is unresolved
    time_bump = days_unresolved // 7 
    final_level = min(base_level + time_bump, 4) # Cap at level 4 (CPGRAMS)

    # 4. Construct the Routing Output
    target_authority = matched_record.get(f"level{final_level}", {})
    
    # Determine who to CC (the next level up, if applicable)
    cc_authority = {}
    if final_level < 4 and severity_score >= 4: 
        # If it's at least medium severity and not at the top level, CC the boss
        cc_authority = matched_record.get(f"level{final_level + 1}", {})

    return {
        "current_escalation_level": final_level,
        "primary_contact": target_authority,
        "cc_contact": cc_authority,
        "reasoning": f"Severity Score is {severity_score}/10. Issue unresolved for {days_unresolved} days."
    }

# --- Example Usage for Testing ---
if __name__ == "__main__":
    # Test 1: A brand new, low-severity pothole (Should go to Level 1)
    print("TEST 1: New Low Severity")
    print(get_escalation_mapping("Punjab", "Amritsar", "Road Potholes", severity_score=2, days_unresolved=0))
    print("-" * 40)

    # Test 2: A highly severe waterlogging issue (Should skip straight to Level 2 or 3)
    print("TEST 2: New High Severity")
    print(get_escalation_mapping("Punjab", "Amritsar", "Waterlogging / Flooding", severity_score=8, days_unresolved=0))
    print("-" * 40)

    # Test 3: A medium severity issue ignored for 15 days (Base Level 1 + 2 time bumps = Level 3)
    print("TEST 3: Ignored Medium Severity")
    print(get_escalation_mapping("Punjab", "Amritsar", "Solid Waste", severity_score=5, days_unresolved=15))