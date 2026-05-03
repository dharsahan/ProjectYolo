# Design Spec: Textbar-Anchored Dynamic Widgets

**Date:** 2026-05-02
**Topic:** Textbar-Anchored Widgets
**Goal:** Enhance the dynamic widget feature by having the widget replace the chat input textbar rather than rendering inline within the chat history.

## 1. Architecture & Concept
When the Electron frontend receives a markdown block with the language `widget`, it will extract the JSON payload. Instead of replacing the markdown with HTML in the chat message stream, the frontend will intercept it, hide the chat input bar, and render the widget in its place at the bottom of the screen.

## 2. Frontend Parsing (`desktop/renderer/app.js`)
Currently, `marked.js` intercepts the `widget` language and renders HTML strings that are appended to the chat.
- We will update the `marked.js` custom renderer for `widget`:
  - When it parses the JSON, it will store the widget data in a global state variable (e.g., `window.activeWidgetData`).
  - It will return an empty string or a placeholder message (e.g., `[Awaiting input...]`) for the chat history, so the raw JSON doesn't show up.
- Alternatively, we intercept the `widget` block *before* it reaches `marked.js` or during the streaming process (in `handle_chat_stream`), but since the agent might mix text and widgets, the `marked.js` hook is still the safest place to extract the payload without breaking other text.

## 3. UI State Management (`desktop/renderer/app.js` & `index.html`)
- We will add a new container in `index.html` inside `#input-area`, next to `.input-wrapper`:
  ```html
  <div id="active-widget-container" class="hidden"></div>
  ```
- We will create a `renderActiveWidget(widgetData)` function in `app.js` that:
  - Hides the `.input-wrapper` (the normal text bar).
  - Unhides `#active-widget-container`.
  - Injects the generated HTML for the widget (title, buttons, and a "Cancel" button).
- We will create a `clearActiveWidget()` function that:
  - Hides `#active-widget-container` and empties it.
  - Unhides `.input-wrapper`.
  - Re-focuses the text input.

## 4. Frontend Interaction (Event Delegation)
- We will attach a click listener to `#active-widget-container` to handle clicks on `.widget-btn` and `.widget-cancel-btn`.
- Clicking an option (`.widget-btn`) will:
  - Extract the `data-value`.
  - Call `sendMessage("[Widget Response: ID] Selected: value")`.
  - Call `clearActiveWidget()`.
- Clicking the cancel button (`.widget-cancel-btn`) will:
  - Call `clearActiveWidget()`.

## 5. CSS Styling (`desktop/renderer/styles.css`)
- We will add styles for `#active-widget-container` so it mimics the textbar area (dark background, padding, border-radius).
- We will update the `.widget-btn` styles to fit this new contextual placement.
- We will add a subtle "Cancel" link/button style below the options.