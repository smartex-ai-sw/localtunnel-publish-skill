#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "psutil>=5.9.0",
# ]
# ///
"""
HTTP Basic Auth static file server on 127.0.0.1 for pairing with a tunnel (e.g. localtunnel).

Password: read from --pass-file; if missing, a random password is created (chmod 0o600 when supported).

Run ``uv run`` on this file to auto-install psutil (PEP 723). ``python3`` works without it, using
stdlib fallbacks for cleanup (weaker on macOS/Windows).

Full workflow (tunnel, curl checks, share text): ``--show-guide``
"""
from __future__ import annotations

import argparse
import base64
import os
import re
import secrets
import signal
import string
import subprocess
import sys
import textwrap
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_AUTH_USER = "preview"
DEFAULT_PASS_FILE = Path(".local/preview-auth.pass")
DEFAULT_PORT = 8765


def publish_guide_text() -> str:
    u = DEFAULT_AUTH_USER
    pf = DEFAULT_PASS_FILE
    port = DEFAULT_PORT
    return textwrap.dedent(
        f"""
        =========================================================================
        Publish preview: this server + localtunnel (no vendor lock-in beyond npm)
        =========================================================================

        This process only serves files on 127.0.0.1. Expose it with a tunnel CLI.

        Defaults (override with flags):
          Basic Auth user:     {u}
          Password file:       {pf}
          Listen port:         {port}

        1) Install uv (optional, recommended for reliable cleanup via psutil)
           macOS/Linux:  curl -LsSf https://astral.sh/uv/install.sh | sh
           Windows:      irm https://astral.sh/uv/install.ps1 | iex
           Docs:         https://docs.astral.sh/uv/getting-started/installation/

        2) Start this server (from the directory where you want {pf} to live, or pass --pass-file):
             uv run serve_basic_auth.py --root /path/to/site --port {port} --user YOUR_USER
           Fallback without uv:
             python3 serve_basic_auth.py --root /path/to/site --port {port}

           Use a --root that contains all assets (e.g. if HTML fetches ../data/, serve the parent).

        3) In another terminal, start localtunnel:
             npx -y localtunnel --port {port}
           Copy the printed https://....loca.lt URL. Append a path if the entry page is not /.

        4) Verify locally (loopback, no tunnel header needed):
             PASS=$(tr -d '\\n' < {pf})
             curl -sS -o /dev/null -w "%{{http_code}}\\n" -u "{u}:$PASS" http://127.0.0.1:{port}/

        5) Verify through the tunnel (skips loca.lt interstitial for scripts):
             curl -sS -o /dev/null -w "%{{http_code}}\\n" \\
               -H "Bypass-Tunnel-Reminder: 1" \\
               -u "{u}:$PASS" "https://YOUR-SUBDOMAIN.loca.lt/your-path"

        6) Share (plain text for chat). Do not post passwords in public channels if policy forbids it.

             Preview (temporary)
             URL: https://YOUR-SUBDOMAIN.loca.lt/your-path
             Login: {u} / <password from {pf}>

             If the site asks you to continue (loca.lt), tap once, then enter the login.

           Technical recipients (optional second message):
             curl: add header Bypass-Tunnel-Reminder: 1

        Git: add {pf} to .gitignore; never commit the password file.

        Cleanup: on start, unless --no-cleanup, this script stops prior localtunnel forwarding the
        same port, other instances of this script with the same --root, then frees the TCP port.

        ThreadingHTTPServer avoids stalls when the tunnel opens multiple connections.

        Automation note: some agent/sandbox runners SIGTERM long-running children. For background
        servers started from automation, prefer python3 on this script; use uv run in your own terminal.

        =========================================================================
        """
    ).strip()


def _get_psutil():
    try:
        import psutil  # type: ignore

        return psutil
    except ImportError:
        return None


def _subprocess_kwargs() -> dict:
    kw: dict = {"capture_output": True, "timeout": 60, "check": False, "text": True}
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kw["startupinfo"] = si
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kw


def _read_proc_cmdline_linux(pid: int) -> list[str]:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return []
    parts = raw.split(b"\0")
    out: list[str] = []
    for p in parts:
        if not p:
            continue
        out.append(p.decode("utf-8", errors="replace"))
    return out


def _iter_process_cmdlines_psutil(psutil) -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            info = proc.info
            pid = info.get("pid")
            cl = info.get("cmdline") or []
            if pid is None:
                continue
            rows.append((int(pid), " ".join(cl)))
        except (psutil.Error, TypeError, ValueError):
            continue
    return rows


def _iter_process_cmdlines_ps_unix() -> list[tuple[int, str]]:
    for args in (
        ["ps", "-e", "-ww", "-o", "pid=", "-o", "args="],
        ["ps", "-ax", "-ww", "-o", "pid=", "-o", "args="],
        ["ps", "-e", "-ww", "-o", "pid=", "-o", "command="],
    ):
        try:
            r = subprocess.run(args, **_subprocess_kwargs())
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        if r.returncode != 0 or not r.stdout:
            continue
        rows: list[tuple[int, str]] = []
        for line in r.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 1)
            if len(parts) < 2:
                continue
            pid_s, cmd = parts[0], parts[1]
            if not pid_s.isdigit():
                continue
            rows.append((int(pid_s), cmd))
        if rows:
            return rows
    return []


def _iter_process_cmdlines_procfs() -> list[tuple[int, str]]:
    proc = Path("/proc")
    if not proc.is_dir():
        return []
    rows: list[tuple[int, str]] = []
    for sub in proc.iterdir():
        if not sub.name.isdigit():
            continue
        argv = _read_proc_cmdline_linux(int(sub.name))
        if argv:
            rows.append((int(sub.name), " ".join(argv)))
    return rows


def _iter_process_cmdlines_windows() -> list[tuple[int, str]]:
    script = (
        "Get-CimInstance Win32_Process | ForEach-Object { "
        "$id = [string]$_.ProcessId; "
        "$cl = $_.CommandLine; "
        "if ($null -eq $cl) { $cl = '' }; "
        "Write-Output ($id + [char]9 + $cl) }"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            **_subprocess_kwargs(),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if r.returncode != 0 or not r.stdout:
        return []
    rows: list[tuple[int, str]] = []
    for line in r.stdout.splitlines():
        if "\t" not in line:
            continue
        pid_s, cmd = line.split("\t", 1)
        pid_s = pid_s.strip()
        if pid_s.isdigit():
            rows.append((int(pid_s), cmd))
    return rows


def iter_process_cmdlines() -> list[tuple[int, str]]:
    psutil = _get_psutil()
    if psutil is not None:
        return _iter_process_cmdlines_psutil(psutil)
    if sys.platform == "win32":
        return _iter_process_cmdlines_windows()
    if sys.platform.startswith("linux"):
        rows = _iter_process_cmdlines_procfs()
        if rows:
            return rows
    return _iter_process_cmdlines_ps_unix()


def _argv_get(argv: list[str], long_opt: str, short_opt: str | None) -> str | None:
    for i, a in enumerate(argv):
        if a == long_opt and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith(long_opt + "="):
            return a.split("=", 1)[1]
        if short_opt and a == short_opt and i + 1 < len(argv):
            return argv[i + 1]
    return None


def _pids_same_serve_root(serve_root: Path, my_pid: int) -> list[int]:
    want = str(serve_root.resolve())
    found: list[int] = []
    for pid, cmd in iter_process_cmdlines():
        if pid == my_pid:
            continue
        if "serve_basic_auth.py" not in cmd:
            continue
        argv = cmd.split()
        root_arg = _argv_get(argv, "--root", None)
        if root_arg is None:
            continue
        try:
            if str(Path(root_arg).resolve()) == want:
                found.append(pid)
        except OSError:
            continue
    return found


def _localtunnel_cmdline_targets_port(cmd: str, port: int) -> bool:
    low = cmd.replace("\\", "/")
    if (
        "localtunnel" not in low
        and "lt.js" not in low
        and "bin/lt" not in low
        and "/lt " not in low
    ):
        return False
    for m in re.finditer(r"(?:--port|-p)\s*=?\s*(\d+)", cmd):
        try:
            if int(m.group(1)) == int(port):
                return True
        except ValueError:
            continue
    return False


def _pids_localtunnel_forwarding_port(port: int, my_pid: int) -> list[int]:
    found: list[int] = []
    for pid, cmd in iter_process_cmdlines():
        if pid == my_pid:
            continue
        if _localtunnel_cmdline_targets_port(cmd, port):
            found.append(pid)
    return found


def _terminate_pids(pids: list[int]) -> None:
    unique = [p for p in dict.fromkeys(pids) if p != os.getpid()]
    if not unique:
        return
    if sys.platform == "win32":
        for pid in unique:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T"],
                **_subprocess_kwargs(),
            )
        time.sleep(0.45)
        for pid in unique:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                **_subprocess_kwargs(),
            )
    else:
        for pid in unique:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except PermissionError:
                pass
        time.sleep(0.45)
        for pid in unique:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                pass


def _pids_listening_on_port_psutil(psutil, port: int, my_pid: int) -> list[int]:
    pids: list[int] = []
    try:
        for c in psutil.net_connections(kind="inet"):
            if c.pid is None or c.pid == my_pid:
                continue
            if c.status != getattr(psutil, "CONN_LISTEN", "LISTEN"):
                continue
            if c.laddr is None:
                continue
            if int(c.laddr.port) != int(port):
                continue
            lip = str(c.laddr.ip)
            if lip in ("127.0.0.1", "0.0.0.0", "::", "::1"):
                pids.append(int(c.pid))
    except psutil.Error:
        pass
    return list(dict.fromkeys(pids))


def _pids_listening_on_port_lsof(port: int) -> list[int]:
    pids: list[int] = []
    for args in (
        ["lsof", "-nP", "-iTCP", f":{int(port)}", "-sTCP:LISTEN", "-t"],
        ["lsof", "-ti", f"tcp:{int(port)}"],
    ):
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=15, check=False)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        if r.returncode != 0 or not r.stdout.strip():
            continue
        for line in r.stdout.strip().split():
            if line.isdigit():
                pids.append(int(line))
        if pids:
            break
    return list(dict.fromkeys(pids))


def _pids_listening_on_port_netstat_windows(port: int) -> list[int]:
    pids: list[int] = []
    try:
        r = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            **_subprocess_kwargs(),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return pids
    if r.returncode != 0 or not r.stdout:
        return pids
    needle = f":{int(port)}"
    for line in r.stdout.splitlines():
        if "LISTENING" not in line.upper():
            continue
        if needle not in line:
            continue
        parts = line.split()
        if not parts:
            continue
        last = parts[-1]
        if last.isdigit():
            pids.append(int(last))
    return list(dict.fromkeys(pids))


def _kill_tcp_listeners_on_port(port: int, my_pid: int) -> None:
    psutil = _get_psutil()
    pids: list[int] = []
    if psutil is not None:
        pids = _pids_listening_on_port_psutil(psutil, port, my_pid)
    if not pids and sys.platform != "win32":
        try:
            subprocess.run(
                ["fuser", "-k", f"{int(port)}/tcp"],
                capture_output=True,
                check=False,
                timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        pids = _pids_listening_on_port_lsof(port)
    if not pids and sys.platform == "win32":
        pids = _pids_listening_on_port_netstat_windows(port)
    pids = [p for p in dict.fromkeys(pids) if p != my_pid]
    if pids:
        _terminate_pids(pids)


def cleanup_prior_preview_instances(*, serve_root: Path, port: int, my_pid: int) -> None:
    lt_pids = _pids_localtunnel_forwarding_port(port, my_pid)
    srv_pids = _pids_same_serve_root(serve_root, my_pid)
    combined = list(dict.fromkeys(lt_pids + srv_pids))
    if combined:
        _terminate_pids(combined)
    time.sleep(0.15)
    _kill_tcp_listeners_on_port(port, my_pid)
    time.sleep(0.1)


def _generate_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _read_or_create_password(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        pw = path.read_text(encoding="utf-8").strip()
        if len(pw) < 8:
            raise SystemExit(f"Password in {path} is too short (min 8 chars). Remove file to regenerate.")
        return pw
    pw = _generate_password()
    path.write_text(pw + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return pw


class AuthStaticHandler(SimpleHTTPRequestHandler):
    directory: str
    auth_user: str
    auth_pass: str

    def __init__(self, *args, directory: str, auth_user: str, auth_pass: str, **kwargs):
        self.directory = directory
        self.auth_user = auth_user
        self.auth_pass = auth_pass
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, fmt, *args):
        if args and str(args[0]).startswith("GET /favicon"):
            return
        super().log_message(fmt, *args)

    def do_GET(self):
        if not self._authorized():
            self._send_401()
            return
        super().do_GET()

    def do_HEAD(self):
        if not self._authorized():
            self._send_401()
            return
        super().do_HEAD()

    def _send_401(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Protected"')
        self.end_headers()

    def _authorized(self) -> bool:
        auth = self.headers.get("Authorization")
        if not auth or not auth.startswith("Basic "):
            return False
        try:
            raw = base64.b64decode(auth.split(" ", 1)[1]).decode("utf-8")
            u, _, p = raw.partition(":")
            return u == self.auth_user and p == self.auth_pass
        except (ValueError, UnicodeDecodeError):
            return False


def _handler_factory(root: str, user: str, password: str):
    def _make(request, client_address, server):
        return AuthStaticHandler(
            request, client_address, server, directory=root, auth_user=user, auth_pass=password
        )

    return _make


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Static HTTP server with Basic Auth on 127.0.0.1 (pair with a tunnel CLI).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Full workflow:  %(prog)s --show-guide",
    )
    parser.add_argument(
        "--show-guide",
        action="store_true",
        help="Print tunnel + curl + share instructions, then exit",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Directory to serve (default: current working directory)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Listen port (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--user",
        default=DEFAULT_AUTH_USER,
        help=f"Basic Auth username (default: {DEFAULT_AUTH_USER})",
    )
    parser.add_argument(
        "--pass-file",
        type=Path,
        default=DEFAULT_PASS_FILE,
        help=f"Password file; created with random password if missing (default: {DEFAULT_PASS_FILE})",
    )
    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Do not stop prior localtunnel or other serve_basic_auth for this root/port",
    )
    args = parser.parse_args()

    if args.show_guide:
        print(publish_guide_text())
        return

    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"Not a directory: {root}")

    if not args.no_cleanup:
        cleanup_prior_preview_instances(serve_root=root, port=args.port, my_pid=os.getpid())

    password = _read_or_create_password(args.pass_file.resolve())
    handler = _handler_factory(str(root), args.user, password)
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    pf = args.pass_file.resolve()
    print(
        f"Serving {root} at http://127.0.0.1:{args.port}/  user={args.user}  pass-file={pf}",
        flush=True,
    )
    print(
        f"Tunnel (other terminal): npx -y localtunnel --port {args.port}",
        flush=True,
    )
    print("Full steps: same script --show-guide", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
