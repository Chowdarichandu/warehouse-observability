"""Compose by default; isolated native Postgres fallback for Docker-free development."""

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = (
    Path("/tmp")
    / f"obs-console-{os.getuid()}-{hashlib.sha1(str(ROOT).encode()).hexdigest()[:8]}"
)
PG = Path("/usr/lib/postgresql/16/bin")
PYTHON = ROOT / ".venv/bin/python"


def run(args: list[str | Path], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run([str(a) for a in args], cwd=ROOT, check=True, **kwargs)


def environment() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("DATABASE_URL", "postgresql://obs:obs_local@127.0.0.1:55432/obs")
    return env


def database() -> None:
    RUNTIME.mkdir(mode=0o700, parents=True, exist_ok=True)
    link = ROOT / ".runtime"
    if not link.exists():
        link.symlink_to(RUNTIME, target_is_directory=True)
    data = RUNTIME / "postgres"
    if not data.exists():
        run(
            [
                PG / "initdb",
                "-D",
                data,
                "-U",
                "obs",
                "-A",
                "trust",
                "--no-locale",
                "--encoding=UTF8",
            ],
            stdout=subprocess.DEVNULL,
        )
    status = subprocess.run(
        [str(PG / "pg_ctl"), "-D", str(data), "status"], stdout=subprocess.DEVNULL
    )
    if status.returncode:
        run(
            [
                PG / "pg_ctl",
                "-D",
                data,
                "-l",
                RUNTIME / "postgres.log",
                "-o",
                f"-p 55432 -h 127.0.0.1 -k {RUNTIME}",
                "-w",
                "start",
            ]
        )
    import psycopg

    with psycopg.connect(
        "postgresql://obs@127.0.0.1:55432/postgres", autocommit=True
    ) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname='obs'").fetchone():
            conn.execute("CREATE DATABASE obs")


def owned_process(pid: int) -> bool:
    try:
        cwd = Path(f"/proc/{pid}/cwd").resolve()
        return cwd in {ROOT, ROOT / "frontend"}
    except (OSError, RuntimeError):
        return False


def spawn(name: str, args: list[str | Path], cwd: Path = ROOT) -> None:
    pidfile = RUNTIME / f"{name}.pid"
    if pidfile.exists():
        try:
            pid = int(pidfile.read_text())
            os.kill(pid, 0)
            if owned_process(pid):
                return
        except ProcessLookupError:
            pass
    with (RUNTIME / f"{name}.log").open("a") as log:
        proc = subprocess.Popen(
            [str(a) for a in args],
            cwd=cwd,
            env=environment(),
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    pidfile.write_text(str(proc.pid))


def down(reset: bool = False) -> None:
    stopped = []
    for pidfile in RUNTIME.glob("*.pid"):
        try:
            pid = int(pidfile.read_text())
            if owned_process(pid):
                os.killpg(pid, signal.SIGTERM)
                stopped.append(pid)
        except ProcessLookupError:
            pass
        pidfile.unlink(missing_ok=True)
    deadline = time.monotonic() + 10
    while any(owned_process(pid) for pid in stopped) and time.monotonic() < deadline:
        time.sleep(0.1)
    for pid in stopped:
        if owned_process(pid):
            os.killpg(pid, signal.SIGKILL)
    data = RUNTIME / "postgres"
    if data.exists():
        subprocess.run(
            [str(PG / "pg_ctl"), "-D", str(data), "-m", "fast", "-w", "stop"],
            stdout=subprocess.DEVNULL,
        )
    if reset and RUNTIME.exists():
        shutil.rmtree(RUNTIME)
        (ROOT / ".runtime").unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", choices=["up", "demo", "live", "down", "reset", "seed"]
    )
    args = parser.parse_args()
    os.chdir(ROOT)
    if not (ROOT / ".env").exists():
        shutil.copy(ROOT / ".env.example", ROOT / ".env")
    if args.action == "live":
        if not (ROOT / ".env.live").exists():
            sys.exit(
                "Copy .env.live.example to .env.live and configure the service secrets and ECR images. See docs/deployment.md."
            )
        if not shutil.which("docker"):
            sys.exit(
                "Live EC2 deployment requires Docker Compose. Use the Helm chart for EKS. See docs/deployment.md."
            )
        run(
            [
                "docker",
                "compose",
                "--env-file",
                ".env.live",
                "-f",
                "deploy/ec2/compose.yaml",
                "up",
                "-d",
                "--wait",
                "--wait-timeout",
                "240",
            ]
        )
        return
    if args.action in {"demo", "seed"}:
        os.environ["MODE"] = "demo"
        os.environ["AUTH_PROVIDER"] = "local"
    if shutil.which("docker") and os.environ.get("OBS_NATIVE") != "1":
        commands = {
            "up": ["up", "--build", "-d"],
            "demo": ["up", "--build", "-d", "--wait"],
            "down": ["down"],
            "reset": ["down", "-v"],
            "seed": ["exec", "-T", "api", "python", "-m", "obs.demo.seed"],
        }
        run(["docker", "compose", *commands[args.action]])
        if args.action == "demo":
            run(
                [
                    "docker",
                    "compose",
                    "exec",
                    "-T",
                    "api",
                    "python",
                    "-m",
                    "obs.demo.seed",
                ]
            )
            print(f"Console: http://localhost:{os.environ.get('OBS_WEB_PORT', '8080')}")
        return
    if args.action in {"down", "reset"}:
        down(args.action == "reset")
        return
    database()
    run([PYTHON, "-m", "obs.migrate"], env=environment())
    if args.action in {"demo", "seed"}:
        run([PYTHON, "-m", "obs.demo.seed"], env=environment())
    if args.action == "seed":
        return
    spawn(
        "api",
        [
            PYTHON,
            "-m",
            "uvicorn",
            "obs.api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
    )
    for _ in range(600):
        try:
            urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=1)
            break
        except Exception:
            time.sleep(0.2)
    else:
        sys.exit(f"API failed to start. See {RUNTIME / 'api.log'}")
    if args.action == "demo":
        spawn("collector", [PYTHON, "-m", "obs.collector"])
        spawn("alerter", [PYTHON, "-m", "obs.alerter"])
    spawn("web", ["npm", "run", "dev"], ROOT / "frontend")
    print(
        "Console: http://localhost:8080  |  Logs: .runtime/  |  Demo password: DEMO_PASSWORD (default demo)"
    )


if __name__ == "__main__":
    main()
