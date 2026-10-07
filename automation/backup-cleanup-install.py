#!/usr/bin/env python3
"""Install without enabling deletions; require paths verified by a prior audit."""
import argparse
from datetime import datetime
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--backup-root", type=Path, required=True)
    p.add_argument("--mountpoint", type=Path, required=True)
    p.add_argument("--docker-root", type=Path, required=True)
    p.add_argument("--timezone", required=True)
    args = p.parse_args()
    source = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("cleanup", source / "backup-cleanup.py")
    cleanup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cleanup)
    result = subprocess.run(["findmnt", "-J", "-T", str(args.backup_root),
                             "-o", "TARGET,SOURCE,FSTYPE,UUID"],
                            check=True, capture_output=True, text=True)
    filesystems = [x for x in json.loads(result.stdout)["filesystems"] if x["fstype"] != "autofs"]
    if len(filesystems) != 1 or filesystems[0]["target"] != str(args.mountpoint):
        raise SystemExit("Audited mount is missing or differs; installation refused")
    # The provided service deliberately uses the existing user's Docker root.
    if args.docker_root != Path.home() / "docker":
        raise SystemExit("Review the service's paths before using a different Docker root")
    lock = args.docker_root / "backup" / ".backup.lock"
    if not lock.is_file() or lock.is_symlink():
        raise SystemExit("Existing verified producer lock is required")
    units = [source / f"backup-cleanup.{suffix}" for suffix in ("service", "timer")]
    subprocess.run(["systemd-analyze", "--user", "verify", *map(str, units)], check=True)
    config = {"backup_root": str(args.backup_root), "filesystem": filesystems[0],
              "lock_file": str(lock), "state_dir": str(Path.home() / ".local/state/homelab-backup-cleanup"),
              "timezone": args.timezone}
    cleanup.check_mount(config)
    # Timestamped backups stay outside both Git and the producer's source tree.
    before = Path.home() / "homelab-private-audits" / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-backup-cleanup-install")
    before.mkdir(mode=0o700, parents=True)
    destination = args.docker_root / "backup"
    unit_dir = Path.home() / ".config/systemd/user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    targets = [(source / "backup-cleanup.py", destination / "backup-cleanup.py")]
    targets += [(u, unit_dir / u.name) for u in units]
    policy = destination / "backup-cleanup-policy.json"
    if policy.exists() and not policy.is_symlink():
        existing = cleanup.read_config(policy)
        if existing["backup_root"] != config["backup_root"]:
            raise SystemExit("Existing approved root differs; review policy before replacing it")
        if existing.get("protected_snapshots"):
            config["protected_snapshots"] = existing["protected_snapshots"]
    for target in [policy, *(dest for _, dest in targets)]:
        if target.is_symlink():
            raise SystemExit(f"Symlink installation target refused: {target.name}")
        if target.exists():
            shutil.copy2(target, before / target.name)
        else:
            (before / (target.name + ".absent")).write_text("Absent before installation\n")
    policy.write_text(json.dumps(config, indent=2) + "\n")
    policy.chmod(0o600)
    for src, dest in targets:
        shutil.copyfile(src, dest)
        dest.chmod(0o600)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    print("Installed. Timer remains disabled until the dry-run has been reviewed.")
    print("Use python3 <installed-script> --dry-run --verbose --plan-output <private-plan>.")
    print("After verification: systemctl --user enable --now backup-cleanup.timer")
    print("First run: python3 <installed-script> --execute --apply-plan <private-plan>")
    print("Requires loginctl Linger=yes for boot execution without an active login.")


if __name__ == "__main__":
    main()
