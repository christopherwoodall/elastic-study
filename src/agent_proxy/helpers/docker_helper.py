#!/usr/bin/env python3
"""
docker-helper — docker-compose helper (services discovered dynamically)
Usage: docker_helper [command] [service]
"""

import shutil
import subprocess
import sys

COMPOSE_FILE = "docker-compose.yaml"


def discover_services() -> list[str]:
    """Ask Docker to enumerate services — handles overrides, env vars, includes."""
    result = subprocess.run(
        ["docker", "compose", "-f", COMPOSE_FILE, "config", "--services"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # Compose file missing or docker not available yet — return empty, fail later
        return []
    return [s for s in result.stdout.strip().splitlines() if s]


SERVICES: list[str] = discover_services()

# ANSI colors
G = "\033[92m"  # green
R = "\033[91m"  # red
Y = "\033[93m"  # yellow
B = "\033[94m"  # blue
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


def run(cmd: list[str], capture=False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=capture, text=True)


def compose(*args):
    base = ["docker", "compose", "-f", COMPOSE_FILE]
    return run(base + list(args))


def compose_out(*args) -> str:
    base = ["docker", "compose", "-f", COMPOSE_FILE]
    result = run(base + list(args), capture=True)
    return result.stdout.strip()


def get_status() -> dict[str, dict]:
    """Returns {service: {running: bool, id: str, ports: str}}"""
    raw = compose_out("ps", "--format", "json")
    if not raw:
        return {s: {"running": False, "id": "", "ports": ""} for s in SERVICES}

    import json

    known = set(SERVICES)
    status = {s: {"running": False, "id": "", "ports": ""} for s in SERVICES}

    # docker compose ps --format json outputs one JSON object per line
    for line in raw.splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = obj.get("Service", "")
        if name in known:
            state = obj.get("State", "").lower()
            status[name] = {
                "running": state == "running",
                "id": obj.get("ID", "")[:12],
                "ports": obj.get("Publishers", ""),
            }
    return status


def fmt_ports(publishers) -> str:
    if not publishers or not isinstance(publishers, list):
        return ""
    parts = []
    for p in publishers:
        pub = p.get("PublishedPort", 0)
        tgt = p.get("TargetPort", 0)
        proto = p.get("Protocol", "tcp")
        if pub:
            parts.append(f"{pub}→{tgt}/{proto}")
    return ", ".join(parts)


def cmd_status():
    status = get_status()
    print(f"\n{BOLD}Stack: {COMPOSE_FILE}{RESET}")
    print(f"{'Service':<20} {'State':<12} {'ID':<14} {'Ports'}")
    print("─" * 60)
    for svc, info in status.items():
        state_str = f"{G}running{RESET}" if info["running"] else f"{DIM}stopped{RESET}"
        ports = fmt_ports(info["ports"]) if isinstance(info["ports"], list) else ""
        print(f"{svc:<20} {state_str:<20} {info['id']:<14} {ports}")
    print()


def cmd_start(service=None):
    if service:
        _validate_service(service)
        print(f"{Y}Starting {service}...{RESET}")
        compose("up", "-d", service)
    else:
        print(f"{Y}Starting all services...{RESET}")
        compose("up", "-d")
    cmd_status()


def cmd_stop(service=None):
    if service:
        _validate_service(service)
        print(f"{Y}Stopping {service}...{RESET}")
        compose("stop", service)
    else:
        print(f"{Y}Stopping all services...{RESET}")
        compose("stop")
    cmd_status()


def cmd_restart(service=None):
    if service:
        _validate_service(service)
        print(f"{Y}Restarting {service}...{RESET}")
        compose("restart", service)
    else:
        print(f"{Y}Restarting all services...{RESET}")
        compose("restart")
    cmd_status()


def cmd_down():
    print(f"{R}Taking down stack (containers + network)...{RESET}")
    compose("down")


def cmd_logs(service=None):
    args = ["logs", "--tail=100", "-f"]
    if service:
        _validate_service(service)
        args.append(service)
    compose(*args)


def cmd_attach(service):
    _validate_service(service)
    status = get_status()
    if not status[service]["running"]:
        print(f"{R}{service} is not running.{RESET}")
        sys.exit(1)
    container = f"{service}"  # container_name matches service name in this compose
    print(f"{Y}Attaching shell to {service}...{RESET}")
    run(["docker", "exec", "-it", container, "/bin/bash"])


def cmd_pull():
    print(f"{Y}Pulling latest images...{RESET}")
    compose("pull")


def _validate_service(service):
    if service not in SERVICES:
        print(f"{R}Unknown service '{service}'. Valid: {', '.join(SERVICES)}{RESET}")
        sys.exit(1)


COMMANDS = {
    "status": (cmd_status, "Show container states"),
    "start": (cmd_start, "Start all or [service]"),
    "stop": (cmd_stop, "Stop all or [service]"),
    "restart": (cmd_restart, "Restart all or [service]"),
    "down": (cmd_down, "Stop and remove containers + network"),
    "logs": (cmd_logs, "Tail logs for all or [service]"),
    "attach": (cmd_attach, "Shell into <service>"),
    "pull": (cmd_pull, "Pull latest images"),
}


def usage():
    svc_str = (
        ", ".join(SERVICES)
        if SERVICES
        else f"{R}(none found — is {COMPOSE_FILE} present?){RESET}"
    )
    print(f"\n{BOLD}docker-helper — compose helper{RESET}")
    print(f"Services: {svc_str}\n")
    print(f"{'Command':<12} {'Args':<20} Description")
    print("─" * 55)
    rows = [
        ("status", "", "Show container states"),
        ("start", "[service]", "Start all or specific service"),
        ("stop", "[service]", "Stop all or specific service"),
        ("restart", "[service]", "Restart all or specific service"),
        ("down", "", "Stop + remove containers/network"),
        ("logs", "[service]", "Tail logs (Ctrl-C to exit)"),
        ("attach", "<service>", "Interactive shell into container"),
        ("pull", "", "Pull latest images"),
    ]
    for cmd, args, desc in rows:
        print(f"  {B}{cmd:<10}{RESET} {DIM}{args:<18}{RESET} {desc}")
    print()


def main():
    if not shutil.which("docker"):
        print(f"{R}docker not found in PATH{RESET}")
        sys.exit(1)

    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help", "help"):
        usage()
        return

    cmd = args[0]
    service = args[1] if len(args) > 1 else None

    if cmd not in COMMANDS:
        print(f"{R}Unknown command '{cmd}'{RESET}")
        usage()
        sys.exit(1)

    fn, _ = COMMANDS[cmd]

    # Commands that require a service arg
    if cmd == "attach":
        if not service:
            print(f"{R}attach requires a service name: {', '.join(SERVICES)}{RESET}")
            sys.exit(1)
        fn(service)
    elif cmd in ("start", "stop", "restart", "logs"):
        fn(service)
    else:
        fn()


if __name__ == "__main__":
    main()
