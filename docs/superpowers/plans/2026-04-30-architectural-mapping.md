# Architectural Mapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide a comprehensive architectural mapping of Project Yolo, from core orchestration to peripheral gateways and the Rust core.

**Architecture:** A top-down investigative approach using `codebase_investigator` for automated mapping and manual surgical reads for logic verification. Synthesis will be delivered via visual diagrams and a final report.

**Tech Stack:** Python, Rust, Electron, Gemini CLI Toolset.

---

### Task 1: Core Orchestration Mapping

**Files:**
- Analyze: `agent.py`, `llm_router.py`, `prompt_builder.py`, `tool_dispatcher.py`

- [ ] **Step 1: Map symbols and dependencies of core components**
Run: `invoke_agent agent_name="codebase_investigator" prompt="Map all major classes and functions in agent.py, llm_router.py, prompt_builder.py, and tool_dispatcher.py. Identify how they interact (call graph) and what external libraries they depend on."`

- [ ] **Step 2: Trace a typical agent loop**
Run: `grep_search pattern="def run" file_path="agent.py"` followed by `read_file` to trace the execution flow from input to output.

- [ ] **Step 3: Document findings in `ANALYSIS.md`**
Update `ANALYSIS.md` with a "Core Orchestration" section.

---

### Task 2: Gateway & Bridge Analysis

**Files:**
- Analyze: `tui.py`, `discord_gateway.py`, `bot.py`, `desktop/main.js`, `desktop/api_bridge.py`

- [ ] **Step 1: Map gateway entry points**
Run: `invoke_agent agent_name="codebase_investigator" prompt="Investigate how tui.py, discord_gateway.py, and bot.py initialize the agent. Identify the common interface or base class they use to communicate with the core."`

- [ ] **Step 2: Analyze Electron-to-Python bridge**
Run: `read_file file_path="desktop/api_bridge.py"` and `read_file file_path="desktop/main.js"` to understand the IPC/Socket communication.

- [ ] **Step 3: Document findings in `ANALYSIS.md`**
Update `ANALYSIS.md` with a "Gateway Integration" section.

---

### Task 3: Tool & Plugin Registry Deep Dive

**Files:**
- Analyze: `tools/`, `plugin_manager.py`, `tool_dispatcher.py`

- [ ] **Step 1: Inventory all tools**
Run: `list_directory dir_path="tools/"` and `grep_search pattern="class.*(BaseTool|Tool)" dir_path="tools/"`

- [ ] **Step 2: Map dynamic loading logic**
Run: `read_file file_path="plugin_manager.py"` to see how tools are discovered and loaded at runtime.

- [ ] **Step 3: Document findings in `ANALYSIS.md`**
Update `ANALYSIS.md` with a "Tool & Plugin System" section.

---

### Task 4: Deep Core & Background Workers

**Files:**
- Analyze: `rust/yolo-core/`, `worker.py`, `monitoring.py`

- [ ] **Step 1: Map Rust core interfaces**
Run: `invoke_agent agent_name="codebase_investigator" prompt="Investigate the rust/yolo-core/ directory. Identify the main entry points (e.g., lib.rs, main.rs) and how the Python core calls into these (e.g., PyO3, subprocess, or CFFI)."`

- [ ] **Step 2: Analyze worker lifecycle**
Run: `read_file file_path="worker.py"` to understand how background tasks are queued and executed.

- [ ] **Step 3: Document findings in `ANALYSIS.md`**
Update `ANALYSIS.md` with a "Deep Core & Workers" section.

---

### Task 5: State, Memory & Persistence

**Files:**
- Analyze: `session.py`, `memory_service.py`, `memory_ops.py`, `database_ops.py`

- [ ] **Step 1: Map session management**
Run: `read_file file_path="session.py"` to understand context window management and history tracking.

- [ ] **Step 2: Trace memory flow**
Run: `grep_search pattern="mem0" dir_path="."` and analyze how `memory_service.py` interacts with the mem0 library.

- [ ] **Step 3: Document findings in `ANALYSIS.md`**
Update `ANALYSIS.md` with a "State & Memory" section.

---

### Task 6: Visual Synthesis & Final Review

- [ ] **Step 1: Generate Architecture Diagrams**
Use the Visual Companion to create SVG/Mermaid diagrams for each subsystem mapped.

- [ ] **Step 2: Final synthesis and report**
Consolidate all sections of `ANALYSIS.md` into a final architectural report.
