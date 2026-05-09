# Design Spec: Live Interactive Browser Streaming

**Date:** 2026-05-02
**Topic:** Live Browser Streaming (CDP Screencast + WebSockets)
**Goal:** Implement a low-latency, interactive video stream of the persistent headless browser (Camoufox/Playwright) to the Electron desktop application, allowing the user to solve CAPTCHAs, perform logins, or manually interact with sites in real-time.

## 1. Architecture & Concept
The system will use Chrome DevTools Protocol (CDP) via Playwright to screencast the active browser page to the desktop client.
The backend will expose an `aiohttp` WebSocket endpoint at `/browser/stream`. The Electron frontend will connect to this WebSocket, display the stream of JPEG frames on an `<img>` or `<canvas>`, and capture mouse/keyboard events to send back to the server to drive the headless browser.

## 2. Backend Implementation (Python)
### `desktop/api_bridge.py`
- Add a new `aiohttp.web.WebSocketResponse` handler mapped to `/browser/stream`.
- On connection, it will invoke a streaming function from `browser_ops.py`.
- It will enter a loop listening for incoming JSON messages from the WebSocket:
  - `{"type": "mousemove", "x": int, "y": int}`
  - `{"type": "mousedown", "button": str}`
  - `{"type": "mouseup", "button": str}`
  - `{"type": "keydown", "key": str}`
  - `{"type": "keyup", "key": str}`
  - `{"type": "wheel", "deltaX": float, "deltaY": float}`
- These JSON messages will trigger the corresponding Playwright `page.mouse` and `page.keyboard` commands.

### `tools/browser_ops.py`
- Add a new async function `browser_start_screencast(ws: aiohttp.web.WebSocketResponse)`.
- It will ensure a browser page is initialized (via `_get_page()`).
- It will acquire a CDP session: `cdp = await page.context.new_cdp_session(page)`.
- It will listen for the `Page.screencastFrame` event:
  - When a frame arrives, it will call `cdp.send('Page.screencastFrameAck', {'sessionId': event['sessionId']})`.
  - It will forward the Base64 image payload over the WebSocket `ws.send_json({"type": "frame", "data": event["data"]})`.
- It will initiate the stream: `await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 50, "everyNthFrame": 1})`.

## 3. Frontend Implementation (Electron / HTML / JS / CSS)
### `desktop/renderer/index.html`
- Add a "Live Browser" panel/modal UI (hidden by default).
- The panel will contain an `<img>` tag (e.g., `<img id="browser-stream-img">`) centered on the screen.
- Add a "Close" button to stop the stream.
- Add a button (e.g., "Live Browser") somewhere in the UI (perhaps next to the settings or workers button) to open the modal and initiate the connection.

### `desktop/renderer/app.js`
- Create a `WebSocket` connection to `ws://127.0.0.1:<PORT>/browser/stream` when the Live Browser panel is opened.
- Listen for WebSocket `message` events:
  - If `data.type === "frame"`, update the `<img>.src` to `data:image/jpeg;base64,${data.data}`.
- Attach event listeners to the `<img>` element:
  - `mousemove`, `mousedown`, `mouseup`, `wheel`, `keydown`, `keyup`.
  - Calculate relative X/Y coordinates based on the image's bounding client rect to ensure clicks map accurately to the headless browser's viewport.
  - Forward these events as JSON over the WebSocket connection.
- When the panel is closed, call `ws.close()`.

### `desktop/renderer/styles.css`
- Add CSS for the Live Browser modal (`.browser-modal-overlay`, `.browser-modal-content`).
- Style the `<img>` tag to fit the screen while maintaining aspect ratio (`object-fit: contain;`).
- Set `user-select: none;` and `-webkit-user-drag: none;` on the image to prevent native dragging.

## 4. Security & Error Handling
- The WebSocket connection should gracefully disconnect and clean up the CDP session when closed.
- Playwright API calls inside the message handler loop should be wrapped in try/except blocks so a single failed click (e.g., page navigation during interaction) doesn't crash the WebSocket loop.