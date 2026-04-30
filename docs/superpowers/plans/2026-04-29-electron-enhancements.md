# Electron App Enhancement Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the Electron app from a visual stub into a production-grade, offline-capable desktop client with native system integration and meaningful HITL safety.

**Architecture:** Enhancements will span the Electron Main process (native features), Renderer process (UX/UI), and the Python API Bridge (data flow).

**Tech Stack:** Electron, Vanilla JS, CSS, Node.js (`child_process`, `fs`), Python (aiohttp).

---

### Phase 1: Offline Reliability (Bundle Dependencies)
**Goal:** Remove external CDN dependencies so the app works without an internet connection.
- [ ] **Step 1: Install dependencies**
  Run: `cd desktop && npm install marked highlight.js motion`
- [ ] **Step 2: Copy assets to a vendor folder (optional but cleaner)**
  Create `desktop/renderer/vendor/` and link them.
- [ ] **Step 3: Update `index.html`**
  Modify `<script>` and `<link>` tags to use local paths.
- [ ] **Step 4: Verification Test**
  Write a script to check if the local files exist and are loaded.
- [ ] **Step 5: Commit**

### Phase 2: Native HITL (Human-In-The-Loop) UI
**Goal:** Stop the bridge from auto-approving destructive actions.
- [ ] **Step 1: Modify `api_bridge.py`**
  Remove the auto-approve logic for `PendingConfirmationError`.
- [ ] **Step 2: IPC for Dialog**
  Add a handler in `main.js` that opens `dialog.showMessageBox`.
- [ ] **Step 3: Verification Test**
  Trigger a destructive tool (like `delete_file`) and ensure the dialog pops up.
- [ ] **Step 4: Commit**

### Phase 3: Real File Attachments
**Goal:** Send actual file content to the agent, not just filenames.
- [ ] **Step 1: Read files in `app.js`**
  Implement `FileReader` logic.
- [ ] **Step 2: Update API schema**
  Modify `handle_chat` to accept an `attachments` array.
- [ ] **Step 3: Verification Test**
  Upload a small text file and verify the agent can "see" its content.
- [ ] **Step 4: Commit**

### Phase 4: Auto-Launch Python Bridge
**Goal:** Start the backend automatically with Electron.
- [x] **Step 1: Spawn process in `main.js`**
  Use `child_process.spawn('python3', ['api_bridge.py'])`.
- [x] **Step 2: Lifecycle Management**
  Kill the child process on exit.
- [x] **Step 3: Verification Test**
  Start Electron and check if port 8790 is listening without manual intervention.
- [x] **Step 4: Commit**

### Phase 5: Assistant Message Copy Button
**Goal:** Add a copy-to-clipboard button for agent responses.
- [ ] **Step 1: Update UI**
  Modify `createMessageEl` to include the button.
- [ ] **Step 2: Implementation**
  Add click listener using `navigator.clipboard`.
- [ ] **Step 3: Verification Test**
  Click copy and verify clipboard content in a temporary file.
- [ ] **Step 4: Commit**

### Phase 6: System Tray & Status Monitoring
**Goal:** Add a tray icon to monitor the agent.
- [ ] **Step 1: Create Tray in `main.js`**
- [ ] **Step 2: Implement Menu**
- [ ] **Step 3: Verification Test**
  Verify the tray icon appears and the menu works.
- [ ] **Step 4: Commit**

### Phase 7: Desktop Notifications
**Goal:** Native notifications for task completion.
- [ ] **Step 1: Notification logic in `main.js`**
- [ ] **Step 2: Verification Test**
  Spawn a worker and wait for the notification.
- [ ] **Step 3: Commit**

### Phase 8: Global Keyboard Shortcut
**Goal:** Cmd+Shift+Y to show/hide.
- [ ] **Step 1: Register shortcut in `main.js`**
- [ ] **Step 2: Verification Test**
  Press keys and verify window focus.
- [ ] **Step 3: Commit**

### Phase 9: Stop/Abort Streaming
**Goal:** Cancel long responses.
- [ ] **Step 1: UI Button**
- [ ] **Step 2: AbortController in IPC**
- [ ] **Step 3: Verification Test**
  Start a long response, click stop, and verify the stream terminates.
- [ ] **Step 4: Commit**

### Phase 10: Conversation History Sidebar
**Goal:** Manage multiple sessions.
- [ ] **Step 1: Bridge Endpoint**
- [ ] **Step 2: Sidebar UI**
- [ ] **Step 3: Verification Test**
  Create two sessions and switch between them.
- [ ] **Step 4: Commit**

### Phase 11: Message Search
**Goal:** Search through chat history.
- [ ] **Step 1: Search UI**
- [ ] **Step 2: Filter Logic**
- [ ] **Step 3: Verification Test**
  Search for a specific keyword and verify filtering.
- [ ] **Step 4: Commit**

### Phase 12: Real Voice Recording (Whisper)
**Goal:** Actual voice input.
- [ ] **Step 1: MediaRecorder in Renderer**
- [ ] **Step 2: Transcode/Transcribe in Bridge**
- [ ] **Step 3: Verification Test**
  Record "Hello" and verify it appears as text in the input.
- [ ] **Step 4: Commit**
