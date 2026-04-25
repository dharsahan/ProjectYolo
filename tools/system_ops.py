import os
import select
import shlex
import signal
import subprocess
import threading
import time
import uuid

from dataclasses import dataclass

try:
    import fcntl
except ImportError:  # pragma: no cover - non-Unix platforms
    from typing import Any
    fcntl: Any = None  # type: ignore[no-redef]

from dotenv import load_dotenv

from tools.base import audit_log, resolve_and_verify_path

# Ensure env is loaded for settings
load_dotenv()


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


LOCAL_TIMEOUT_SECONDS = _get_int_env("BASH_TIMEOUT_SECONDS", 60)
DOCKER_TIMEOUT_SECONDS = _get_int_env("DOCKER_BASH_TIMEOUT_SECONDS", 90)
MAX_OUTPUT_CHARS = _get_int_env("MAX_BASH_OUTPUT_CHARS", 30000)
TERMINAL_READ_WAIT_MS = _get_int_env("TERMINAL_READ_WAIT_MS", 120, min_value=0)


@dataclass
class _TerminalSession:
    session_id: str
    process: subprocess.Popen
    master_fd: int
    shell: str
    cwd: str
    created_at: float


_terminal_sessions: dict[str, _TerminalSession] = {}
_terminal_lock = threading.Lock()


def _trim_output(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    trimmed = text[:MAX_OUTPUT_CHARS]
    return (
        trimmed
        + f"\n\n[OUTPUT TRUNCATED: showing first {MAX_OUTPUT_CHARS} characters of {len(text)} total]"
    )


def _set_nonblocking(fd: int) -> None:
    if fcntl is None:
        return
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)


def _read_from_fd(master_fd: int, max_chars: int) -> str:
    chunks: list[bytes] = []
    collected = 0

    while collected < max_chars:
        ready, _, _ = select.select([master_fd], [], [], 0)
        if not ready:
            break
        try:
            buf = os.read(master_fd, min(4096, max_chars - collected))
        except BlockingIOError:
            break
        except OSError:
            break

        if not buf:
            break
        chunks.append(buf)
        collected += len(buf)

    if not chunks:
        return ""
    return b"".join(chunks).decode("utf-8", errors="replace")


def _get_session(session_id: str) -> _TerminalSession:
    with _terminal_lock:
        sess = _terminal_sessions.get(session_id)
    if not sess:
        raise ValueError(f"Terminal session '{session_id}' not found.")
    return sess


def terminal_start(shell: str = "", cwd: str = "") -> str:
    """Start a persistent interactive terminal session and return a session ID."""
    if os.name == "nt":
        return "Error: interactive terminal sessions are currently supported on Unix-like systems only."

    try:
        import pty

        shell_bin = shell.strip() or os.getenv("SHELL", "/bin/bash")
        target_cwd = (
            str(resolve_and_verify_path(cwd)) if cwd and cwd.strip() else os.getcwd()
        )
        shell_parts = shlex.split(shell_bin)
        if not shell_parts:
            return "Error: Invalid shell command."

        master_fd, slave_fd = pty.openpty()
        proc = subprocess.Popen(
            shell_parts + ["-i"],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=target_cwd,
            env=os.environ.copy(),
            start_new_session=True,
            close_fds=True,
        )
        os.close(slave_fd)
        _set_nonblocking(master_fd)

        session_id = str(uuid.uuid4())
        session = _TerminalSession(
            session_id=session_id,
            process=proc,
            master_fd=master_fd,
            shell=" ".join(shell_parts),
            cwd=target_cwd,
            created_at=time.time(),
        )

        with _terminal_lock:
            _terminal_sessions[session_id] = session

        time.sleep(max(0, TERMINAL_READ_WAIT_MS) / 1000.0)
        banner = _read_from_fd(master_fd, MAX_OUTPUT_CHARS)

        audit_log(
            "terminal_start",
            {"session_id": session_id, "shell": session.shell, "cwd": target_cwd},
            "success",
            f"PID: {proc.pid}",
        )

        if banner:
            banner = _trim_output(banner)
            return (
                f"Terminal session started. session_id={session_id}\n"
                f"shell={session.shell} cwd={target_cwd} pid={proc.pid}\n"
                f"[INITIAL_OUTPUT]\n{banner}"
            )

        return (
            f"Terminal session started. session_id={session_id}\n"
            f"shell={session.shell} cwd={target_cwd} pid={proc.pid}"
        )
    except Exception as e:
        audit_log("terminal_start", {"shell": shell, "cwd": cwd}, "error", str(e))
        return f"Error starting terminal session: {e}"


def terminal_send(
    session_id: str,
    text: str,
    append_newline: bool = True,
    read_after_send: bool = True,
) -> str:
    """Send text to an interactive terminal session (like typing then Enter)."""
    try:
        session = _get_session(session_id)
        if session.process.poll() is not None:
            return (
                f"Session '{session_id}' has already exited with code {session.process.returncode}."
            )

        payload = text
        if append_newline:
            payload += "\n"

        os.write(session.master_fd, payload.encode("utf-8", errors="replace"))
        audit_log(
            "terminal_send",
            {"session_id": session_id, "text_len": len(text)},
            "success",
        )

        if not read_after_send:
            return f"Input sent to session '{session_id}'."

        time.sleep(max(0, TERMINAL_READ_WAIT_MS) / 1000.0)
        out = _read_from_fd(session.master_fd, MAX_OUTPUT_CHARS)
        if not out:
            return f"Input sent to session '{session_id}'. No immediate output."

        return _trim_output(out)
    except Exception as e:
        audit_log("terminal_send", {"session_id": session_id}, "error", str(e))
        return f"Error sending terminal input: {e}"


def terminal_read(session_id: str, max_chars: int = MAX_OUTPUT_CHARS) -> str:
    """Read currently available output from a terminal session without sending input."""
    try:
        session = _get_session(session_id)
        out = _read_from_fd(session.master_fd, max(1, max_chars))
        status = (
            "running"
            if session.process.poll() is None
            else f"exited({session.process.returncode})"
        )
        if not out:
            return f"No new output. Session '{session_id}' status={status}."

        return f"[status={status}]\n" + _trim_output(out)
    except Exception as e:
        audit_log("terminal_read", {"session_id": session_id}, "error", str(e))
        return f"Error reading terminal output: {e}"


def terminal_stop(session_id: str, force: bool = False) -> str:
    """Stop and clean up an interactive terminal session."""
    try:
        with _terminal_lock:
            session = _terminal_sessions.pop(session_id, None)
        if not session:
            return f"Session '{session_id}' not found."

        proc = session.process
        if proc.poll() is None:
            try:
                sig = signal.SIGKILL if force else signal.SIGTERM
                os.killpg(proc.pid, sig)
            except Exception:
                if force:
                    proc.kill()
                else:
                    proc.terminate()

            try:
                proc.wait(timeout=2 if force else 5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)

        try:
            os.close(session.master_fd)
        except OSError:
            pass

        audit_log(
            "terminal_stop",
            {"session_id": session_id, "force": force},
            "success",
            f"Exit code: {proc.returncode}",
        )
        return f"Terminal session '{session_id}' stopped with exit code {proc.returncode}."
    except Exception as e:
        audit_log("terminal_stop", {"session_id": session_id}, "error", str(e))
        return f"Error stopping terminal session: {e}"


def _parse_session_id(start_output: str) -> str:
    marker = "session_id="
    idx = start_output.find(marker)
    if idx < 0:
        return ""
    rest = start_output[idx + len(marker) :]
    token = rest.splitlines()[0].split()[0].strip()
    return token


def terminal_interactive_run(
    command: str = "",
    inputs: list[str] | None = None,
    cwd: str = "",
    shell: str = "",
    stop_after: bool = True,
    force_stop: bool = False,
) -> str:
    """Run a full interactive terminal flow: start, send command/inputs, read output, optional stop."""
    session_id = ""
    transcript: list[str] = []

    try:
        start_output = terminal_start(shell=shell, cwd=cwd)
        transcript.append(f"[START]\n{start_output}")

        session_id = _parse_session_id(start_output)
        if not session_id:
            audit_log(
                "terminal_interactive_run",
                {"command": command, "cwd": cwd},
                "error",
                "Failed to parse session_id from terminal_start output",
            )
            return "\n\n".join(transcript)

        if command:
            cmd_output = terminal_send(
                session_id=session_id,
                text=command,
                append_newline=True,
                read_after_send=True,
            )
            transcript.append(f"[COMMAND]\n$ {command}\n{cmd_output}")

        for idx, user_input in enumerate(inputs or [], start=1):
            step_output = terminal_send(
                session_id=session_id,
                text=user_input,
                append_newline=True,
                read_after_send=True,
            )
            transcript.append(f"[INPUT {idx}]\n{user_input}\n{step_output}")

        final_read = terminal_read(session_id=session_id)
        if not final_read.startswith("No new output"):
            transcript.append(f"[FINAL_READ]\n{final_read}")

        if stop_after:
            stop_output = terminal_stop(session_id=session_id, force=force_stop)
            transcript.append(f"[STOP]\n{stop_output}")

        audit_log(
            "terminal_interactive_run",
            {
                "session_id": session_id,
                "command": command,
                "inputs_count": len(inputs or []),
                "stop_after": stop_after,
            },
            "success",
        )
        return _trim_output("\n\n".join(transcript))
    except Exception as e:
        if session_id and stop_after:
            terminal_stop(session_id=session_id, force=True)
        audit_log(
            "terminal_interactive_run",
            {"session_id": session_id, "command": command, "cwd": cwd},
            "error",
            str(e),
        )
        transcript.append(f"Error in interactive run: {e}")
        return _trim_output("\n\n".join(transcript))


def run_bash(command: str) -> str:
    """Execute a bash command either locally or in a Docker sandbox."""
    enabled = os.getenv("DOCKER_SANDBOX_ENABLED", "false").lower() == "true"
    image = os.getenv("DOCKER_IMAGE", "python:3.11-slim")

    if enabled:
        return run_bash_in_docker(command, image)
    else:
        return run_bash_locally(command)


def run_bash_locally(command: str) -> str:
    """Execute a command on the host system using the appropriate shell."""
    try:
        shell = ["cmd", "/c"] if os.name == "nt" else ["bash", "-c"]
        result = subprocess.run(
            shell + [command],
            capture_output=True,
            text=True,
            timeout=LOCAL_TIMEOUT_SECONDS,
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[STDERR]\n{result.stderr}"

        status = "success" if result.returncode == 0 else "error"
        audit_log(
            "run_bash_local",
            {"command": command},
            status,
            f"Exit code: {result.returncode}",
        )

        output = _trim_output(output)
        return (
            output
            if output
            else f"(Command executed with exit code {result.returncode}, no output)"
        )
    except subprocess.TimeoutExpired:
        audit_log("run_bash_local", {"command": command}, "error", "Timeout")
        return f"Error: Command timed out after {LOCAL_TIMEOUT_SECONDS} seconds."
    except Exception as e:
        audit_log("run_bash_local", {"command": command}, "error", str(e))
        return f"{type(e).__name__}: {e}"


def run_bash_in_docker(command: str, image: str) -> str:
    """Execute a bash command inside a Docker container mounting the CWD."""
    try:
        cwd = os.getcwd()
        # docker run --rm -v CWD:/workspace -w /workspace IMAGE bash -c COMMAND
        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{cwd}:/workspace",
            "-w",
            "/workspace",
            image,
            "bash",
            "-c",
            command,
        ]

        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            timeout=DOCKER_TIMEOUT_SECONDS,
        )

        output = result.stdout
        if result.stderr:
            output += f"\n[STDERR]\n{result.stderr}"

        status = "success" if result.returncode == 0 else "error"
        audit_log(
            "run_bash_docker",
            {"command": command, "image": image},
            status,
            f"Exit code: {result.returncode}",
        )

        output = _trim_output(output)
        return (
            output
            if output
            else f"(Docker command executed with exit code {result.returncode}, no output)"
        )
    except subprocess.TimeoutExpired:
        audit_log("run_bash_docker", {"command": command}, "error", "Timeout")
        return (
            f"Error: Docker command timed out after {DOCKER_TIMEOUT_SECONDS} seconds."
        )
    except Exception as e:
        audit_log("run_bash_docker", {"command": command}, "error", str(e))
        return f"{type(e).__name__}: {e}"
