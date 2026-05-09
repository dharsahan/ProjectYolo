# Live Interactive Browser Streaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a low-latency, interactive video stream of the persistent headless browser to the Electron desktop application.

**Architecture:** Use Playwright's CDP `Page.startScreencast` to capture JPEG frames. Stream them over an `aiohttp` WebSocket endpoint in `api_bridge.py`. The Electron frontend connects to this WebSocket, renders the frames in an `<img>` tag, and sends mouse/keyboard coordinates back over the socket to trigger Playwright actions.

**Tech Stack:** Python 3, aiohttp, Playwright/Camoufox, HTML/JS/CSS.

---

### Task 1: Add CDP Screencast Logic to `browser_ops.py`

**Files:**
- Modify: `tools/browser_ops.py`

- [ ] **Step 1: Implement `browser_start_screencast` function**

```python
# Add this to the end of tools/browser_ops.py

import aiohttp
import json
import logging

logger = logging.getLogger(__name__)

async def browser_start_screencast(ws: aiohttp.web.WebSocketResponse):
    """
    Attach to the current browser page via CDP, start a screencast, 
    stream frames to the WebSocket, and listen for interaction events.
    """
    page = await _get_page()
    cdp = await page.context.new_cdp_session(page)
    
    async def handle_frame(event):
        try:
            # Acknowledge the frame so the browser sends the next one
            await cdp.send("Page.screencastFrameAck", {"sessionId": event["sessionId"]})
            # Send the base64 JPEG to the WebSocket
            await ws.send_json({"type": "frame", "data": event["data"]})
        except Exception as e:
            logger.error(f"Screencast frame error: {e}")

    cdp.on("Page.screencastFrame", handle_frame)
    await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 50, "everyNthFrame": 1})
    
    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                ev_type = data.get("type")
                
                try:
                    if ev_type == "mousemove":
                        await page.mouse.move(data["x"], data["y"])
                    elif ev_type == "mousedown":
                        await page.mouse.down(button=data.get("button", "left"))
                    elif ev_type == "mouseup":
                        await page.mouse.up(button=data.get("button", "left"))
                    elif ev_type == "click":
                        await page.mouse.click(data["x"], data["y"], button=data.get("button", "left"))
                    elif ev_type == "wheel":
                        await page.mouse.wheel(data["deltaX"], data["deltaY"])
                    elif ev_type == "keydown":
                        await page.keyboard.down(data["key"])
                    elif ev_type == "keyup":
                        await page.keyboard.up(data["key"])
                except Exception as inner_e:
                    logger.error(f"Error handling browser interaction: {inner_e}")
                    
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                break
    finally:
        try:
            await cdp.send("Page.stopScreencast")
            await cdp.detach()
        except Exception:
            pass
```

- [ ] **Step 2: Commit**

```bash
git add tools/browser_ops.py
git commit -m "feat: add CDP screencast streaming logic to browser_ops"
```

---

### Task 2: Add WebSocket Endpoint to `api_bridge.py`

**Files:**
- Modify: `desktop/api_bridge.py`

- [ ] **Step 1: Add `/browser/stream` endpoint**

```python
# Add near the other handlers in desktop/api_bridge.py

async def handle_browser_stream(request: web.Request) -> web.WebSocketResponse:
    """WebSocket endpoint for live browser streaming."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    from tools.browser_ops import browser_start_screencast
    
    try:
        await browser_start_screencast(ws)
    except Exception as e:
        import logging
        logging.error(f"Browser stream error: {e}")
        
    return ws

# In the `run_api_bridge` function, add the route:
# app.router.add_get("/browser/stream", handle_browser_stream)
```

- [ ] **Step 2: Commit**

```bash
git add desktop/api_bridge.py
git commit -m "feat: expose /browser/stream websocket endpoint"
```

---

### Task 3: Build Frontend Live Browser UI

**Files:**
- Modify: `desktop/renderer/index.html`
- Modify: `desktop/renderer/styles.css`
- Modify: `desktop/renderer/app.js`

- [ ] **Step 1: Add HTML markup**

```html
<!-- Add this right before the SETTINGS MODAL in desktop/renderer/index.html -->
    <!-- ═══════════════ LIVE BROWSER MODAL ═══════════════ -->
    <div id="browser-modal" class="modal-overlay hidden">
      <div class="browser-modal-container">
        <div class="browser-header">
          <h2>Live Browser</h2>
          <button id="close-browser-btn" class="icon-btn" title="Close Browser">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
          </button>
        </div>
        <div class="browser-content">
          <img id="browser-stream-img" draggable="false" />
        </div>
      </div>
    </div>

<!-- Add a button to open it in the sidebar (e.g. above the Settings button) -->
          <button id="open-browser-btn" class="icon-btn" title="Live Browser">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="3" y1="9" x2="21" y2="9"></line><line x1="9" y1="21" x2="9" y2="9"></line></svg>
          </button>
```

- [ ] **Step 2: Add CSS styling**

```css
/* Add to desktop/renderer/styles.css */
/* --- Live Browser Modal --- */
.browser-modal-container {
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: 12px;
  width: 90vw;
  height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5);
}

.browser-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
}

.browser-header h2 {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
}

.browser-content {
  flex: 1;
  background: #000;
  display: flex;
  justify-content: center;
  align-items: center;
  overflow: hidden;
  position: relative;
}

#browser-stream-img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  user-select: none;
  -webkit-user-drag: none;
  cursor: crosshair;
}
```

- [ ] **Step 3: Add JavaScript connection and events**

```javascript
// Add to desktop/renderer/app.js (in the DOM refs and init section)
// DOM refs:
// openBrowserBtn: $('#open-browser-btn'),
// browserModal: $('#browser-modal'),
// closeBrowserBtn: $('#close-browser-btn'),
// browserImg: $('#browser-stream-img'),

  let browserWs = null;

  function openLiveBrowser() {
    dom.browserModal.classList.remove('hidden');
    const wsUrl = `ws://127.0.0.1:${state.bridgePort}/browser/stream`;
    browserWs = new WebSocket(wsUrl);
    
    browserWs.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === 'frame') {
        dom.browserImg.src = `data:image/jpeg;base64,${msg.data}`;
      }
    };
    
    browserWs.onerror = (err) => console.error("Browser WS Error", err);
  }

  function closeLiveBrowser() {
    dom.browserModal.classList.add('hidden');
    if (browserWs) {
      browserWs.close();
      browserWs = null;
    }
    dom.browserImg.src = '';
  }

  // In bindEvents():
  dom.openBrowserBtn.addEventListener('click', openLiveBrowser);
  dom.closeBrowserBtn.addEventListener('click', closeLiveBrowser);

  // Mouse & Keyboard mapping for the image
  function getCoordinates(e) {
    const rect = dom.browserImg.getBoundingClientRect();
    // Calculate the actual displayed image dimensions based on object-fit: contain
    const imgRatio = dom.browserImg.naturalWidth / dom.browserImg.naturalHeight;
    const boxRatio = rect.width / rect.height;
    
    let renderWidth, renderHeight, offsetX = 0, offsetY = 0;
    
    if (imgRatio > boxRatio) {
      renderWidth = rect.width;
      renderHeight = rect.width / imgRatio;
      offsetY = (rect.height - renderHeight) / 2;
    } else {
      renderHeight = rect.height;
      renderWidth = rect.height * imgRatio;
      offsetX = (rect.width - renderWidth) / 2;
    }

    const x = (e.clientX - rect.left - offsetX) * (dom.browserImg.naturalWidth / renderWidth);
    const y = (e.clientY - rect.top - offsetY) * (dom.browserImg.naturalHeight / renderHeight);
    
    return { x: Math.max(0, Math.min(x, dom.browserImg.naturalWidth)), y: Math.max(0, Math.min(y, dom.browserImg.naturalHeight)) };
  }

  const mapButton = (e) => {
    if (e.button === 0) return 'left';
    if (e.button === 1) return 'middle';
    if (e.button === 2) return 'right';
    return 'left';
  };

  dom.browserImg.addEventListener('mousemove', (e) => {
    if (!browserWs || browserWs.readyState !== WebSocket.OPEN) return;
    const { x, y } = getCoordinates(e);
    browserWs.send(JSON.stringify({ type: 'mousemove', x, y }));
  });

  dom.browserImg.addEventListener('mousedown', (e) => {
    if (!browserWs || browserWs.readyState !== WebSocket.OPEN) return;
    e.preventDefault();
    browserWs.send(JSON.stringify({ type: 'mousedown', button: mapButton(e) }));
  });

  dom.browserImg.addEventListener('mouseup', (e) => {
    if (!browserWs || browserWs.readyState !== WebSocket.OPEN) return;
    e.preventDefault();
    browserWs.send(JSON.stringify({ type: 'mouseup', button: mapButton(e) }));
  });

  dom.browserImg.addEventListener('wheel', (e) => {
    if (!browserWs || browserWs.readyState !== WebSocket.OPEN) return;
    e.preventDefault();
    browserWs.send(JSON.stringify({ type: 'wheel', deltaX: e.deltaX, deltaY: e.deltaY }));
  });

  // To catch keyboard events, we need the modal or document to listen while open
  document.addEventListener('keydown', (e) => {
    if (!dom.browserModal.classList.contains('hidden') && browserWs && browserWs.readyState === WebSocket.OPEN) {
      if (e.key === 'Escape') return; // Let escape do something else or close it
      e.preventDefault();
      browserWs.send(JSON.stringify({ type: 'keydown', key: e.key }));
    }
  });

  document.addEventListener('keyup', (e) => {
    if (!dom.browserModal.classList.contains('hidden') && browserWs && browserWs.readyState === WebSocket.OPEN) {
      e.preventDefault();
      browserWs.send(JSON.stringify({ type: 'keyup', key: e.key }));
    }
  });
```

- [ ] **Step 4: Commit**

```bash
git add desktop/renderer/index.html desktop/renderer/styles.css desktop/renderer/app.js
git commit -m "feat: add live browser streaming UI to electron app"
```
