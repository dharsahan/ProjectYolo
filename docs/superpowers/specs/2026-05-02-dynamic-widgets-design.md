# Design Spec: Dynamic Contextual Widgets for Electron App

**Date:** 2026-05-02
**Topic:** Dynamic Widgets in Chat
**Goal:** Allow the agent to render dynamic, interactive UI widgets (like multiple-choice questions) inside the Electron chat interface.

## 1. Architecture & Format
The agent will communicate the need for a widget using standard Markdown fenced code blocks with a custom language identifier `widget`.
The content of the code block will be a strict JSON object defining the widget.

**Example Agent Output:**
```widget
{
  "type": "choice",
  "id": "framework_choice_1",
  "text": "Which frontend framework would you prefer for this project?",
  "options": [
    {"label": "React", "value": "React"},
    {"label": "Vue", "value": "Vue"},
    {"label": "Vanilla JS", "value": "Vanilla JS"}
  ]
}
```

## 2. Frontend Parsing (`desktop/renderer/app.js`)
The Electron app uses `marked.js` to render Markdown.
- We will add a custom renderer for `code` blocks in `app.js`.
- If the language is `widget`, we will parse the text as JSON.
- If parsing is successful and the type is supported (e.g., `choice`), we return custom HTML markup (e.g., `<div class="dynamic-widget" data-widget-id="...">...</div>`) instead of a `<pre><code>` block.

## 3. Frontend Interaction & State (`desktop/renderer/app.js` & `styles.css`)
- **Event Delegation:** We will add a click event listener to the `#messages` container to handle clicks on widget buttons (`.widget-btn`).
- **Auto-Send:** When a button is clicked, we retrieve its `data-value`. We will automatically call the existing `sendMessage(value)` function to send the response back to the agent.
- **Locking:** Once a selection is made, we add a `.locked` class to the widget container, disabling all its buttons so the user cannot click multiple options for the same question.
- **Styling:** New CSS rules will be added to `desktop/renderer/styles.css` to make the widgets look native to the chat interface.

## 4. Agent System Prompt (`prompt_builder.py`)
- We will update the system prompt (e.g., the base system prompt or legacy template) to instruct the agent on how to use this feature.
- Example instruction: "To ask the user a multiple-choice question, output a fenced code block with the language `widget` containing a JSON object with `type='choice'`, `text`, and `options`."

## 5. Security & Error Handling
- Invalid JSON in a `widget` block will gracefully fall back to rendering as a standard code block, or display a subtle error message.
- HTML escaping will be enforced on widget text and button labels to prevent XSS.