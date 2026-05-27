# UI/UX Design System

## 1. Core Philosophy
* **Mode:** Always use Dark Theme (Material 3).
* **Density:** High-density, data-centric layout for professional usage.
* **Navigation:** Sidebar-based navigation for primary views; modals/dialogs for settings.

## 2. Color Palette & Theme
* **Seed Color:** Use `ft.colors.BLUE_GREY` as the base for a professional, neutral aesthetic.
* **Semantic Colors:**
    * Success: `ft.colors.GREEN_400`
    * Error: `ft.colors.RED_400`
    * Warning: `ft.colors.AMBER_400`
* **Backgrounds:** Primary: `ft.colors.BLACK`, Surface: `ft.colors.BLUE_GREY_900`.

## 3. Typography & Spacing
* **Font:** Use `Inter` or system default (`Segoe UI` for Windows).
* **Spacing:** * `spacing=10` for standard column/row gaps.
    * `padding=20` for main view containers.
* **Table UI:**
    * Borders: `ft.border.all(1, ft.colors.BLUE_GREY_800)`
    * Zebra-striping: `data_row_color={ft.ControlState.SELECTED: ft.Colors.BLUE_GREY_800}`

## 4. Component Rules
* **Tables:** Always wrap text in `ft.Container` to force column sizing. Summary column width: `400px`.
* **Buttons:** Use `ft.ElevatedButton` for primary actions; `ft.OutlinedButton` for secondary.
* **Dialogs:** Must be responsive, centered, with `width=600`, `height=auto`.
* **Selection:** Ensure `show_checkbox_column=True` is applied to all data-heavy tables.