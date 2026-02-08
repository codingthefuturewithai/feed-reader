# How to Dockerize an MCP Server

A comprehensive guide for containerizing a Python-based MCP server with a management script for start/stop/update operations.

---

## Overview

This guide will help you:
1. Create a multi-stage Dockerfile using `uv` for fast dependency installation
2. Create a `.dockerignore` to keep the image lean
3. Create a Python management script (`scripts/docker.py`) for container lifecycle
4. Optionally create a `docker-compose.yml` for users who prefer compose

**Important:** The MCP server will be exposed via **streamable HTTP** on a `/mcp` endpoint, making it accessible to Claude Code via `--transport http`.

---

## Prerequisites

Before starting, ensure:
- Your MCP server runs with `python -m your_package`
- You have a `pyproject.toml` and `uv.lock` file
- Your server supports the `--transport streamable-http` flag (FastMCP does this)

---

## Critical: Host Binding for Docker

**This is the most common issue.** By default, many servers bind to `127.0.0.1` (localhost), which is unreachable from outside the container.

You MUST ensure your server binds to `0.0.0.0` when running in Docker.

### Solution: Add a `--host` CLI Option

If your server doesn't already have one, add a `--host` option:

```python
@click.option(
    "--host",
    default="127.0.0.1",
    help="Host to bind to (use 0.0.0.0 for Docker)"
)
def main(port: int, host: str, transport: str):
    # ... in the streamable-http section:
    server.settings.host = host
    server.settings.port = port
```

Then your Dockerfile CMD will use `--host 0.0.0.0`.

---

## Critical: DNS Rebinding Protection

**Another common issue.** The MCP library includes DNS rebinding protection that validates Host headers. This causes HTTP 421 errors when accessing from VMs or non-localhost clients.

### Solution: Make Protection Configurable

Add transport security settings to your FastMCP instantiation:

```python
import os
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

# Configure DNS rebinding protection (disabled by default for development)
dns_protection = os.getenv("MCP_DNS_REBINDING_PROTECTION", "false").lower() == "true"
allowed_hosts_env = os.getenv("MCP_ALLOWED_HOSTS", "")
allowed_hosts = [h.strip() for h in allowed_hosts_env.split(",") if h.strip()] if allowed_hosts_env else []

mcp_server = FastMCP(
    "Server Name",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=dns_protection,
        allowed_hosts=allowed_hosts
    )
)
```

**Environment Variables:**
- `MCP_DNS_REBINDING_PROTECTION` - Set to `true` to enable (default: `false`)
- `MCP_ALLOWED_HOSTS` - Comma-separated allowed Host headers (e.g., `localhost:19000,myhost:19000`)

---

## File 1: Dockerfile

Create a `Dockerfile` in your project root:

```dockerfile
# Build stage - install dependencies with uv
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv venv /app/.venv && \
    uv pip install --python /app/.venv/bin/python -e . --no-cache-dir
COPY your_package/ ./your_package/

# Runtime stage - minimal image
FROM python:3.12-slim AS runtime
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid 1000 --create-home appuser
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/your_package /app/your_package
COPY --from=builder /app/pyproject.toml /app/pyproject.toml

# Create directories for persistent data (adjust paths as needed)
RUN mkdir -p /home/appuser/.your_package \
             /home/appuser/.config/your_package \
             /home/appuser/.local/share/your_package && \
    chown -R appuser:appuser /home/appuser /app

USER appuser
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH="/app" HOME="/home/appuser"
ENV LOG_LEVEL="INFO" PORT="3001"
EXPOSE 3001

# Health check - verify the server is responding
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import socket; s = socket.socket(); s.settimeout(5); s.connect(('127.0.0.1', 3001)); s.close()"

# CRITICAL: Use --host 0.0.0.0 to bind to all interfaces
CMD ["python", "-m", "your_package", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "3001"]
```

**Customize:**
- Replace `your_package` with your actual package name
- Adjust the data directories in the `mkdir` command to match where your server stores data
- The internal port (3001) can be any port; it will be mapped to the external port by the management script

---

## File 2: .dockerignore

Create a `.dockerignore` in your project root:

```
__pycache__/
*.py[cod]
.venv/
venv/
.env
.idea/
.vscode/
.pytest_cache/
.coverage
htmlcov/
.git/
*.md
tests/
.claude/
scripts/
docker-data/
```

This keeps the Docker build context small and fast.

---

## File 3: scripts/docker.py

Create `scripts/docker.py` - a management script with colored output:

```python
#!/usr/bin/env python3
"""MCP Server Docker Manager

Usage:
    python scripts/docker.py start    # Build and start container
    python scripts/docker.py stop     # Stop container
    python scripts/docker.py restart  # Restart container (no rebuild)
    python scripts/docker.py update   # Rebuild image and restart
    python scripts/docker.py status   # Show container status
    python scripts/docker.py logs     # Tail container logs
"""

import argparse
import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Tuple


class Colors:
    """ANSI color codes for terminal output"""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"


# ============================================================================
# CONFIGURATION - Customize these for your MCP server
# ============================================================================
CONTAINER_NAME = "your-server-mcp"      # Docker container name
IMAGE_NAME = "your-server-mcp"          # Docker image name
BASE_PORT = 19000                       # Starting port for dynamic allocation
CONFIG_DIR = Path.home() / ".config" / "your_package"
STATE_FILE = CONFIG_DIR / "docker.json"
# ============================================================================


def print_header(text: str):
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{text}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}\n")


def print_success(text: str):
    print(f"{Colors.GREEN}  ✓ {text}{Colors.RESET}")


def print_warning(text: str):
    print(f"{Colors.YELLOW}  ⚠ {text}{Colors.RESET}")


def print_error(text: str):
    print(f"{Colors.RED}  ✗ {text}{Colors.RESET}")


def print_info(text: str):
    print(f"{Colors.BLUE}  → {text}{Colors.RESET}")


def run_command(cmd: list, capture: bool = True, timeout: int = None) -> Tuple[int, str, str]:
    """Run shell command and return exit code, stdout, stderr"""
    try:
        result = subprocess.run(cmd, capture_output=capture, text=True, timeout=timeout)
        return result.returncode, result.stdout if capture else "", result.stderr if capture else ""
    except subprocess.TimeoutExpired:
        return 1, "", "Command timed out"
    except Exception as e:
        return 1, "", str(e)


def is_port_available(port: int) -> bool:
    """Check if port is available"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        return result != 0
    except Exception:
        return True


def find_available_port(start_port: int = BASE_PORT) -> int:
    """Find first available port starting from start_port"""
    port = start_port
    for _ in range(100):
        if is_port_available(port):
            return port
        port += 1
    raise RuntimeError(f"No available ports in range {start_port}-{start_port+99}")


def load_state() -> dict:
    """Load persisted state"""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_state(state: dict):
    """Save state to disk"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def get_container_status() -> Tuple[bool, bool, str]:
    """Get container status: (exists, running, health)"""
    code, stdout, _ = run_command(
        ["docker", "ps", "-a", "--filter", f"name=^{CONTAINER_NAME}$", "--format", "{{.Status}}"]
    )
    if not stdout.strip():
        return False, False, "not found"

    status = stdout.strip()
    running = "Up" in status
    if "healthy" in status:
        health = "healthy"
    elif "starting" in status:
        health = "starting"
    elif running:
        health = "running"
    else:
        health = "stopped"
    return True, running, health


def check_docker_running() -> bool:
    """Check if Docker daemon is running"""
    print_info("Checking Docker daemon...")
    code, _, _ = run_command(["docker", "ps"])
    if code == 0:
        print_success("Docker daemon is running")
        return True
    print_error("Docker daemon is not running")
    print_info("Start Docker Desktop and try again")
    return False


def build_image() -> bool:
    """Build the Docker image from source code"""
    project_root = Path(__file__).parent.parent
    print_info("Building Docker image from latest code...")
    print_info(f"Project root: {project_root}")

    code, _, _ = run_command(
        ["docker", "build", "-t", IMAGE_NAME, str(project_root)],
        capture=False,
        timeout=600
    )

    if code != 0:
        print_error("Failed to build Docker image")
        return False

    print_success("Docker image built successfully")
    return True


def start_container(port: int = None) -> bool:
    """Start the container"""
    if port is None:
        port = find_available_port()

    print_info(f"Starting container on port {port}...")

    # Customize volume mounts for your server's data persistence needs
    code, _, stderr = run_command([
        "docker", "run", "-d",
        "--name", CONTAINER_NAME,
        "-p", f"{port}:3001",
        "-e", "PORT=3001",
        "-e", "LOG_LEVEL=INFO",
        # Add volume mounts for persistent data - customize these paths
        "-v", f"{CONTAINER_NAME}_data:/home/appuser/.your_package",
        "-v", f"{CONTAINER_NAME}_config:/home/appuser/.config/your_package",
        "-v", f"{CONTAINER_NAME}_logs:/home/appuser/.local/share/your_package",
        "--restart", "unless-stopped",
        IMAGE_NAME
    ])

    if code != 0:
        print_error(f"Failed to start container: {stderr}")
        return False

    save_state({"port": port})
    print_success(f"Container started on port {port}")
    return True


def stop_container() -> bool:
    """Stop and remove the container"""
    print_info("Stopping container...")
    run_command(["docker", "stop", CONTAINER_NAME])
    run_command(["docker", "rm", CONTAINER_NAME])
    print_success("Container stopped")
    return True


def verify_health(timeout_seconds: int = 60) -> bool:
    """Wait for container to become healthy"""
    print_info(f"Waiting up to {timeout_seconds}s for container to become healthy...")

    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        code, stdout, _ = run_command(
            ["docker", "inspect", "--format", "{{.State.Health.Status}}", CONTAINER_NAME]
        )
        if code == 0:
            health_status = stdout.strip()
            if health_status == "healthy":
                elapsed = int(time.time() - start_time)
                print_success(f"Container is healthy (took {elapsed}s)")
                return True
            print_info(f"Health status: {health_status}, waiting...")
        time.sleep(2)

    print_warning("Health check timeout - container may still be starting")
    print_info(f"Check logs with: docker logs {CONTAINER_NAME}")
    return False


def cmd_start():
    """Build and start the container"""
    print(f"\n{Colors.BOLD}{Colors.GREEN}MCP Server - Start{Colors.RESET}\n")

    exists, running, _ = get_container_status()
    if running:
        state = load_state()
        port = state.get("port", BASE_PORT)
        print_warning("Container already running")
        print_info(f"MCP endpoint: http://localhost:{port}/mcp")
        print_info("Use 'update' to rebuild and restart, or 'restart' to just restart")
        return

    if not check_docker_running():
        sys.exit(1)

    if exists and not running:
        print_info("Removing stopped container...")
        run_command(["docker", "rm", CONTAINER_NAME])

    print_header("Step 1: Building Image")
    if not build_image():
        sys.exit(1)

    print_header("Step 2: Starting Container")
    port = find_available_port()
    if not start_container(port):
        sys.exit(1)

    print_header("Step 3: Verifying Health")
    verify_health(timeout_seconds=60)

    print_header("Start Complete")
    print_success("MCP server is running!")
    print()
    print_info(f"MCP endpoint: http://localhost:{port}/mcp")
    print()
    print_info("Add to Claude Code:")
    print(f"  {Colors.CYAN}claude mcp add your-server --transport http http://localhost:{port}/mcp{Colors.RESET}")
    print()


def cmd_stop():
    """Stop the container"""
    print(f"\n{Colors.BOLD}{Colors.GREEN}MCP Server - Stop{Colors.RESET}\n")
    stop_container()


def cmd_restart():
    """Restart the container (without rebuild)"""
    print(f"\n{Colors.BOLD}{Colors.GREEN}MCP Server - Restart{Colors.RESET}\n")

    state = load_state()
    port = state.get("port", BASE_PORT)

    stop_container()

    print_header("Starting Container")
    if not start_container(port):
        sys.exit(1)

    print_header("Verifying Health")
    verify_health(timeout_seconds=60)

    print_header("Restart Complete")
    print_success("Container restarted successfully")
    print_info(f"MCP endpoint: http://localhost:{port}/mcp")


def cmd_update():
    """Rebuild image and restart container (for code changes)"""
    print(f"\n{Colors.BOLD}{Colors.GREEN}MCP Server - Update{Colors.RESET}")
    print("Rebuilds image from latest code and restarts container\n")

    if not check_docker_running():
        sys.exit(1)

    state = load_state()
    port = state.get("port")

    exists, running, _ = get_container_status()
    if not exists and port is None:
        print_warning("No existing deployment found")
        print_info("Running 'start' instead...")
        cmd_start()
        return

    if port is None:
        port = find_available_port()

    print_header("Step 1: Stopping Container")
    if exists:
        stop_container()
    else:
        print_info("Container not running")

    print_header("Step 2: Rebuilding Image")
    if not build_image():
        sys.exit(1)

    print_header("Step 3: Starting Container")
    if not start_container(port):
        sys.exit(1)

    print_header("Step 4: Verifying Health")
    verify_health(timeout_seconds=60)

    print_header("Update Complete")
    print_success("MCP server updated with latest code!")
    print_info(f"MCP endpoint: http://localhost:{port}/mcp")


def cmd_status():
    """Show container status"""
    print(f"\n{Colors.BOLD}{Colors.GREEN}MCP Server - Status{Colors.RESET}\n")

    exists, running, health = get_container_status()
    state = load_state()
    port = state.get("port", "unknown")

    if not exists:
        print_info("Status: not deployed")
        print_info("Run 'python scripts/docker.py start' to deploy")
    elif running:
        print_success(f"Status: {health}")
        print_info(f"Port: {port}")
        print_info(f"MCP endpoint: http://localhost:{port}/mcp")
    else:
        print_warning("Status: stopped")
        print_info("Run 'python scripts/docker.py start' to start")


def cmd_logs():
    """Tail container logs"""
    print(f"\n{Colors.BOLD}{Colors.GREEN}MCP Server - Logs{Colors.RESET}")
    print("Press Ctrl+C to stop\n")
    subprocess.run(["docker", "logs", "-f", CONTAINER_NAME])


def main():
    parser = argparse.ArgumentParser(
        description="MCP Server Docker Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  start    Build image and start container
  stop     Stop and remove container
  restart  Restart container (without rebuild)
  update   Rebuild image and restart (use after code changes)
  status   Show container status
  logs     Tail container logs
"""
    )
    parser.add_argument(
        "command",
        choices=["start", "stop", "restart", "update", "status", "logs"],
        help="Command to run"
    )

    args = parser.parse_args()

    commands = {
        "start": cmd_start,
        "stop": cmd_stop,
        "restart": cmd_restart,
        "update": cmd_update,
        "status": cmd_status,
        "logs": cmd_logs,
    }

    try:
        commands[args.command]()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Cancelled by user{Colors.RESET}")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

---

## File 4: docker-compose.yml (Optional)

For users who prefer docker-compose:

```yaml
version: '3.8'
services:
  mcp-server:
    build: .
    container_name: your-server-mcp
    ports:
      - "${MCP_PORT:-19000}:3001"
    environment:
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - PORT=3001
    volumes:
      - server_data:/home/appuser/.your_package
      - server_config:/home/appuser/.config/your_package
      - server_logs:/home/appuser/.local/share/your_package
    restart: unless-stopped

volumes:
  server_data:
  server_config:
  server_logs:
```

---

## Customization Checklist

Before using these files, customize:

1. **Dockerfile:**
   - [ ] Replace `your_package` with your actual package name
   - [ ] Adjust data directory paths in the `mkdir` command
   - [ ] Verify the CMD matches your server's CLI interface

2. **scripts/docker.py:**
   - [ ] Set `CONTAINER_NAME` (e.g., `"my-awesome-mcp"`)
   - [ ] Set `IMAGE_NAME` (usually same as container name)
   - [ ] Set `BASE_PORT` (choose a unique range, e.g., 19000, 19100, etc.)
   - [ ] Update `CONFIG_DIR` path
   - [ ] Customize volume mount paths in `start_container()`

3. **docker-compose.yml (if using):**
   - [ ] Update service and container names
   - [ ] Update volume names and paths

---

## Usage

```bash
# First time - build and start
python scripts/docker.py start

# After making code changes - rebuild and restart
python scripts/docker.py update

# Check status
python scripts/docker.py status

# View logs
python scripts/docker.py logs

# Stop
python scripts/docker.py stop

# Restart without rebuilding
python scripts/docker.py restart
```

---

## Connecting to Claude Code

After starting, add the MCP server to Claude Code:

```bash
claude mcp add your-server --transport http http://localhost:19000/mcp
```

The port will be shown in the output of `start` or `status` commands.

---

## Troubleshooting

### Server not reachable from outside container

**Symptom:** Container starts but `curl http://localhost:19000/mcp` fails or times out.

**Cause:** Server is binding to `127.0.0.1` instead of `0.0.0.0`.

**Fix:** Ensure your Dockerfile CMD includes `--host 0.0.0.0`. Check container logs:
```bash
docker logs your-server-mcp
```
Look for the line showing what address it's binding to. It should say `0.0.0.0:3001`, not `127.0.0.1:3001`.

### Port already in use

**Symptom:** Start fails with "port already in use".

**Fix:** The script automatically finds available ports. If issues persist, check what's using the port:
```bash
lsof -i :19000
```

### Health check failing

**Symptom:** Container starts but health check times out.

**Fix:** Check logs to see if server is crashing:
```bash
docker logs your-server-mcp --tail 50
```

### Data not persisting

**Symptom:** Data disappears after container restart.

**Fix:** Ensure volumes are correctly mounted. Check volume names match in both `start_container()` and Dockerfile paths. Verify volumes exist:
```bash
docker volume ls | grep your-server
```

---

## Summary

| File | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage build with uv, runs server on 0.0.0.0 |
| `.dockerignore` | Keeps image lean |
| `scripts/docker.py` | Management script (start/stop/update/status/logs) |
| `docker-compose.yml` | Optional, for compose users |

The key insight: **Always bind to `0.0.0.0`** in Docker, not `127.0.0.1`.
