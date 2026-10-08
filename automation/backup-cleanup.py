#!/usr/bin/env python3
"""Conservative retention for explicitly approved, complete homelab snapshots.

No application-state discovery, extraction, shell deletion or Docker operations.
All destructive operations use pinned directory descriptors and exact filenames.
"""

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from zoneinfo import ZoneInfo

BASE_FILES = frozenset({
    "docker-configs.tar.gz", "jellyfin-critical.tar.gz",
    "volume-adguard-home_adguard-config.tar.gz",
    "volume-adguard-home_adguard-work.tar.gz", "volume-portainer_data.tar.gz",
    "volume-uptime-kuma_uptime-kuma-data.tar.gz", "CONTENTS.txt",
    "docker-inspect.json", "docker-images.txt", "docker-volumes.txt",
})
MARKER = ".cleanup-disposable.json"
SNAPSHOT = re.compile(r"20\d\d-\d\d-\d\dT\d{6}\Z")
NOFOLLOW = os.O_NOFOLLOW | os.O_CLOEXEC


class Unsafe(Exception):
    pass


def signature(st):
    return (st.st_dev, st.st_ino, st.st_mode, st.st_nlink, st.st_size,
            st.st_mtime_ns, st.st_ctime_ns)


@contextmanager
def directory(path):
    """Reject symlinks in every component, including approved-root ancestors."""
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise Unsafe("Directory must be an absolute path without traversal")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | NOFOLLOW)
    try:
        for part in path.parts[1:]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        yield fd
    finally:
        os.close(fd)


def read_file(fd, name, digest=False, max_bytes=None):
    if Path(name).name != name or name in {".", ".."}:
        raise Unsafe("Non-local filename")
    # NONBLOCK prevents a forged FIFO/device from hanging before fstat rejects it.
    f = os.open(name, os.O_RDONLY | os.O_NONBLOCK | NOFOLLOW, dir_fd=fd)
    try:
        before = os.fstat(f)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise Unsafe(f"Not a single-link regular file: {name}")
        if max_bytes is not None and before.st_size > max_bytes:
            raise Unsafe(f"Oversized metadata: {name}")
        h = hashlib.sha256() if digest else None
        parts = []
        while True:
            data = os.read(f, 1024 * 1024)
            if not data:
                break
            if h:
                h.update(data)
            else:
                parts.append(data)
        if signature(before) != signature(os.fstat(f)):
            raise Unsafe(f"Changed during verification: {name}")
        return (h.hexdigest() if h else b"".join(parts)), signature(before)
    finally:
        os.close(f)


def parse_manifest(data, expected):
    result = {}
    for line in data.decode("utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64}) [ *](.+)", line)
        if not match:
            raise Unsafe("Invalid checksum manifest")
        name = match[2]
        if name.startswith("./"):
            name = name[2:]
        if name not in expected or name in result:
            raise Unsafe("Unexpected, duplicate or unsafe manifest filename")
        result[name] = match[1]
    if set(result) != set(expected):
        raise Unsafe("Incomplete checksum manifest")
    return result


def services_from_inspect(data):
    records = json.loads(data)
    if not isinstance(records, list) or not records:
        raise Unsafe("Missing service inventory")
    names = set()
    for record in records:
        name = record.get("Name", "").removeprefix("/")
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", name):
            raise Unsafe("Invalid service inventory")
        names.add(name)
    return sorted(names)


def binding_versions(data):
    """A changed mount must never supersede the old mount's last restore set.

    Hash stored metadata only; never inspect the actual bind/volume source.
    This also protects a service's old data when a later configuration moves
    its state outside the producer's audited source tree.
    """
    result = {}
    for record in json.loads(data):
        mounts = [{key: m.get(key) for key in ("Type", "Source", "Destination", "RW")}
                  for m in record.get("Mounts", [])]
        encoded = json.dumps(sorted(mounts, key=lambda m: json.dumps(m, sort_keys=True)),
                             sort_keys=True).encode()
        result[record["Name"].removeprefix("/")] = hashlib.sha256(encoded).hexdigest()
    return result


def marker_services(data):
    marker = json.loads(data)
    if (marker.get("protocol") != "homelab-full-v1"
            or marker.get("disposable") is not True):
        raise Unsafe("Unrecognized disposable-artifact marker")
    names = marker.get("services")
    if not isinstance(names, list) or not names or any(
        not isinstance(n, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", n)
        for n in names
    ):
        raise Unsafe("Invalid disposable-artifact service inventory")
    return sorted(set(names))


def verify_snapshot(rootfd, name, zone):
    stamp = datetime.strptime(name, "%Y-%m-%dT%H%M%S").replace(tzinfo=zone)
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | NOFOLLOW, dir_fd=rootfd)
    try:
        ds = signature(os.fstat(fd))
        files = set(os.listdir(fd))
        expected = BASE_FILES | ({MARKER} if MARKER in files else set())
        if files != expected | {"SHA256SUMS"}:
            raise Unsafe("Unknown/missing files or nested directories")
        raw, sig = read_file(fd, "SHA256SUMS", max_bytes=16384)
        hashes = parse_manifest(raw, expected)
        identities = {"SHA256SUMS": sig}
        allocated = logical = 0
        for filename in sorted(expected):
            value, sig = read_file(fd, filename, digest=True)
            if value != hashes[filename]:
                raise Unsafe(f"Checksum mismatch: {filename}")
            if sig[4] == 0:
                raise Unsafe(f"Empty snapshot component: {filename}")
            identities[filename] = sig
        inventory, _ = read_file(fd, "docker-inspect.json", max_bytes=16 * 1024 * 1024)
        services = services_from_inspect(inventory)
        if MARKER in expected:
            marker, _ = read_file(fd, MARKER, max_bytes=16384)
            if marker_services(marker) != services:
                raise Unsafe("Snapshot and marker service inventories differ")
            if "bindings" in json.loads(marker) and json.loads(marker)["bindings"] != binding_versions(inventory):
                raise Unsafe("Service mounts changed during backup; preserve uncertain snapshot")
        for filename, sig in identities.items():
            st = os.stat(filename, dir_fd=fd, follow_symlinks=False)
            if signature(st) != sig:
                raise Unsafe("Snapshot changed during verification")
            allocated += st.st_blocks * 512
            logical += st.st_size
        if signature(os.fstat(fd)) != ds or set(os.listdir(fd)) != files:
            raise Unsafe("Snapshot directory changed during verification")
        return {"name": name, "timestamp": stamp.isoformat(), "services": services,
                "bindings": binding_versions(inventory),
                "files": identities, "directory": ds, "bytes": logical,
                "allocated_bytes": allocated, "kind": "snapshot"}
    finally:
        os.close(fd)


def usage(path):
    s = os.statvfs(path)
    used = s.f_blocks - s.f_bfree
    denominator = used + s.f_bavail
    percent = used * 100 / denominator if denominator else 100
    return {"usage_percent": round(percent, 4), "df_percent": math.ceil(percent),
            "used_bytes": used * s.f_frsize, "available_bytes": s.f_bavail * s.f_frsize}


def pressure(percent):
    return "CRITICAL" if percent > 85 else "WARNING" if percent >= 80 else "HEALTHY"


def uuid_device(uuid, source):
    """Require the mounted source to be the block device named by the UUID."""
    if not isinstance(uuid, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*", uuid):
        raise Unsafe("Missing or invalid audited filesystem UUID")
    if not isinstance(source, str) or not source.startswith("/dev/"):
        raise Unsafe("Mounted filesystem source is not a verifiable block device")
    try:
        stable = os.stat(Path("/dev/disk/by-uuid") / uuid)
        mounted = os.stat(source)
    except OSError as exc:
        raise Unsafe("Filesystem UUID device cannot be verified") from exc
    if (not stat.S_ISBLK(stable.st_mode) or not stat.S_ISBLK(mounted.st_mode)
            or stable.st_rdev != mounted.st_rdev):
        raise Unsafe("Mounted device differs from the audited filesystem UUID")
    return stable.st_rdev


def check_mount(config):
    """Require UUID, mountpoint and type; /dev/sdX names may change at boot."""
    result = subprocess.run(
        ["findmnt", "-J", "-T", config["backup_root"], "-o", "TARGET,SOURCE,FSTYPE,UUID"],
        check=True, capture_output=True, text=True, timeout=10)
    matches = [x for x in json.loads(result.stdout)["filesystems"]
               if x.get("fstype") != "autofs"]
    expected = config["filesystem"]
    if len(matches) != 1 or any(matches[0].get(k) != expected.get(k)
                              for k in ("target", "fstype", "uuid")):
        raise Unsafe("Backup filesystem missing or identity differs from audit")
    device = uuid_device(expected.get("uuid"), matches[0].get("source"))
    with directory(config["backup_root"]) as fd:
        identity = signature(os.fstat(fd))[:2]
        if identity[0] != device:
            raise Unsafe("Backup root is not on the verified UUID device")
        return identity


def read_config(path):
    config = json.loads(Path(path).read_text())
    root = Path(config["backup_root"])
    if not root.is_absolute() or root.name != "HomelabBackups" or ".." in root.parts:
        raise Unsafe("Only an explicitly approved HomelabBackups root is supported")
    fs = config["filesystem"]
    if set(fs) != {"target", "source", "fstype", "uuid"} or not all(fs.values()):
        raise Unsafe("Exact audited mount identity is required")
    if Path(fs["target"]) not in root.parents:
        raise Unsafe("Backup directory must be beneath audited mount")
    for key in ("lock_file", "state_dir"):
        if not Path(config[key]).is_absolute():
            raise Unsafe(f"Absolute {key} required")
    ZoneInfo(config["timezone"])
    pins = config.get("protected_snapshots", {})
    if not isinstance(pins, dict) or any(
        not SNAPSHOT.fullmatch(name) or not isinstance(reason, str) or not reason
        for name, reason in pins.items()
    ):
        raise Unsafe("Invalid explicitly protected snapshot inventory")
    warnings = config.get("coverage_warnings", [])
    if not isinstance(warnings, list) or any(not isinstance(w, str) or not w for w in warnings):
        raise Unsafe("Invalid audited backup coverage warnings")
    return config


def retention(records, now):
    """Union of rolling seven days, four completed ISO weeks, three months.

    Apply buckets per service, so a service removed from newer snapshots keeps
    its own newest verified restore point and its own historical anchors.
    """
    reasons = {r["name"]: set() for r in records}
    anchors = {}
    week = now.date() - timedelta(days=now.weekday())
    months = []
    index = now.year * 12 + now.month - 1
    for offset in range(1, 4):
        year, month = divmod(index - offset, 12)
        months.append((year, month + 1))
    for service in sorted({s for r in records for s in r["services"]}):
        service_records = sorted([r for r in records if service in r["services"]],
                                 key=lambda r: r["timestamp"], reverse=True)
        newest = service_records[0]
        anchors[service] = newest["name"]
        reasons[newest["name"]].add(f"latest:{service}")
        versions = {}
        for r in service_records:
            version = r.get("bindings", {}).get(service, "unspecified")
            versions.setdefault(version, r)
        for version, r in versions.items():
            reasons[r["name"]].add(f"last-mount-version:{service}:{version[:12]}")
        for r in service_records:
            stamp = datetime.fromisoformat(r["timestamp"])
            if stamp >= now - timedelta(days=7):
                reasons[r["name"]].add("daily:7-days")
        for offset in range(1, 5):
            start = week - timedelta(weeks=offset)
            end = start + timedelta(weeks=1)
            winner = next((r for r in service_records
                           if start <= datetime.fromisoformat(r["timestamp"]).date() < end), None)
            if winner:
                reasons[winner["name"]].add(f"weekly:{start.isoformat()}")
        for year, month in months:
            winner = next((r for r in service_records
                           if (datetime.fromisoformat(r["timestamp"]).year,
                               datetime.fromisoformat(r["timestamp"]).month) == (year, month)), None)
            if winner:
                reasons[winner["name"]].add(f"monthly:{year:04}-{month:02}")
    return {k: sorted(v) for k, v in reasons.items()}, anchors


def inspect_disposable(rootfd, name, records, now):
    """Only explicit producer-marked artifacts, older than 7d, with replacements."""
    stamp = datetime.strptime(name.removeprefix(".incomplete-"), "%Y-%m-%dT%H%M%S").replace(tzinfo=now.tzinfo)
    if stamp >= now - timedelta(days=7):
        raise Unsafe("Recent incomplete snapshot")
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | NOFOLLOW, dir_fd=rootfd)
    try:
        files = set(os.listdir(fd))
        allowed = BASE_FILES | {"SHA256SUMS", MARKER} | {
            n.removesuffix(".gz") for n in BASE_FILES if n.endswith(".tar.gz")}
        if MARKER not in files or not files <= allowed:
            raise Unsafe("Incomplete artifacts lack explicit disposable proof")
        raw, _ = read_file(fd, MARKER, max_bytes=16384)
        services = marker_services(raw)
        bindings = json.loads(raw).get("bindings")
        if not isinstance(bindings, dict) or set(bindings) != set(services):
            raise Unsafe("Incomplete artifacts lack verified mount versions")
        for service in services:
            if not any(service in r["services"] and
                       r["bindings"][service] == bindings[service] and
                       datetime.fromisoformat(r["timestamp"]) > stamp for r in records):
                raise Unsafe(f"No newer verified replacement for {service}")
        identities = {}; allocated = logical = 0
        for filename in sorted(files):
            st = os.stat(filename, dir_fd=fd, follow_symlinks=False)
            if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                    or datetime.fromtimestamp(st.st_mtime, now.tzinfo) >= now - timedelta(days=7)):
                raise Unsafe("Active, linked or unknown incomplete artifact")
            identities[filename] = signature(st)
            allocated += st.st_blocks * 512; logical += st.st_size
        return {"name": name, "timestamp": stamp.isoformat(), "services": services,
                "files": identities, "directory": signature(os.fstat(fd)),
                "bytes": logical, "allocated_bytes": allocated, "kind": "disposable",
                "bindings": bindings}
    finally:
        os.close(fd)


def build_plan(config, now, verbose=False, verified_plan=None):
    root_identity = check_mount(config)
    before = usage(config["backup_root"])
    records = []; protected = []; errors = []; incompletes = []
    cache = {}
    if verified_plan is not None:
        age = now - datetime.fromisoformat(verified_plan["timestamp"])
        if (verified_plan.get("version") not in {1, 2} or verified_plan["root"] != config["backup_root"]
                or tuple(verified_plan["root_identity"]) != tuple(root_identity)
                or age < timedelta(0) or age > timedelta(hours=1)):
            raise Unsafe("Verified dry-run cache is stale or belongs to a different root")
        cache = {r["name"]: r for r in verified_plan["selected"] + verified_plan["retained"]
                 if r["kind"] == "snapshot"}
    zone = now.tzinfo
    with directory(config["backup_root"]) as rootfd:
        for name in sorted(os.listdir(rootfd)):
            try:
                st = os.stat(name, dir_fd=rootfd, follow_symlinks=False)
                if stat.S_ISLNK(st.st_mode):
                    raise Unsafe("Symlink rejected; links are never followed")
                if name.startswith(".incomplete-") and SNAPSHOT.fullmatch(name[12:]):
                    incompletes.append(name); continue
                if not SNAPSHOT.fullmatch(name) or not stat.S_ISDIR(st.st_mode):
                    raise Unsafe("Unrecognized backup/artifact; preserved")
                if name in cache:
                    # Dry-run-only reuse of recent hashes. ctime/mtime, inode,
                    # type, links, size and complete tree membership must match.
                    assert_unchanged(rootfd, cache[name])
                    record = cache[name]
                    # Enrich an earlier verified preview with immutable mount
                    # metadata without reading any live application state.
                    cached_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | NOFOLLOW, dir_fd=rootfd)
                    try:
                        inventory, _ = read_file(cached_fd, "docker-inspect.json", max_bytes=16 * 1024 * 1024)
                        record = {**record, "bindings": binding_versions(inventory)}
                    finally:
                        os.close(cached_fd)
                    if verbose:
                        print(f"Verified identities unchanged: {name}", flush=True)
                else:
                    if verbose:
                        print(f"Verifying {name}", flush=True)
                    record = verify_snapshot(rootfd, name, zone)
                if datetime.fromisoformat(record["timestamp"]) > now:
                    raise Unsafe("Future-dated backup; preserved")
                records.append(record)
            except (Unsafe, OSError, ValueError, KeyError, TypeError) as exc:
                protected.append({"name": name, "reason": str(exc)})
                errors.append(f"{name}: {exc}")
        reasons, anchors = retention(records, now)
        for name, reason in config.get("protected_snapshots", {}).items():
            if name in reasons:
                reasons[name].append("explicit-protection:" + reason)
        selected = [r for r in records if not reasons[r["name"]]]
        retained = [r for r in records if reasons[r["name"]]]
        for record in retained:
            protected.append({"name": record["name"], "reason": reasons[record["name"]]})
        for name in incompletes:
            if pressure(before["usage_percent"]) == "CRITICAL":
                try:
                    selected.append(inspect_disposable(rootfd, name, retained, now))
                    continue
                except (Unsafe, OSError, ValueError, KeyError, TypeError) as exc:
                    reason = str(exc)
            else:
                reason = "Incomplete artifacts preserved below critical disk pressure"
            protected.append({"name": name, "reason": reason})
    if not records:
        errors.append("No complete checksum-verified restore points; deletion disabled")
        selected = []
    return {"version": 2, "timestamp": now.isoformat(), "root": config["backup_root"],
            "root_identity": root_identity, "filesystem_before": before,
            "selected": selected, "retained": retained, "anchors": anchors,
            "protected": protected, "errors": errors,
            "estimated_reclaimed_bytes": sum(r["allocated_bytes"] for r in selected),
            "backup_bytes_before": sum(r["bytes"] for r in records),
            "backup_count_before": len(records), "unknown_count": len(protected) - len(retained)}


def plan_key(plan):
    payload = {k: plan[k] for k in ("root", "root_identity", "selected", "retained", "anchors")}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def assert_unchanged(rootfd, record):
    fd = os.open(record["name"], os.O_RDONLY | os.O_DIRECTORY | NOFOLLOW, dir_fd=rootfd)
    try:
        if signature(os.fstat(fd)) != tuple(record["directory"]):
            raise Unsafe(f"Directory changed: {record['name']}")
        if set(os.listdir(fd)) != set(record["files"]):
            raise Unsafe(f"Snapshot membership changed: {record['name']}")
        for filename, sig in record["files"].items():
            if signature(os.stat(filename, dir_fd=fd, follow_symlinks=False)) != tuple(sig):
                raise Unsafe(f"Verified backup changed: {record['name']}/{filename}")
    finally:
        os.close(fd)


def write_json(path, value):
    # State directory is private; reject existing symlinks and write atomically.
    path = Path(path)
    with directory(path.parent) as fd:
        tmp = f".{path.name}.{os.getpid()}.tmp"
        f = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | NOFOLLOW, 0o600, dir_fd=fd)
        try:
            data = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
            while data:
                data = data[os.write(f, data):]
            os.fsync(f)
        finally:
            os.close(f)
        os.replace(tmp, path.name, src_dir_fd=fd, dst_dir_fd=fd)
        os.fsync(fd)


class Log:
    def __init__(self, state_dir, now):
        self.now = now
        self.path = Path(state_dir) / f"cleanup-{now:%Y-%m}.jsonl"

    def event(self, event, **values):
        entry = {"timestamp": datetime.now(self.now.tzinfo).isoformat(), "event": event, **values}
        with directory(self.path.parent) as fd:
            f = os.open(self.path.name, os.O_WRONLY | os.O_APPEND | os.O_CREAT | NOFOLLOW, 0o600, dir_fd=fd)
            try:
                if not stat.S_ISREG(os.fstat(f).st_mode) or os.fstat(f).st_nlink != 1:
                    raise Unsafe("Unsafe persistent log")
                data = (json.dumps(entry, sort_keys=True) + "\n").encode()
                # Handle short writes; log intent must be durable before unlink.
                while data:
                    data = data[os.write(f, data):]
                os.fsync(f)
            finally:
                os.close(f)


def execute(config, plan, log):
    retained = {r["name"]: r for r in plan["retained"]}
    deleted = []; reclaimed = 0; errors = []
    with directory(config["backup_root"]) as rootfd:
        for record in plan["selected"]:
            try:
                if record["kind"] == "disposable" and pressure(
                        usage(config["backup_root"])["usage_percent"]) != "CRITICAL":
                    log.event("protected", name=record["name"],
                              reason="Pressure no longer critical after retention")
                    continue
                if record["name"] in plan["anchors"].values():
                    raise Unsafe("Last valid restore point cannot be deleted")
                assert_unchanged(rootfd, record)
                fd = os.open(record["name"], os.O_RDONLY | os.O_DIRECTORY | NOFOLLOW, dir_fd=rootfd)
                try:
                    for filename, sig in sorted(record["files"].items(), key=lambda x: x[0] == "SHA256SUMS"):
                        # Recheck containment/mount and every affected latest restore
                        # point immediately before EVERY unlink, not only at startup.
                        if tuple(check_mount(config)) != tuple(plan["root_identity"]):
                            raise Unsafe("Approved root changed")
                        if (os.stat(record["name"], dir_fd=rootfd, follow_symlinks=False).st_ino
                                != os.fstat(fd).st_ino):
                            raise Unsafe("Candidate directory replaced")
                        affected = set()
                        for service in record["services"]:
                            anchor = retained.get(plan["anchors"].get(service))
                            if record["kind"] == "snapshot":
                                same_binding = [r for r in retained.values()
                                                if service in r["services"] and
                                                r["bindings"][service] == record["bindings"][service]]
                                anchor = max(same_binding, key=lambda r: r["timestamp"]) if same_binding else None
                            elif anchor is not None and anchor["bindings"][service] != record["bindings"][service]:
                                same_binding = [r for r in retained.values() if service in r["services"] and
                                                r["bindings"][service] == record["bindings"][service]]
                                anchor = max(same_binding, key=lambda r: r["timestamp"]) if same_binding else None
                            if anchor is None or anchor["name"] == record["name"]:
                                raise Unsafe(f"No protected valid restore point for {service}")
                            affected.add(anchor["name"])
                        for name in affected:
                            assert_unchanged(rootfd, retained[name])
                        st = os.stat(filename, dir_fd=fd, follow_symlinks=False)
                        if signature(st) != tuple(sig):
                            raise Unsafe("Deletion target changed or became a link")
                        log.event("delete_intent", backup=record["name"], file=filename,
                                  allocated_bytes=st.st_blocks * 512)
                        os.unlink(filename, dir_fd=fd)
                        reclaimed += st.st_blocks * 512
                        log.event("deleted_file", backup=record["name"], file=filename,
                                  reclaimed_bytes=st.st_blocks * 512)
                    # A new unknown file prevents rmdir; it is never recursively removed.
                    if os.listdir(fd):
                        raise Unsafe("Unexpected file appeared; directory preserved")
                    check_mount(config)
                    st = os.stat(record["name"], dir_fd=rootfd, follow_symlinks=False)
                    if (st.st_dev, st.st_ino) != (os.fstat(fd).st_dev, os.fstat(fd).st_ino):
                        raise Unsafe("Directory changed before rmdir")
                    os.rmdir(record["name"], dir_fd=rootfd)
                    deleted.append(record["name"])
                    log.event("deleted_backup", backup=record["name"])
                finally:
                    os.close(fd)
            except (Unsafe, OSError, subprocess.SubprocessError, ValueError) as exc:
                errors.append(f"{record['name']}: {exc}")
                log.event("error", backup=record["name"], reason=str(exc))
                # Stop on first failure; a changed anchor may affect all other services.
                break
    return deleted, reclaimed, errors


def print_plan(plan, verbose):
    print(f"Filesystem: {plan['filesystem_before']['usage_percent']:.2f}% "
          f"({pressure(plan['filesystem_before']['usage_percent'])})")
    for r in plan["selected"]:
        print(f"WOULD DELETE {plan['root']}/{r['name']} "
              f"({len(r['files'])} files; {r['allocated_bytes']} allocated bytes; {r['kind']})")
        if verbose:
            for filename in sorted(r["files"]):
                print(f"  {r['name']}/{filename}")
    if verbose:
        for r in plan["protected"]:
            print(f"PROTECTED {r['name']}: {r['reason']}")
    print(f"Latest verified snapshots per service inventory protected: {len(plan['anchors'])}")
    print(f"Selected backups: {len(plan['selected'])}; estimated reclaimed space: "
          f"{plan['estimated_reclaimed_bytes']} bytes "
          f"({plan['estimated_reclaimed_bytes'] / 1024**3:.2f} GiB)")
    for error in plan["errors"]:
        print(f"WARNING: {error}")


def health(config, now):
    problems = list(config.get("coverage_warnings", []))
    state = Path(config["state_dir"]) / "last-run.json"
    check_mount(config)
    disk = usage(config["backup_root"])
    if state.exists():
        summary = json.loads(state.read_text())
        if summary.get("mode") != "execute" or summary.get("root") != config["backup_root"]:
            problems.append("Cleanup state does not match the approved root")
        age = now - datetime.fromisoformat(summary["timestamp"])
        if age > timedelta(hours=36) or age < timedelta(0):
            problems.append("Cleanup result is stale or future-dated")
        problems += summary.get("errors", [])
    else:
        summary = {}; problems.append("Cleanup has no completed real run")
    status = pressure(disk["usage_percent"])
    if status != "HEALTHY":
        problems.append(f"Backup filesystem usage {disk['usage_percent']:.2f}%")
    if problems and status == "HEALTHY":
        status = "WARNING"
    count = 0; dates = []
    with directory(config["backup_root"]) as fd:
        for name in os.listdir(fd):
            st = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if SNAPSHOT.fullmatch(name) and stat.S_ISDIR(st.st_mode):
                count += 1; dates.append(name[:10])
    deleted = summary.get("deleted", [])
    cleanup_line = (f"Cleanup: {len(deleted)} removed" if deleted else
                    "Cleanup: Failed or unverified" if summary.get("errors") or not summary else
                    "Cleanup: Not required")
    lines = ["BACKUP STORAGE", f"Status: {status}", f"Usage: {disk['usage_percent']:.2f}%",
             f"Backups: {count}", f"Oldest retained: {min(dates) if dates else 'none'}",
             cleanup_line,
             f"Space reclaimed: {summary.get('reclaimed_bytes', 0) / 1024**3:.2f} GiB"]
    if problems:
        lines.append("Reason: " + "; ".join(problems))
    return {"status": status, "text": "\n".join(lines), "reasons": problems}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("backup-cleanup-policy.json"))
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--health", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--plan-output", type=Path)
    parser.add_argument("--apply-plan", type=Path)
    parser.add_argument("--verified-plan", type=Path,
                        help="Dry-run only: reuse <1h-old hashes after checking every file identity")
    args = parser.parse_args()
    if args.apply_plan and not args.execute:
        parser.error("--apply-plan requires --execute")
    if args.verified_plan and (args.execute or args.health):
        parser.error("--verified-plan is dry-run only; execution always hashes backups again")
    config = None; log = None
    try:
        config = read_config(args.config)
        now = datetime.now(ZoneInfo(config["timezone"]))
        if args.health:
            print(json.dumps(health(config, now))); return 0
        state = Path(config["state_dir"])
        state.mkdir(mode=0o700, parents=True, exist_ok=True)
        log = Log(state, now)
        mode = "execute" if args.execute else "dry-run"
        log.event("start", mode=mode)
        with directory(Path(config["lock_file"]).parent) as lockdir:
            lock = os.open(Path(config["lock_file"]).name,
                           os.O_WRONLY | os.O_CREAT | os.O_NONBLOCK | NOFOLLOW, 0o600, dir_fd=lockdir)
            try:
                if not stat.S_ISREG(os.fstat(lock).st_mode) or os.fstat(lock).st_nlink != 1:
                    raise Unsafe("Unsafe backup lock")
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise Unsafe("Backup/maintenance lock busy; no deletion") from exc
                verified = json.loads(args.verified_plan.read_text()) if args.verified_plan else None
                plan = build_plan(config, now, args.verbose, verified)
                print_plan(plan, args.verbose)
                if args.plan_output:
                    write_json(args.plan_output, plan)
                for p in plan["protected"]:
                    log.event("protected", **p)
                deleted = []; reclaimed = 0; errors = list(plan["errors"])
                if args.execute:
                    if args.apply_plan:
                        reviewed = json.loads(args.apply_plan.read_text())
                        if plan_key(reviewed) != plan_key(plan):
                            raise Unsafe("Dry-run plan changed; deletion refused")
                    log.event("plan", selected=[r["name"] for r in plan["selected"]],
                              filesystem_before=plan["filesystem_before"],
                              estimated_reclaimed_bytes=plan["estimated_reclaimed_bytes"])
                    deleted, reclaimed, delete_errors = execute(config, plan, log)
                    errors += delete_errors
                after = usage(config["backup_root"])
                retained_dates = [r["timestamp"][:10] for r in plan["retained"]]
                summary = {"timestamp": now.isoformat(), "mode": mode, "root": plan["root"],
                           "deleted": deleted, "reclaimed_bytes": reclaimed,
                           "filesystem_before": plan["filesystem_before"], "filesystem_after": after,
                           "backup_count_before": plan["backup_count_before"],
                           "backup_count_after": plan["backup_count_before"] - len(
                               [r for r in plan["selected"] if r["kind"] == "snapshot" and r["name"] in deleted]),
                           "backup_bytes_before": plan["backup_bytes_before"],
                           "backup_bytes_after": plan["backup_bytes_before"] - sum(
                               r["bytes"] for r in plan["selected"] if r["kind"] == "snapshot" and r["name"] in deleted),
                           "oldest_retained": min(retained_dates) if retained_dates else None,
                           "protected": plan["protected"], "anchors": plan["anchors"], "errors": errors}
                log.event("summary", **summary)
                if args.execute:
                    write_json(state / "last-run.json", summary)
                print(json.dumps(summary, sort_keys=True))
                return 1 if errors else 0
            finally:
                os.close(lock)
    except (Unsafe, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        message = f"Backup cleanup refused: {exc}"
        if log:
            log.event("error", reason=message)
            if args.execute and config:
                write_json(Path(config["state_dir"]) / "last-run.json", {
                    "timestamp": datetime.now(ZoneInfo(config["timezone"])).isoformat(),
                    "mode": "execute", "root": config["backup_root"], "errors": [message],
                    "deleted": [], "reclaimed_bytes": 0})
        if args.health:
            print(json.dumps({"status": "CRITICAL", "text": f"BACKUP STORAGE\nStatus: CRITICAL\nReason: {message}",
                              "reasons": [message]}))
        else:
            print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
