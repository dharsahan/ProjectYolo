# Widget UI Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance the dynamic widget UI with a modern, rounded aesthetic and add an integrated text field for custom "Other" answers.

**Architecture:** Modify `styles.css` to update existing widget classes with the new aesthetic. Update `app.js` to conditionally render a text input and SVG send button when `allow_custom` is true in the JSON schema. Attach event listeners for `keydown` (Enter) and `click` on the new custom input container to submit the text.

**Tech Stack:** JavaScript, CSS, HTML.

---

### Task 1: UI Styling & Polish

**Files:**
- Modify: `desktop/renderer/styles.css`

- [ ] **Step 1: Update existing widget styles**

In `desktop/renderer/styles.css`, replace the `.textbar-widget` and `.dynamic-widget .widget-btn` classes with updated rounded styles and a drop shadow.

```css
/* Update these inside styles.css */
.textbar-widget {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 16px;
  padding: 20px;
  margin: 0;
  font-family: var(--font-body);
  box-shadow: 0 8px 30px rgba(0,0,0,0.6);
}

.dynamic-widget .widget-btn {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  padding: 12px 16px;
  border-radius: 8px;
  cursor: pointer;
  text-align: left;
  transition: all 0.2s ease;
}
```

- [ ] **Step 2: Add custom input styles**

In `desktop/renderer/styles.css`, append new styles for the custom input elements.

```css
/* Add to styles.css */
.widget-custom-input-container {
  display: flex;
  align-items: center;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 8px 12px;
  margin-top: 8px;
  transition: border-color 0.2s ease;
}

.widget-custom-input-container:focus-within {
  border-color: var(--accent-color);
}

.widget-custom-input {
  background: transparent;
  border: none;
  color: var(--text-primary);
  width: 100%;
  outline: none;
  font-size: 13px;
  font-family: var(--font-body);
}

.widget-custom-send-btn {
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color 0.2s ease;
}

.widget-custom-send-btn:hover {
  color: var(--accent-color);
}

.widget-custom-send-btn svg {
  width: 16px;
  height: 16px;
}
```

- [ ] **Step 3: Commit**

```bash
git add desktop/renderer/styles.css
git commit -m "feat(desktop): update widget UI to modern rounded aesthetic with custom input styles"
```

---

### Task 2: Frontend Rendering Update

**Files:**
- Modify: `desktop/renderer/app.js`

- [ ] **Step 1: Update renderActiveWidget in app.js**

In `desktop/renderer/app.js`, locate `function renderActiveWidget(data)`. Update the HTML generation to conditionally include the custom input container if `data.allow_custom` is true.

```javascript
    // Inside renderActiveWidget, replace the innerHTML generation logic:
    if (data.type === 'choice') {
      const optionsHtml = (data.options || []).map(opt => {
        const label = opt.label.replace(/</g, '&lt;').replace(/>/g, '&gt;');
        const val = opt.value.replace(/"/g, '&quot;');
        return `<button class="widget-btn" data-widget-id="${data.id}" data-value="${val}">${label}</button>`;
      }).join('');
      
      const title = (data.text || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      
      let customInputHtml = '';
      if (data.allow_custom) {
        customInputHtml = `
          <div class="widget-custom-input-container">
            <input type="text" class="widget-custom-input" placeholder="Or type your own answer..." data-widget-id="${data.id}">
            <button class="widget-custom-send-btn">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
              </svg>
            </button>
          </div>
        `;
      }
      
      dom.activeWidgetContainer.innerHTML = `
        <div class="dynamic-widget textbar-widget" id="widget-${data.id}">
          <div class="widget-title">${title}</div>
          <div class="widget-options">
            ${optionsHtml}
          </div>
          ${customInputHtml}
          <div class="widget-cancel" onclick="window.clearActiveWidget()">Cancel</div>
        </div>
      `;
      
      dom.inputWrapper.classList.add('hidden');
      dom.activeWidgetContainer.classList.remove('hidden');
      
      if (data.allow_custom) {
        const inputEl = dom.activeWidgetContainer.querySelector('.widget-custom-input');
        if (inputEl) inputEl.focus();
      }
    }
```

- [ ] **Step 2: Commit**

```bash
git add desktop/renderer/app.js
git commit -m "feat(desktop): render custom input field in widgets when allow_custom is true"
```

---

### Task 3: Event Delegation for Custom Input

**Files:**
- Modify: `desktop/renderer/app.js`

- [ ] **Step 1: Add handlers for custom input submission**

In `desktop/renderer/app.js`, locate the `dom.activeWidgetContainer.addEventListener('click', ...)` block. Add logic to handle the send button click. Then, add a `keydown` listener for the Enter key.

```javascript
    // Update the click listener:
    dom.activeWidgetContainer.addEventListener('click', (e) => {
      const btn = e.target.closest('.widget-btn');
      const sendBtn = e.target.closest('.widget-custom-send-btn');
      
      const widget = e.target.closest('.dynamic-widget');
      if (!widget || widget.classList.contains('locked')) return;

      if (btn) {
        // Lock the widget visually
        widget.classList.add('locked');
        btn.setAttribute('data-selected', 'true');

        // Extract value
        const value = btn.getAttribute('data-value');
        const widgetId = btn.getAttribute('data-widget-id');
        
        // Send the response
        sendMessage(`[Widget Response: ${widgetId}] Selected: ${value}`);
        
        setTimeout(() => clearActiveWidget(), 300);
      } else if (sendBtn) {
        const inputEl = widget.querySelector('.widget-custom-input');
        const value = inputEl ? inputEl.value.trim() : '';
        if (!value) return;

        widget.classList.add('locked');
        const widgetId = inputEl.getAttribute('data-widget-id');
        
        sendMessage(`[Widget Response: ${widgetId}] Custom: ${value}`);
        
        setTimeout(() => clearActiveWidget(), 300);
      }
    });

    // Add keydown listener for Enter key:
    dom.activeWidgetContainer.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        const inputEl = e.target.closest('.widget-custom-input');
        if (!inputEl) return;
        
        e.preventDefault();
        const value = inputEl.value.trim();
        if (!value) return;

        const widget = inputEl.closest('.dynamic-widget');
        if (!widget || widget.classList.contains('locked')) return;

        widget.classList.add('locked');
        const widgetId = inputEl.getAttribute('data-widget-id');
        
        sendMessage(`[Widget Response: ${widgetId}] Custom: ${value}`);
        
        setTimeout(() => clearActiveWidget(), 300);
      }
    });
```

- [ ] **Step 2: Commit**

```bash
git add desktop/renderer/app.js
git commit -m "feat(desktop): handle custom input submission in widgets"
```

---

### Task 4: Agent Prompt Updates

**Files:**
- Modify: `configs/prompts/base.md`
- Modify: `configs/prompts/base_compact.md`
- Modify: `~/.yolo/prompts/base.md` (via a quick python script to ensure override works)

- [ ] **Step 1: Update prompt files**

Update the instructions for Dynamic Widgets in `configs/prompts/base.md` to mention the `"allow_custom": true` flag.

```markdown
## Dynamic Widgets
If you need to ask the user a multiple-choice question (e.g., to select a framework, confirm a destructive choice, or pick an option), you can render a native UI widget in the chat.
Output a fenced code block with the language `widget` containing exactly this JSON structure:
```widget
{
  "type": "choice",
  "id": "unique_id_here",
  "text": "Your question here?",
  "allow_custom": true,
  "options": [
    {"label": "Display Text 1", "value": "value_1"},
    {"label": "Display Text 2", "value": "value_2"}
  ]
}
```
Set `"allow_custom": true` if the user should be able to type their own custom answer.
The user's selection will be returned as a standard chat message.
```

- [ ] **Step 2: Run a python script to patch the user's override file**

```python
# scripts/patch_prompt.py
import os
base_path = os.path.expanduser("~/.yolo/prompts/base.md")
if os.path.exists(base_path):
    with open(base_path, "r") as f:
        content = f.read()
    
    if '"allow_custom": true' not in content:
        content = content.replace(
            '"text": "Your question here?",',
            '"text": "Your question here?",\n  "allow_custom": true,'
        )
        content = content.replace(
            'The user\'s selection will be returned as a standard chat message.',
            'Set `"allow_custom": true` if the user should be able to type their own custom answer.\nThe user\'s selection will be returned as a standard chat message.'
        )
        with open(base_path, "w") as f:
            f.write(content)
```
Run `python scripts/patch_prompt.py` and then delete the script.

- [ ] **Step 3: Commit**

```bash
git add configs/prompts/base.md configs/prompts/base_compact.md
git commit -m "feat: add allow_custom flag to dynamic widget instructions"
```
