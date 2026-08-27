# Architecture

## Host

- Linux Mint Cinnamon on an HP Laptop 15-db0xxx
- Docker Compose stacks stored under the operator's local Docker directory
- Persistent media stored outside container configuration
- Local DNS uses the reserved `home.arpa` namespace
- Remote administration uses Tailscale

## Request flow

```text
LAN client -> AdGuard Home DNS -> Nginx Proxy Manager -> application
Remote client -> Tailscale -> application port or approved HTTPS endpoint
```

## Media automation

```text
Jellyseerr -> Sonarr/Radarr -> Prowlarr -> qBittorrent -> Jellyfin
Lidarr -> Prowlarr/qBittorrent -> Music library -> Navidrome
Lidarr wanted list -> Soularr -> slskd -> Lidarr import -> Navidrome
```

qBittorrent and slskd share Gluetun's network namespace. Gluetun must become
healthy before either downloader starts.

## Storage boundaries

Container configuration, databases and secrets stay on the host and are not
tracked. Compose templates use `${MEDIA_ROOT}` instead of a personal mount
path. Backups are also excluded from Git.
