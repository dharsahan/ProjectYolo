"""
Git Integration Tools — structured wrappers around git operations.

These replace verbose `run_bash("git ...")` calls with tools that return
parsed, token-efficient output.  All commands execute in the current
working directory.
"""

import json
import os
import subprocess

from tools.base import audit_log


def _get_int_env(name: str, default: int, min_value: int = 1) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if value < min_value:
        return default
    return value


GIT_TIMEOUT_SECONDS = _get_int_env("GIT_TIMEOUT_SECONDS", 30)


def _run_git(*args: str, timeout: int = GIT_TIMEOUT_SECONDS) -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr)."""
    cmd = ["git"] + list(args)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd(),
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Git command timed out after {timeout}s"
    except Exception as e:
        return -1, "", str(e)


def git_status() -> str:
    """Get the current git repository status in a structured format."""
    try:
        # Check if we're in a git repo
        rc, _, stderr = _run_git("rev-parse", "--is-inside-work-tree")
        if rc != 0:
            return "Error: Not inside a git repository."

        # Get branch name
        rc, branch, _ = _run_git("branch", "--show-current")
        branch = branch.strip() or "(detached HEAD)"

        # Get short status
        rc, status_output, _ = _run_git("status", "--porcelain=v1")

        # Parse status into categories
        staged = []
        modified = []
        untracked = []
        for line in status_output.splitlines():
            if not line or len(line) < 3:
                continue
            index_status = line[0]
            worktree_status = line[1]
            filepath = line[3:]

            if index_status in {"A", "M", "D", "R", "C"}:
                staged.append(f"{index_status} {filepath}")
            if worktree_status == "M":
                modified.append(filepath)
            elif worktree_status == "D":
                modified.append(f"(deleted) {filepath}")
            if index_status == "?" and worktree_status == "?":
                untracked.append(filepath)

        # Get ahead/behind info
        rc, ahead_behind, _ = _run_git(
            "rev-list", "--left-right", "--count", "HEAD...@{upstream}"
        )
        ahead = behind = 0
        if rc == 0 and ahead_behind.strip():
            parts = ahead_behind.strip().split()
            if len(parts) == 2:
                ahead, behind = int(parts[0]), int(parts[1])

        result = {
            "branch": branch,
            "staged": staged,
            "modified": modified,
            "untracked": untracked,
            "ahead": ahead,
            "behind": behind,
            "clean": not (staged or modified or untracked),
        }

        audit_log("git_status", {}, "success")
        return json.dumps(result, indent=2)
    except Exception as e:
        audit_log("git_status", {}, "error", str(e))
        return f"Error: {e}"


def git_diff(path: str = "", staged: bool = False) -> str:
    """Show the diff for modified files. Use `staged=true` for staged changes."""
    try:
        args = ["diff"]
        if staged:
            args.append("--cached")
        args.extend(["--stat", "--patch"])
        if path:
            args.extend(["--", path])

        rc, output, stderr = _run_git(*args)
        if rc != 0:
            return f"Error: {stderr.strip()}"

        if not output.strip():
            scope = "staged" if staged else "working tree"
            target = f" for `{path}`" if path else ""
            return f"No changes in {scope}{target}."

        # Truncate very large diffs to save tokens
        max_chars = _get_int_env("MAX_GIT_DIFF_CHARS", 15000)
        if len(output) > max_chars:
            output = (
                output[:max_chars]
                + f"\n\n[DIFF TRUNCATED: showing first {max_chars} of {len(output)} chars]"
            )

        audit_log("git_diff", {"path": path, "staged": staged}, "success")
        return output
    except Exception as e:
        audit_log("git_diff", {"path": path}, "error", str(e))
        return f"Error: {e}"


def git_log(count: int = 10, oneline: bool = True) -> str:
    """Show recent commit history."""
    try:
        count = min(max(1, count), 50)  # Clamp to 1-50

        if oneline:
            args = ["log", f"-{count}", "--oneline", "--decorate"]
        else:
            args = [
                "log",
                f"-{count}",
                "--format=%h | %an | %ar | %s",
                "--decorate",
            ]

        rc, output, stderr = _run_git(*args)
        if rc != 0:
            return f"Error: {stderr.strip()}"

        if not output.strip():
            return "No commits found."

        audit_log("git_log", {"count": count}, "success")
        return output.strip()
    except Exception as e:
        audit_log("git_log", {"count": count}, "error", str(e))
        return f"Error: {e}"


def git_commit(message: str, add_all: bool = False) -> str:
    """Create a git commit. Optionally stage all changes first."""
    try:
        if not message or not message.strip():
            return "Error: Commit message cannot be empty."

        if add_all:
            rc, _, stderr = _run_git("add", "-A")
            if rc != 0:
                return f"Error staging files: {stderr.strip()}"

        # Check if there's anything to commit
        rc, status, _ = _run_git("diff", "--cached", "--quiet")
        if rc == 0:
            return "Nothing to commit. Stage changes first or use `add_all=true`."

        rc, output, stderr = _run_git("commit", "-m", message)
        if rc != 0:
            return f"Error committing: {stderr.strip()}"

        audit_log("git_commit", {"message": message, "add_all": add_all}, "success")
        return output.strip()
    except Exception as e:
        audit_log("git_commit", {"message": message}, "error", str(e))
        return f"Error: {e}"


def git_branch(name: str = "", switch: bool = False, delete: bool = False) -> str:
    """List, create, switch, or delete branches."""
    try:
        # List branches
        if not name:
            rc, output, stderr = _run_git("branch", "-a", "--no-color")
            if rc != 0:
                return f"Error: {stderr.strip()}"
            audit_log("git_branch", {"action": "list"}, "success")
            return output.strip() or "No branches found."

        if delete:
            rc, output, stderr = _run_git("branch", "-d", name)
            if rc != 0:
                return f"Error deleting branch: {stderr.strip()}"
            audit_log("git_branch", {"action": "delete", "name": name}, "success")
            return output.strip()

        if switch:
            rc, output, stderr = _run_git("switch", name)
            if rc != 0:
                # Try checkout as fallback for older git
                rc, output, stderr = _run_git("checkout", name)
                if rc != 0:
                    return f"Error switching to branch: {stderr.strip()}"
            audit_log("git_branch", {"action": "switch", "name": name}, "success")
            return f"Switched to branch `{name}`."

        # Create branch
        rc, output, stderr = _run_git("branch", name)
        if rc != 0:
            return f"Error creating branch: {stderr.strip()}"
        audit_log("git_branch", {"action": "create", "name": name}, "success")
        return f"Branch `{name}` created."
    except Exception as e:
        audit_log("git_branch", {"name": name}, "error", str(e))
        return f"Error: {e}"


def git_stash(action: str = "list", message: str = "") -> str:
    """Manage the git stash: list, push, pop, or apply."""
    try:
        action = action.lower().strip()

        if action == "list":
            rc, output, stderr = _run_git("stash", "list")
            if rc != 0:
                return f"Error: {stderr.strip()}"
            audit_log("git_stash", {"action": "list"}, "success")
            return output.strip() or "No stashes found."

        if action in {"push", "save"}:
            args = ["stash", "push"]
            if message:
                args.extend(["-m", message])
            rc, output, stderr = _run_git(*args)
            if rc != 0:
                return f"Error stashing: {stderr.strip()}"
            audit_log("git_stash", {"action": "push"}, "success")
            return output.strip()

        if action == "pop":
            rc, output, stderr = _run_git("stash", "pop")
            if rc != 0:
                return f"Error popping stash: {stderr.strip()}"
            audit_log("git_stash", {"action": "pop"}, "success")
            return output.strip()

        if action == "apply":
            rc, output, stderr = _run_git("stash", "apply")
            if rc != 0:
                return f"Error applying stash: {stderr.strip()}"
            audit_log("git_stash", {"action": "apply"}, "success")
            return output.strip()

        return f"Error: Unknown stash action `{action}`. Use: list, push, pop, apply."
    except Exception as e:
        audit_log("git_stash", {"action": action}, "error", str(e))
        return f"Error: {e}"
