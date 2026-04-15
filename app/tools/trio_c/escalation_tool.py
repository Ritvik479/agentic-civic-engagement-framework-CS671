import os

# Import the lookup function teammate built. 
# (Note: If they named the function something else, just update the import name below)
from authority_lookup import get_authorities

def get_escalation_mapping(state: str, district: str, issue: str, severity_score: int, days_unresolved: int = 0) -> dict:
    """
    Calculates the correct escalation level based on issue severity and age.
    It then queries authority_lookup to fetch the target authority and CCs.
    """
    
    # 1. Determine Base Level from the Severity Score (1-10) provided by severity_agent.py
    # Critical (9-10) starts at Level 3 directly
    # High (7-8) starts at Level 2 directly
    # Low/Medium (1-6) starts at Level 1
    if severity_score >= 9:
        base_level = 3
    elif severity_score >= 7:
        base_level = 2
    else:
        base_level = 1

    # 2. Apply Time-Based Escalation (Aging)
    # Bumps the complaint up 1 level for every 7 days it goes unresolved.
    time_bump = days_unresolved // 7 
    final_level = min(base_level + time_bump, 4) # Cap at level 4 (CPGRAMS)

    # 3. Fetch the Primary Contact using your teammate's lookup script
    primary_contact = get_authorities(state, district, issue, escalation_level=final_level)
    
    # 4. Determine who to CC (the next level up, if applicable)
    cc_contact = {}
    
    # If it's a medium/high severity issue and hasn't reached the top level yet, CC the boss
    if final_level < 4 and severity_score >= 4: 
        cc_contact = get_routing_authority(state, district, issue, escalation_level=final_level + 1)

    # Handle edge cases where the lookup might fail
    if "error" in primary_contact:
        return {"error": primary_contact["error"]}

    return {
        "current_escalation_level": final_level,
        "primary_contact": primary_contact,
        "cc_contact": cc_contact,
        "reasoning": f"Initial severity was {severity_score}/10. Issue has been unresolved for {days_unresolved} days."
    }

# --- Example Usage for Testing ---
if __name__ == "__main__":
    # You can test this by running it locally, assuming authority_lookup.py is in the same folder.
    
    # Test 1: A medium severity issue ignored for 15 days
    # Base level for 5 is Level 1. 15 days unresolved gives a +2 bump. Final level = 3.
    result = get_escalation_mapping(
        state="Punjab", 
        district="Amritsar", 
        issue="Solid Waste", 
        severity_score=5, 
        days_unresolved=15
    )
    
    print("Escalation Result:")
    print(result)