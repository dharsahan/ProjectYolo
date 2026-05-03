# Dynamic Contextual Widgets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow the agent to render dynamic, interactive UI widgets (like multiple-choice questions) inside the Electron chat interface.

**Architecture:** We will override the `marked.js` code block renderer in `desktop/renderer/app.js` to intercept `widget` language blocks. We will parse the JSON, render HTML for the widget, style it in `styles.css`, and handle clicks via event delegation. We will also update the system prompt so the agent knows how to use it.

**Tech Stack:** JavaScript, HTML, CSS, marked.js, Python (for prompt builder).

---

### Task 1: Frontend Markdown Renderer & Styles

**Files:**
- Modify: `desktop/renderer/app.js`
- Modify: `desktop/renderer/styles.css`

- [ ] **Step 1: Add CSS styles for the widget**

Modify `desktop/renderer/styles.css` to add styles for `.dynamic-widget`, `.widget-title`, `.widget-options`, and `.widget-btn`.

```css
/* --- Dynamic Widgets --- */
.dynamic-widget {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 16px;
  margin: 12px 0;
  font-family: var(--font-body);
}

.dynamic-widget .widget-title {
  font-weight: 600;
  margin-bottom: 12px;
  color: var(--text-primary);
}

.dynamic-widget .widget-options {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.dynamic-widget .widget-btn {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  padding: 10px 16px;
  border-radius: 6px;
  cursor: pointer;
  text-align: left;
  transition: all 0.2s ease;
}

.dynamic-widget .widget-btn:hover {
  background: var(--bg-hover);
  border-color: var(--text-muted);
}

.dynamic-widget.locked {
  opacity: 0.7;
  pointer-events: none;
}

.dynamic-widget.locked .widget-btn[data-selected="true"] {
  background: var(--accent-color);
  color: #fff;
  border-color: var(--accent-color);
}
```

- [ ] **Step 2: Update marked renderer in `app.js`**

Find the `renderMarkdown` function in `desktop/renderer/app.js`. If there isn't a custom renderer already, configure `marked.use()`. If there is, extend it.

```javascript
    // In desktop/renderer/app.js, near where marked is initialized (e.g. top of file or in renderMarkdown)
    const renderer = new marked.Renderer();
    const originalCodeRenderer = renderer.code.bind(renderer);

    renderer.code = function(code, language, isEscaped) {
      if (language === 'widget') {
        try {
          const data = JSON.parse(code);
          if (data.type === 'choice') {
            const optionsHtml = (data.options || []).map(opt => {
              const label = opt.label.replace(/</g, '&lt;').replace(/>/g, '&gt;');
              const val = opt.value.replace(/"/g, '&quot;');
              return `<button class="widget-btn" data-widget-id="${data.id}" data-value="${val}">${label}</button>`;
            }).join('');
            
            const title = (data.text || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            
            return `
              <div class="dynamic-widget" id="widget-${data.id}">
                <div class="widget-title">${title}</div>
                <div class="widget-options">
                  ${optionsHtml}
                </div>
              </div>
            `;
          }
        } catch (e) {
          console.error("Failed to parse widget JSON:", e);
          // Fallback to normal rendering if JSON is invalid
        }
      }
      return originalCodeRenderer(code, language, isEscaped);
    };

    marked.setOptions({ renderer: renderer });
```

- [ ] **Step 3: Commit**

```bash
git add desktop/renderer/app.js desktop/renderer/styles.css
git commit -m "feat(desktop): add markdown renderer and styles for dynamic widgets"
```

---

### Task 2: Frontend Interaction (Event Delegation)

**Files:**
- Modify: `desktop/renderer/app.js`

- [ ] **Step 1: Add click listener to messages container**

In `desktop/renderer/app.js`, locate where event listeners are attached (e.g., near the bottom of the DOM content loaded block) and add event delegation for `.widget-btn`.

```javascript
    // Inside DOMContentLoaded or similar initialization area
    dom.messages.addEventListener('click', (e) => {
      const btn = e.target.closest('.widget-btn');
      if (!btn) return;
      
      const widget = btn.closest('.dynamic-widget');
      if (!widget || widget.classList.contains('locked')) return;

      // Lock the widget
      widget.classList.add('locked');
      btn.setAttribute('data-selected', 'true');

      // Extract value
      const value = btn.getAttribute('data-value');
      const widgetId = btn.getAttribute('data-widget-id');
      
      // Send the response
      sendMessage(`[Widget Response: ${widgetId}] Selected: ${value}`);
    });
```

- [ ] **Step 2: Commit**

```bash
git add desktop/renderer/app.js
git commit -m "feat(desktop): add auto-send and lock interaction for dynamic widgets"
```

---

### Task 3: Agent Prompt Updates

**Files:**
- Modify: `configs/prompts/base.md`
- Modify: `configs/prompts/base_compact.md`

- [ ] **Step 1: Update `base.md` to instruct the agent on widgets**

Append the following instructions to the `# Tooling Doctrine` or `## Terminal Interaction Strategy` section in `configs/prompts/base.md`.

```markdown
## Dynamic Widgets
If you need to ask the user a multiple-choice question (e.g., to select a framework, confirm a destructive choice, or pick an option), you can render a native UI widget in the chat.
Output a fenced code block with the language `widget` containing exactly this JSON structure:
```widget
{
  "type": "choice",
  "id": "unique_id_here",
  "text": "Your question here?",
  "options": [
    {"label": "Display Text 1", "value": "value_1"},
    {"label": "Display Text 2", "value": "value_2"}
  ]
}
```
The user's selection will be returned as a standard chat message.
```

- [ ] **Step 2: Update `base_compact.md`**

Add a concise version to `configs/prompts/base_compact.md`.

```markdown
To ask a multiple choice question, output a JSON block:
```widget
{"type": "choice", "id": "q1", "text": "Question?", "options": [{"label": "Yes", "value": "yes"}, {"label": "No", "value": "no"}]}
```
```

- [ ] **Step 3: Commit**

```bash
git add configs/prompts/base.md configs/prompts/base_compact.md
git commit -m "feat: add dynamic widget instructions to system prompts"
```