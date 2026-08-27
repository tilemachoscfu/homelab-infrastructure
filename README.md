# Homelab Infrastructure

Sanitized, reproducible configuration for the Linux Mint homelab hosted on an
HP Laptop 15-db0xxx.

## Services

- Media: Jellyfin, Jellyseerr, Sonarr, Radarr, Prowlarr, Bazarr
- Downloads: qBittorrent behind Gluetun/AirVPN, slskd and Soularr
- Music: Lidarr and Navidrome
- Network: AdGuard Home and Nginx Proxy Manager
- Operations: Homepage, Uptime Kuma, Scrutiny, Portainer, Netdata and Glances
- Data: Vaultwarden, Immich, Paperless-ngx, Kiwix and Home Assistant

## Security model

This repository contains templates only. It intentionally excludes:

- passwords, API keys, tokens and private keys;
- WireGuard/AirVPN configuration;
- `.env` files and application databases;
- media, photos, documents and backups;
- live application state and logs;
- public or Tailscale-specific hostnames.

Copy `.env.example` to `.env` locally and replace `CHANGE_ME` values. Never
commit the resulting `.env` file.

## Updating

```bash
./scripts/sync-from-live.py
./scripts/check-secrets.py
./scripts/update-repo.sh "Describe the homelab change"
```

`update-repo.sh` refuses to commit when the safety scan fails.

See [docs/architecture.md](docs/architecture.md) and
[docs/operations.md](docs/operations.md).
