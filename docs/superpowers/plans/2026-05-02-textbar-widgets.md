# Textbar-Anchored Dynamic Widgets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance the dynamic widget feature by having the widget replace the chat input textbar rather than rendering inline within the chat history.

**Architecture:** We will modify `index.html` to add a new `#active-widget-container` inside the `#input-area`. In `app.js`, we will intercept `widget` code blocks during markdown rendering, save their payload to a global variable, and render them in the bottom container instead of the chat stream. We will also add functions to toggle between the normal input wrapper and the widget container.

**Tech Stack:** HTML, CSS, JavaScript (marked.js).

---

### Task 1: UI Structure & State Management

**Files:**
- Modify: `desktop/renderer/index.html`
- Modify: `desktop/renderer/app.js`

- [ ] **Step 1: Add widget container to HTML**

In `desktop/renderer/index.html`, locate the `<div class="input-wrapper floating-input">` element. Insert the new widget container directly below it, still inside `#input-area`.

```html
      <!-- Input area -->
      <div id="input-area">
        <div class="input-wrapper floating-input">
          <!-- existing input wrapper content -->
        </div>
        <div id="active-widget-container" class="hidden"></div>
      </div>
```

- [ ] **Step 2: Add DOM references and UI toggle functions in app.js**

In `desktop/renderer/app.js`, add the new container to the `dom` object and create the `clearActiveWidget` and `renderActiveWidget` functions.

```javascript
  const dom = {
    // ... existing dom elements ...
    inputWrapper: document.querySelector('.input-wrapper'),
    activeWidgetContainer: document.getElementById('active-widget-container'),
  };

  // State to hold the current widget payload
  window.activeWidgetData = null;

  function clearActiveWidget() {
    window.activeWidgetData = null;
    dom.activeWidgetContainer.innerHTML = '';
    dom.activeWidgetContainer.classList.add('hidden');
    dom.inputWrapper.classList.remove('hidden');
    dom.input.focus();
  }

  function renderActiveWidget(data) {
    window.activeWidgetData = data;
    
    if (data.type === 'choice') {
      const optionsHtml = (data.options || []).map(opt => {
        const label = opt.label.replace(/</g, '&lt;').replace(/>/g, '&gt;');
        const val = opt.value.replace(/"/g, '&quot;');
        return `<button class="widget-btn" data-widget-id="${data.id}" data-value="${val}">${label}</button>`;
      }).join('');
      
      const title = (data.text || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      
      dom.activeWidgetContainer.innerHTML = `
        <div class="dynamic-widget textbar-widget" id="widget-${data.id}">
          <div class="widget-title">${title}</div>
          <div class="widget-options">
            ${optionsHtml}
          </div>
          <div class="widget-cancel" onclick="window.clearActiveWidget()">Cancel</div>
        </div>
      `;
      
      dom.inputWrapper.classList.add('hidden');
      dom.activeWidgetContainer.classList.remove('hidden');
    }
  }

  // Expose to window so onclick works
  window.clearActiveWidget = clearActiveWidget;
```

- [ ] **Step 3: Commit changes**

```bash
git add desktop/renderer/index.html desktop/renderer/app.js
git commit -m "feat(desktop): add active widget container and state management"
```

---

### Task 2: Markdown Interception & Rendering

**Files:**
- Modify: `desktop/renderer/app.js`

- [ ] **Step 1: Update marked.js custom renderer**

In `desktop/renderer/app.js`, locate the `renderer.code` override. Change it so that when it successfully parses a `widget`, it calls `renderActiveWidget(data)` and returns an empty string or placeholder for the chat log, rather than the raw HTML.

```javascript
        renderer.code = function(tokenOrCode, language, isEscaped) {
          let codeText = '';
          let lang = '';
          
          if (typeof tokenOrCode === 'object' && tokenOrCode !== null) {
            codeText = tokenOrCode.text;
            lang = tokenOrCode.lang;
          } else {
            codeText = tokenOrCode;
            lang = language;
          }

          if (lang === 'widget') {
            try {
              const data = JSON.parse(codeText);
              // Call the new global render function
              if (typeof renderActiveWidget === 'function') {
                renderActiveWidget(data);
              }
              // Return a placeholder for the chat history
              return `<div class="widget-placeholder"><em>[Interactive Widget Expanded]</em></div>`;
            } catch (e) {
              console.error("Failed to parse widget JSON:", e);
            }
          }
          return originalCodeRenderer(tokenOrCode, language, isEscaped);
        };
```

- [ ] **Step 2: Commit changes**

```bash
git add desktop/renderer/app.js
git commit -m "feat(desktop): intercept widget markdown to render in textbar"
```

---

### Task 3: Event Delegation & Styling

**Files:**
- Modify: `desktop/renderer/app.js`
- Modify: `desktop/renderer/styles.css`

- [ ] **Step 1: Remove old delegation and add new event listener**

In `desktop/renderer/app.js`, remove the previously added event listener on `dom.messages` for `.widget-btn`. Instead, add it to `dom.activeWidgetContainer`.

```javascript
    // In bindEvents()
    dom.activeWidgetContainer.addEventListener('click', (e) => {
      const btn = e.target.closest('.widget-btn');
      if (!btn) return;
      
      const widget = btn.closest('.dynamic-widget');
      if (!widget || widget.classList.contains('locked')) return;

      // Lock the widget visually
      widget.classList.add('locked');
      btn.setAttribute('data-selected', 'true');

      // Extract value
      const value = btn.getAttribute('data-value');
      const widgetId = btn.getAttribute('data-widget-id');
      
      // Send the response
      sendMessage(`[Widget Response: ${widgetId}] Selected: ${value}`);
      
      // Clear the widget and restore input bar
      setTimeout(() => {
        clearActiveWidget();
      }, 300); // brief delay so user sees selection
    });
```

- [ ] **Step 2: Update CSS for Textbar Placement**

In `desktop/renderer/styles.css`, add styles to ensure the `#active-widget-container` looks like part of the input area.

```css
/* --- Textbar-Anchored Widget --- */
#active-widget-container {
  width: 100%;
}

.textbar-widget {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 15px;
  margin: 0; /* Remove top/bottom margin since it's anchored */
  font-family: var(--font-body);
  box-shadow: 0 -4px 15px rgba(0,0,0,0.2);
}

.widget-cancel {
  color: var(--text-muted);
  font-size: 12px;
  text-align: center;
  margin-top: 12px;
  cursor: pointer;
  transition: color 0.2s ease;
}

.widget-cancel:hover {
  color: var(--text-primary);
  text-decoration: underline;
}

.widget-placeholder {
  color: var(--text-muted);
  font-size: 0.9em;
  padding: 8px 0;
}
```

- [ ] **Step 3: Commit changes**

```bash
git add desktop/renderer/app.js desktop/renderer/styles.css
git commit -m "feat(desktop): style textbar widget and handle interactions"
```