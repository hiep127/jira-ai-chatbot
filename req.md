# UI Refactoring v2 & Error Boundary Implementation

**Source Context:** Flet Frontend UI (`frontend/main.py`, `frontend/views/jira_settings.py`)
**Architecture Laws:** Deterministic System Design, Strict State Management, Actionable Observability
**Objective:** Prioritize JQL imports, implement a side navigation drawer for active filter selection, fix `NoneType` state errors, and implement global exception catching.

Operating strictly in **Plan Mode**, outline the file modifications to achieve the following 4 requirements. Do not write the code until I approve the plan.

## 1. Prioritize "Import Filter from JQL"
**Issue:** The UI currently buries the JQL import feature. It should be the primary way users create filters.
**Implementation:**
* In `frontend/views/jira_settings.py`, move the "Import from JQL" input field and button to the **very top** of the settings menu.
* Make it visually distinct (e.g., using a Card or distinct divider) so it is the first thing the user interacts with before falling back to manual row building.

## 2. Side Menu for Active Filter Profiles
**Issue:** Users need a dedicated space to see saved filter profiles and select which ones to use for summaries.
**Implementation:**
* Add an `ft.NavigationDrawer` (or a persistent left-side `ft.Column`) to `frontend/main.py`.
* **Content:** It must display a list of currently loaded "Filter Profiles" (using their names/keys).
* **Selection:** Place an `ft.Checkbox` next to each profile name. 
* **Payload Integration:** Update the `on_send` function. When the user sends a message, iterate through this side menu, check which checkboxes are `True`, and include **only** those specific filter configurations in the LangGraph/FastAPI payload.

## 3. Fix `AttributeError: 'NoneType'` in `on_send`
**Issue:** Line 67 in `on_send` is crashing with `AttributeError: 'NoneType' object has no attribute 'get'`. The app is trying to read `jira_settings.get("target_server")` before the settings state has been properly initialized.
**Implementation:**
* Locate where the global or page-level UI state is defined in `frontend/main.py`.
* Ensure that the dictionary holding the settings (e.g., `page.session.set("jira_settings", {})` or the class attribute) is explicitly initialized with default keys upon app startup, so it is never `None`.

## 4. Global Exception Handling & Error Dialogs
**Issue:** When an error occurs (like a failed API call, parsing error, or state bug), the app crashes in the terminal or fails silently in the UI. 
**Implementation:**
* **Reusable Error UI:** Create a generic function `show_error_dialog(page: ft.Page, error_message: str)` that opens an `ft.AlertDialog` with a red title ("Application Error") and the exception text.
* **Scan and Wrap:** Audit all major event handlers in Flet (specifically `on_send`, `on_click` for adding/importing filters). Wrap their internal logic in `try...except Exception as e:` blocks.
* **Actionable Observability:** In the `except` block, log the error to the terminal and immediately call `show_error_dialog` so the user knows exactly why the action failed.

---
**Claude:** Please acknowledge these constraints and output the step-by-step implementation plan and exact files you intend to modify.