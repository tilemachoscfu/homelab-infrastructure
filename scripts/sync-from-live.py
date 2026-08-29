#!/usr/bin/env python3
"""Export an allowlisted, sanitized view of the live Compose stacks."""

from pathlib import Path
import ipaddress
import os
import re
import shutil
import socket
import subprocess

LIVE = Path(os.environ.get("HOMELAB_LIVE_ROOT", Path.home() / "docker"))
LIVE_MEDIA = os.environ.get(
    "HOMELAB_LIVE_MEDIA_ROOT", f"/media/{Path.home().name}/Windows"
)


def detected_lan_ip() -> str | None:
    configured = os.environ.get("HOMELAB_LIVE_IP")
    if configured:
        return configured
    try:
        addresses = subprocess.check_output(["hostname", "-I"], text=True).split()
    except (OSError, subprocess.CalledProcessError):
        return None
    return next(
        (
            address
            for address in addresses
            if re.match(r"^(?:10[.]|192[.]168[.]|172[.](?:1[6-9]|2\d|3[01])[.])", address)
        ),
        None,
    )


def detected_gateway() -> str | None:
    try:
        route = subprocess.check_output(
            ["ip", "route", "show", "default"], text=True
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    match = re.search(r"\bvia\s+(\S+)", route)
    return match.group(1) if match else None


REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "stacks"
AUTOMATION_OUT = REPO / "automation"

STACKS = {
    "aurral": "compose.yaml",
    "bazarr": "docker-compose.yml",
    "crowdsec": "compose.yaml",
    "explo": "compose.yaml",
    "glances": "compose.yaml",
    "homeassistant": "compose.yaml",
    "homepage": "compose.yaml",
    "immich": "compose.yaml",
    "jellyseerr": "docker-compose.yml",
    "kiwix": "compose.yaml",
    "lidarr": "compose.yaml",
    "navidrome": "compose.yaml",
    "netdata": "compose.yaml",
    "nginx-proxy-manager": "compose.yaml",
    "paperless": "compose.yaml",
    "portainer": "compose.yaml",
    "prowlarr": "docker-compose.yml",
    "qbittorrent": "docker-compose.yml",
    "radarr": "docker-compose.yml",
    "scrutiny": "compose.yaml",
    "sonarr": "docker-compose.yml",
    "vaultwarden": "compose.yaml",
}

AUTOMATION_FILES = {
    "crontab.example": LIVE / "monitoring" / "crontab.install",
    "daily-health-report.sh": LIVE / "monitoring" / "daily-health-report.sh",
    "install-nightly-maintenance.sh": LIVE
    / "monitoring"
    / "install-nightly-maintenance.sh",
    "nightly-maintenance.sh": LIVE / "monitoring" / "nightly-maintenance.sh",
}


def sanitize(text: str) -> str:
    text = text.replace(LIVE_MEDIA, "${MEDIA_ROOT:-/srv/media}")
    text = text.replace(str(LIVE), "${DOCKER_ROOT:-/opt/homelab}")
    lan_ip = detected_lan_ip()
    if lan_ip:
        live_subnet = os.environ.get(
            "HOMELAB_LIVE_SUBNET",
            str(ipaddress.ip_network(f"{lan_ip}/24", strict=False)),
        )
        text = text.replace(live_subnet, "${LAN_SUBNET:?Set LAN_SUBNET}")
        text = text.replace(lan_ip, "${HOMELAB_IP:?Set HOMELAB_IP}")
    gateway = detected_gateway()
    if gateway:
        text = text.replace(gateway, "${LAN_GATEWAY:?Set LAN_GATEWAY}")
    text = text.replace(socket.gethostname(), "homelab-host")
    text = re.sub(
        r'(?mi)^(\s*hostname\s*:\s*).+$',
        r'\1homelab-host',
        text,
    )
    sensitive_names = (
        r"POSTGRES_PASSWORD|DB_PASSWORD|PASSWORD|PASSWD|API_KEY|APIKEY|TOKEN|SECRET|"
        r"PRIVATE_KEY|WIREGUARD_PRIVATE_KEY"
    )
    text = re.sub(
        rf'(?mi)^(\s*(?:{sensitive_names})\s*:\s*).+$',
        r'\1${SECRET_VALUE:-CHANGE_ME}',
        text,
    )
    text = re.sub(
        rf'(?mi)^(\s*-\s*(?:{sensitive_names})\s*=).+$',
        r'\1${SECRET_VALUE:-CHANGE_ME}',
        text,
    )
    text = re.sub(
        r'https://[^\s"\']+\.ts\.net',
        'https://your-hostname.example.invalid',
        text,
    )
    return text


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    expected = set(STACKS)
    for directory in OUT.iterdir():
        if directory.is_dir() and directory.name not in expected:
            shutil.rmtree(directory)

    for name, compose_name in STACKS.items():
        source = LIVE / name / compose_name
        if not source.is_file():
            print(f"Skipped missing live stack (kept existing template): {source}")
            continue
        target_dir = OUT / name
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "compose.yaml").write_text(
            sanitize(source.read_text(encoding="utf-8")), encoding="utf-8"
        )

    AUTOMATION_OUT.mkdir(parents=True, exist_ok=True)
    for target_name, source in AUTOMATION_FILES.items():
        if not source.is_file():
            raise SystemExit(f"Missing allowlisted automation source: {source}")
        target = AUTOMATION_OUT / target_name
        target.write_text(
            sanitize(source.read_text(encoding="utf-8")), encoding="utf-8"
        )
        if source.suffix == ".sh":
            target.chmod(0o755)

    print(f"Exported sanitized live stacks to {OUT}")
    print(f"Exported {len(AUTOMATION_FILES)} sanitized automations to {AUTOMATION_OUT}")


if __name__ == "__main__":
    main()
