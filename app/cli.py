"""Command-line entrypoint for serve, install, and uninstall."""

from __future__ import annotations

import argparse
import getpass
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from app.config import DATA_DIR, LOG_DIR, ensure_data_dir, ensure_state_dirs

SERVICE_NAME = "wormhole-auto-config"
LAUNCH_LABEL = "com.wormhole.auto-config"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8080


def _log(message: str) -> None:
    """Print a CLI status line to stdout."""
    print(f"[wormhole-auto-config] {message}")


def _die(message: str, code: int = 1) -> None:
    """Print an error and exit the process."""
    print(f"[wormhole-auto-config] ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def resolve_cli_path() -> Path:
    """
    Resolve the installed wormhole-auto-config console script path.

    Prefers the script next to the current interpreter so autostart units
    keep using the same virtualenv or install prefix.
    """
    bin_dir = Path(sys.executable).resolve().parent
    candidate = bin_dir / SERVICE_NAME
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return candidate
    which = shutil.which(SERVICE_NAME)
    if which:
        return Path(which).resolve()
    _die(
        f"console script '{SERVICE_NAME}' not found next to "
        f"{sys.executable}; reinstall the package in this environment"
    )


def cmd_serve(host: str, port: int) -> None:
    """Run the FastAPI service in the foreground via uvicorn."""
    ensure_data_dir()
    ensure_state_dirs()
    import uvicorn

    uvicorn.run("app.main:app", host=host, port=port, factory=False)


def _write_macos_plist(cli_path: Path, host: str, port: int) -> Path:
    """Write and return the LaunchAgent plist path."""
    plist_dir = Path.home() / "Library" / "LaunchAgents"
    plist_path = plist_dir / f"{LAUNCH_LABEL}.plist"
    log_out = LOG_DIR / "service.out.log"
    log_err = LOG_DIR / "service.err.log"
    plist_dir.mkdir(parents=True, exist_ok=True)

    plist_path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{LAUNCH_LABEL}</string>
  <key>WorkingDirectory</key>
  <string>{LOG_DIR}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{cli_path}</string>
    <string>serve</string>
    <string>--host</string>
    <string>{host}</string>
    <string>--port</string>
    <string>{port}</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>{log_out}</string>
  <key>StandardErrorPath</key>
  <string>{log_err}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/usr/local/bin:/usr/bin:/bin:{cli_path.parent}</string>
  </dict>
</dict>
</plist>
""",
        encoding="utf-8",
    )
    return plist_path


def _install_macos(cli_path: Path, host: str, port: int) -> None:
    """Register and start the macOS LaunchAgent."""
    plist_path = _write_macos_plist(cli_path, host, port)
    domain = f"gui/{os.getuid()}"
    if subprocess.run(
        ["launchctl", "print", f"{domain}/{LAUNCH_LABEL}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0:
        _log("Unloading existing LaunchAgent")
        subprocess.run(
            ["launchctl", "bootout", domain, str(plist_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )

    _log(f"Loading LaunchAgent: {plist_path}")
    subprocess.run(
        ["launchctl", "bootstrap", domain, str(plist_path)],
        check=True,
    )
    subprocess.run(
        ["launchctl", "enable", f"{domain}/{LAUNCH_LABEL}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    _log(f"macOS login autostart enabled ({LAUNCH_LABEL})")


def _uninstall_macos() -> None:
    """Stop and remove the macOS LaunchAgent."""
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_LABEL}.plist"
    domain = f"gui/{os.getuid()}"
    if subprocess.run(
        ["launchctl", "print", f"{domain}/{LAUNCH_LABEL}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0:
        _log(f"Stopping LaunchAgent {LAUNCH_LABEL}")
        subprocess.run(
            ["launchctl", "bootout", domain, str(plist_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        subprocess.run(
            ["launchctl", "bootout", f"{domain}/{LAUNCH_LABEL}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    if plist_path.is_file():
        plist_path.unlink()
        _log(f"Removed {plist_path}")
    else:
        _log("LaunchAgent plist not found (already removed)")


def _write_linux_unit(cli_path: Path, host: str, port: int) -> Path:
    """Write and return the systemd user unit path."""
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_path = unit_dir / f"{SERVICE_NAME}.service"
    log_out = LOG_DIR / "service.out.log"
    log_err = LOG_DIR / "service.err.log"
    unit_dir.mkdir(parents=True, exist_ok=True)
    unit_path.write_text(
        f"""[Unit]
Description=Wormhole Auto-Config Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={LOG_DIR}
ExecStart={cli_path} serve --host {host} --port {port}
Restart=always
RestartSec=3
StandardOutput=append:{log_out}
StandardError=append:{log_err}

[Install]
WantedBy=default.target
""",
        encoding="utf-8",
    )
    return unit_path


def _linux_linger_enabled(user: str) -> bool:
    """Return True when systemd lingering is on for the given user."""
    result = subprocess.run(
        ["loginctl", "show-user", user, "--property=Linger"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and "Linger=yes" in result.stdout


def _enable_linux_linger() -> None:
    """
    Enable systemd lingering so the user service starts at boot.

    Without lingering, systemd --user (and this service) only start after an
    interactive login, and they stop shortly after the last session ends.
    """
    user = getpass.getuser()
    if _linux_linger_enabled(user):
        _log(f"systemd lingering already enabled for {user}")
        return
    result = subprocess.run(
        ["loginctl", "enable-linger", user],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0 and _linux_linger_enabled(user):
        _log(f"Enabled systemd lingering for {user} (boot without login)")
        return
    detail = (result.stderr or result.stdout or "").strip()
    _log(
        "WARNING: lingering is not enabled; the service will not start at boot "
        f"until {user} logs in. Run: loginctl enable-linger {user}"
    )
    if detail:
        _log(detail)


def _install_linux(cli_path: Path, host: str, port: int) -> None:
    """Register and start the systemd user service."""
    unit_path = _write_linux_unit(cli_path, host, port)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(
        ["systemctl", "--user", "enable", "--now", f"{SERVICE_NAME}.service"],
        check=True,
    )
    _log(f"Linux systemd user service enabled ({SERVICE_NAME})")
    _log(f"Unit written: {unit_path}")
    _enable_linux_linger()


def _uninstall_linux() -> None:
    """Stop and remove the systemd user service."""
    unit_path = Path.home() / ".config" / "systemd" / "user" / f"{SERVICE_NAME}.service"
    subprocess.run(
        ["systemctl", "--user", "disable", "--now", f"{SERVICE_NAME}.service"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if unit_path.is_file():
        unit_path.unlink()
        subprocess.run(
            ["systemctl", "--user", "daemon-reload"],
            check=False,
        )
        _log(f"Removed {unit_path}")
    else:
        _log("systemd unit not found (already removed)")


def cmd_install(host: str, port: int) -> None:
    """Install login/boot autostart and start the service."""
    ensure_data_dir()
    ensure_state_dirs()
    cli_path = resolve_cli_path()
    system = platform.system()
    if system == "Darwin":
        _install_macos(cli_path, host, port)
    elif system == "Linux":
        _install_linux(cli_path, host, port)
    else:
        _die(f"Unsupported OS: {system}. Supported: macOS, Linux")

    _log("Install complete")
    _log(f"UI: http://127.0.0.1:{port}")
    _log(f"Logs: {LOG_DIR}/")
    _log(f"Uninstall: {SERVICE_NAME} uninstall")


def cmd_uninstall() -> None:
    """Remove login/boot autostart; keep data and logs."""
    system = platform.system()
    if system == "Darwin":
        _uninstall_macos()
    elif system == "Linux":
        _uninstall_linux()
    else:
        _die(f"Unsupported OS: {system}. Supported: macOS, Linux")
    _log("Autostart removed. Config and logs were kept.")
    _log(f"Config: {DATA_DIR}")
    _log(f"Logs: {LOG_DIR}")


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog=SERVICE_NAME,
        description="Wormhole Auto-Config service CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    serve_p = sub.add_parser("serve", help="Run the service in the foreground")
    serve_p.add_argument("--host", default=DEFAULT_HOST)
    serve_p.add_argument("--port", type=int, default=DEFAULT_PORT)

    install_p = sub.add_parser(
        "install",
        help="Register login/boot autostart and start the service",
    )
    install_p.add_argument("--host", default=DEFAULT_HOST)
    install_p.add_argument("--port", type=int, default=DEFAULT_PORT)

    sub.add_parser("uninstall", help="Remove login/boot autostart")
    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint used by the console_scripts wrapper."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "serve":
        cmd_serve(args.host, args.port)
    elif args.command == "install":
        cmd_install(args.host, args.port)
    elif args.command == "uninstall":
        cmd_uninstall()
    else:
        parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
