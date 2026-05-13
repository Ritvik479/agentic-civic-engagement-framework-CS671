def decide_next_action(elements, memory):

    # -------------------------------------------------
    # USERNAME
    # -------------------------------------------------

    if not memory.get("username_filled"):

        for e in elements:

            if e["type"] == "textbox":

                placeholder = str(
                    e.get("placeholder", "")
                ).lower()

                if (
                    "username" in placeholder
                    or "email" in placeholder
                    or "mobile" in placeholder
                ):

                    return {
                        "action": "fill",
                        "target": e["id"],
                        "value": "highdreameater"
                    }

    # -------------------------------------------------
    # PASSWORD
    # -------------------------------------------------

    if not memory.get("password_filled"):

        for e in elements:

            if e["type"] == "textbox":

                placeholder = str(
                    e.get("placeholder", "")
                ).lower()

                if "password" in placeholder:

                    return {
                        "action": "fill",
                        "target": e["id"],
                        "value": "Vitthal@2876"
                    }

    # -------------------------------------------------
    # CAPTCHA
    # -------------------------------------------------

    if not memory.get("captcha_filled"):

        for e in elements:

            if e["type"] == "textbox":

                placeholder = str(
                    e.get("placeholder", "")
                ).lower()

                if "security" in placeholder:

                    return {
                        "action": "captcha",
                        "target": e["id"]
                    }

    # -------------------------------------------------
    # LOGIN BUTTON
    # -------------------------------------------------

    if (
        memory.get("username_filled")
        and memory.get("password_filled")
        and memory.get("captcha_filled")
    ):

        # ---------------------------------------------
        # STOP RETRY SPAM
        # ---------------------------------------------

        if memory.get("login_failed"):

            print("\nPrevious login failed.\n")

            return None

        for e in elements:

            if e["type"] == "button":

                text = str(
                    e.get("text", "")
                ).lower()

                if "login" in text:

                    return {
                        "action": "click",
                        "target": 2
                    }

    return None