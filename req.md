I need to fix the Jira Filter UI. Follow this plan strictly:

1. **Dynamic Environment Refactor**: 
   - Remove hardcoded "SPAWS" and "LGE" references in `frontend/main.py`.
   - Implement a "Named Filter" system: Add a `ft.TextField` for "Filter Profile Name".
   - Add a `ft.TextField` for "Jira Parent Link" that is sent to the backend as part of the state.

2. **Wiring "Add Filter"**:
   - Ensure the `on_click` event for the "Add Filter" button calls a function that dynamically adds a new `ft.Row` to the `filter_rows_column`.
   - Each row should include a dropdown for common Jira fields (Project, Assignee, Status, Priority) and a TextField for the value.

3. **Fix State Bug (AssertionError)**:
   - Identify why the 3rd screenshot shows a crash when updating controls.
   - Implement a check to ensure `control.page` is not None before calling `control.update()`.
   - Ensure that when a user changes a "Field" dropdown to "Status", the "Value" textfield correctly swaps to a dropdown without losing the reference in the page tree.

4. **Data Sync**:
   - Ensure all dynamic filters are gathered into a dictionary and sent to the FastAPI `/chat` endpoint within the `ChatRequest` model.

Review the current `frontend/main.py` first, then propose the code changes.