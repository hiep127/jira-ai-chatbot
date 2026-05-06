# Feature Plan: UI Refactoring v3 - Validation & Quick Actions

**Source Context:** Flet Frontend UI (`frontend/main.py`, `frontend/views/jira_settings.py`)
**Architecture Laws:** Actionable Observability, DRY (Don't Repeat Yourself)
**Objective:** Reorder settings hierarchy, enforce mandatory credential fields via error dialogs, and add a quick-action "Daily Summary" button to the main chat interface.

Operating strictly in **Plan Mode**, outline the file modifications to achieve the following 3 requirements. Do not write the code until I approve the plan.

## 1. Reorder Settings Menu (Credentials First)
**Issue:** The JQL Import was moved to the top, but Profile Name and Access Token are the actual prerequisites for the app to function.
**Implementation in `frontend/views/jira_settings.py`:**
* Update `_build_dialog_content()` so the order is strictly:
    1.  **Filter Profile Name** (Update label to indicate it is REQUIRED, e.g., `"Profile Name * "`)
    2.  **Jira Personal Access Token (PAT)** (Update label to `"Jira PAT * "`)
    3.  **Jira Parent Link** (Update label to `"Jira Parent Link * "`)
    4.  **Import Filter from JQL** (The `ft.Card` created in v2)
    5.  **Current Saved Filters / Filter Builder Rows**

## 2. Enforce Mandatory Fields with Error Dialogs
**Issue:** Clicking "Save & Close" with empty required fields does nothing, leaving the user confused.
**Implementation in `frontend/views/jira_settings.py`:**
* Locate the `on_save(e)` function.
* Before attempting to parse the Jira Environment or save to state, add strict validation checks for the three required fields: `profile_name_field.value`, `pat_field.value`, and `parent_link_field.value`.
* If *any* of these are empty (or just whitespace), completely halt the save process and call the existing `show_error_dialog` function.
* **Actionable Message:** Use the exact string: `"Validation Error: Missing Required Fields.\n\nRemediation: You must provide a Profile Name, Jira PAT, and Parent Link before saving."`

## 3. "Generate Daily Summary" Quick-Action Button
**Issue:** Users have to manually type out a prompt to get a summary of their active filters.
**Implementation in `frontend/main.py`:**
* **Step A (Refactor for DRY):** The current `on_send(e)` function handles reading the input, updating the UI with chat bubbles, and making the HTTP call. Extract the core logic (everything *after* reading `input_field.value`) into a standalone async function: `async def process_chat_message(prompt_text: str)`.
* **Step B (Update `on_send`):** Update `on_send(e)` to simply check if `input_field.value` is not empty, clear the field, and call `await process_chat_message(user_text)`.
* **Step C (The UI Button):** Create a new `ft.ElevatedButton("Generate Daily Summary", icon=ft.icons.AUTO_AWESOME)`. Place it in the main UI, ideally in the header row next to the settings icon, or immediately above the chat input field.
* **Step D (The Trigger):** Add an `on_click` event to this new button that programmatically calls `await process_chat_message("Please generate a detailed daily summary based on my currently active Jira filters.")`.

---
**Claude:** Please acknowledge these constraints and output the step-by-step implementation plan and exact files you intend to modify. Do not skip Step 3A (the refactor); do not duplicate the HTTP POST logic inside the new summary button callback.