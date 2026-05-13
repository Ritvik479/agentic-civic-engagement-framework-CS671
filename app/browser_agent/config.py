import os

# =====================================================
# GOAL
# =====================================================

GOAL = """
Login to PGPortal (https://pgportal.gov.in/Signin) and submit a road pothole complaint.

Reference workflow — follow steps in this EXACT order:

PHASE 1 — LOGIN (url: /Signin)
1. Fill username field  →  value: USERNAME
2. Fill password field  →  value: PASSWORD
3. Fill captcha field   →  pause and ask the user (action: captcha)
4. Click Login button

PHASE 2 — TERMS PAGE (url: /NewGrievance)
5. Check the terms checkbox (checkbox_0) if not already checked
6. Click Submit button (button_0)

PHASE 3 — MINISTRY SELECTION (url: /NewGrievance/Organisation)
*** This page shows ministry names as CLICKABLE LINKS, not a dropdown ***
7. Click the link with text "Housing and Urban Affairs"

PHASE 4 — CATEGORY DROPDOWNS (url changes after step 7)
8.  Click the "Please select main category" combobox, then select option "DDA (Delhi Development Authority)"
9.  Click the next "Select next level category" combobox, then select option "Civic Issues (Development..."
10. Click the next "Select next level category" combobox, then select option "Road Repair/Road related"

PHASE 5 — FORM FIELDS
11. Fill "Address of site *"          →  value: POTHOLE_ADDRESS
12. Fill "Organisation Name *"        →  value: ORG_NAME
13. Fill "Text of grievance (Remarks) *" →  value: GRIEVANCE_TEXT

PHASE 6 — SUBMIT
14. Click "Next" or "Submit" button to lodge the complaint
"""

# =====================================================
# CREDENTIALS
# =====================================================

USERNAME = "highdreameater"
PASSWORD = "Vitthal@2876"

# =====================================================
# LLM
# =====================================================

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")

# =====================================================
# COMPLAINT DETAILS  (edit before running)
# =====================================================

POTHOLE_ADDRESS   = "Near Main Market, Sector 12, Dwarka, New Delhi"
ORG_NAME          = "Public Works Department"
GRIEVANCE_TEXT    = (
    "There is a large pothole at the above mentioned address that has been "
    "causing accidents and damage to vehicles. Immediate repair is requested."
)