#!/usr/bin/env python3
"""Export an allowlisted, sanitized view of the live Compose stacks."""

from pathlib import Path
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
REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "stacks"

STACKS = {
    "bazarr": "docker-compose.yml",
    "crowdsec": "compose.yaml",
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


def sanitize(text: str) -> str:
    text = text.replace(LIVE_MEDIA, "${MEDIA_ROOT:-/srv/media}")
    text = text.replace(str(LIVE), "${DOCKER_ROOT:-/opt/homelab}")
    lan_ip = detected_lan_ip()
    if lan_ip:
        text = text.replace(lan_ip, "${HOMELAB_IP:?Set HOMELAB_IP}")
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
            raise SystemExit(f"Missing allowlisted source: {source}")
        target_dir = OUT / name
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "compose.yaml").write_text(
            sanitize(source.read_text(encoding="utf-8")), encoding="utf-8"
        )

    print(f"Exported {len(STACKS)} sanitized stacks to {OUT}")


if __name__ == "__main__":
    main()
