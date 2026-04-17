import os
import subprocess

from dotenv import load_dotenv

from tools.base import audit_log

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


def _trim_output(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    trimmed = text[:MAX_OUTPUT_CHARS]
    return (
        trimmed
        + f"\n\n[OUTPUT TRUNCATED: showing first {MAX_OUTPUT_CHARS} characters of {len(text)} total]"
    )

def run_bash(command: str) -> str:
    """Execute a bash command either locally or in a Docker sandbox."""
    enabled = os.getenv("DOCKER_SANDBOX_ENABLED", "false").lower() == "true"
    image = os.getenv("DOCKER_IMAGE", "python:3.11-slim")

    if enabled:
        return run_bash_in_docker(command, image)
    else:
        return run_bash_locally(command)

def run_bash_locally(command: str) -> str:
    """Execute a bash command on the host system."""
    try:
        result = subprocess.run(
            ["bash", "-c", command],
            capture_output=True,
            text=True,
            timeout=LOCAL_TIMEOUT_SECONDS,
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[STDERR]\n{result.stderr}"

        status = "success" if result.returncode == 0 else "error"
        audit_log(
            "run_bash_local", {"command": command}, status, f"Exit code: {result.returncode}"
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
            "docker", "run", "--rm",
            "-v", f"{cwd}:/workspace",
            "-w", "/workspace",
            image,
            "bash", "-c", command
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
            "run_bash_docker", {"command": command, "image": image}, status, f"Exit code: {result.returncode}"
        )

        output = _trim_output(output)
        return (
            output
            if output
            else f"(Docker command executed with exit code {result.returncode}, no output)"
        )
    except subprocess.TimeoutExpired:
        audit_log("run_bash_docker", {"command": command}, "error", "Timeout")
        return f"Error: Docker command timed out after {DOCKER_TIMEOUT_SECONDS} seconds."
    except Exception as e:
        audit_log("run_bash_docker", {"command": command}, "error", str(e))
        return f"{type(e).__name__}: {e}"
