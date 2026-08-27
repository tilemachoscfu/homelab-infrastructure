# Changelog

## 2026-08-27 — Public project foundation

- Expanded the README with architecture, service and safe-use guidance.
- Added continuous validation for secrets, scripts and Compose templates.
- Added security, contribution and roadmap documentation.
- Added detailed architecture and storage-boundary diagrams.
- Published a linked roadmap board with initial reliability and documentation
  issues.
- Removed the obsolete Home Assistant `http:` YAML block after verifying its
  successful migration to UI-managed network settings.
- Allowed the VPN-isolated Soularr service to reach Lidarr on the LAN while
  keeping Internet traffic routed through Gluetun/AirVPN.

## 2026-08-27

- Documented the existing media, network, monitoring and data stacks.
- Added Lidarr and Navidrome music automation.
- Added slskd and Soularr behind Gluetun/AirVPN.
- Fixed qBittorrent startup ordering so it waits for a healthy VPN.
- Added Vaultwarden over an approved Tailscale HTTPS endpoint.
- Corrected Home Assistant reverse-proxy trust settings.
- Diagnosed the dual-AMD black-screen boot race and prepared a LightDM wait.
- Set Linux Mint as the primary UEFI boot entry and removed the stale Windows
  Boot Manager entry.
