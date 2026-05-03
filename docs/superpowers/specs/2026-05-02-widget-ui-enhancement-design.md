# Design Spec: Widget UI Enhancement & Custom Input

**Date:** 2026-05-02
**Topic:** Widget UI Enhancement
**Goal:** Enhance the dynamic widget UI with a modern, rounded aesthetic and add an integrated text field for custom "Other" answers.

## 1. Architecture & Concept
When the Electron frontend receives a markdown block with the language `widget`, the JSON schema can now optionally include an `"allow_custom": true` flag. If this flag is true, the `renderActiveWidget` function will append a custom text input field below the choice buttons. 

## 2. Frontend Rendering (`desktop/renderer/app.js`)
- We will update `renderActiveWidget` to check for `data.allow_custom`.
- If true, append an HTML block containing an `<input type="text">` and a send icon (SVG) wrapped in a styled container.

## 3. UI Styling & Polish (`desktop/renderer/styles.css`)
- **Widget Container**: Update `.textbar-widget` with `background: var(--bg-tertiary)`, `border-radius: 16px`, `padding: 20px`, and a modern `box-shadow: 0 8px 30px rgba(0,0,0,0.6)`.
- **Buttons**: Update `.widget-btn` with `border-radius: 8px`, `background: var(--bg-secondary)`, and a distinct hover transition.
- **Custom Input**: Add classes `.widget-custom-input-container`, `.widget-custom-input`, and `.widget-custom-send-btn` to style the new integrated text field natively within the widget body.

## 4. Frontend Interaction (Event Delegation)
- We will update the event listener on `#active-widget-container` to handle clicks on the `.widget-custom-send-btn`.
- We will also add a `keydown` listener for the "Enter" key on `.widget-custom-input`.
- Submitting the custom text will:
  - Extract the text value.
  - Call `sendMessage("[Widget Response: ID] Custom: " + text)`.
  - Add the `.locked` class to the widget container and display a brief success state before calling `clearActiveWidget()`.

## 5. Agent System Prompt (`prompt_builder.py`)
- We will update the system prompt (e.g. `base.md` and `base_compact.md`) to instruct the agent on how to use the `"allow_custom": true` flag in the JSON schema.
