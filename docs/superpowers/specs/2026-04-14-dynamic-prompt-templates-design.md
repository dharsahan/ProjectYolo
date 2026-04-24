# Dynamic Prompt Template System Design

**Goal:** Decouple system instructions from hardcoded strings in `agent.py` and move them to dynamic, persistent Markdown templates in `~/.yolo/prompts/`.

## Architecture

### 1. Storage Layer
- **Location:** `~/.yolo/prompts/`
- **Format:** Markdown (`.md`) files.
- **Initial Templates:**
    - `base.md`: Core identity, mandates, and communication style.
    - `self_upgrade.md`: Formal Research -> Implement -> Validate -> Evolve workflow.
    - `experience.md`: Instructions for the `learn_experience` mandate.
    - `think.md`: Instructions for complex planning and sequential execution.

### 2. Logic Layer (`tools/prompt_ops.py`)
- **`initialize_default_prompts()`**: Seeds `~/.yolo/prompts/` with defaults if empty.
- **`load_template(name: str, **context) -> str`**: 
    - Reads from the filesystem.
    - Replaces `{{placeholder}}` with values from `**context`.
    - Handles missing files by falling back to hardcoded defaults.
- **`render_system_prompt(session, memory_service) -> str`**:
    - Aggregates active directives based on session state (`think_mode`, `self_upgrade_active`, etc.).
    - Injects `{{memory_context}}` and `{{basic_facts}}` dynamically.

### 3. Integration Layer (`agent.py`)
- Remove static directive strings (e.g., `SELF_UPGRADE_SYSTEM_DIRECTIVE`).
- Update `run_agent_turn` to call the prompt manager at the start of every turn.
- Ensure the system message is fully reconstructed each turn to reflect changes in memory or template files.

## Dynamic Placeholders
The system will support the following standard placeholders:
- `{{user_id}}`: Current user ID.
- `{{current_time}}`: Current ISO timestamp.
- `{{memory_context}}`: Relevant long-term memories for the current turn.
- `{{basic_facts}}`: Durable user facts (preferences, name, etc.).

## Error Handling
- If a template file is missing, the system will log a warning and use a minimal hardcoded fallback to prevent agent failure.
- Malformed placeholders will be ignored or left as-is to avoid breaking the prompt structure.

## Success Criteria
1. System instructions are no longer present as strings in `agent.py`.
2. Changes to `.md` files in `~/.yolo/prompts/` are reflected in the next agent turn without a restart.
3. Yolo maintains its core mandates (Self-Upgrade, etc.) using the new templates.
