# Verified media maintenance — 2026-10-08

Production uses a lightweight five-minute authenticated push collector with application payload checks, VPN namespace/firewall/interface checks, stalled/import checks, subtitle-provider checks, music availability, recent transcoding errors, mount/SMART state and backup freshness. Two bad samples trigger an alert; three good samples plus a 30-minute recovery hold clear it. Repeated Kuma notifications are disabled. Existing Telegram integration is retained. No new inbound monitoring endpoint is opened.

Daily application backups run at 05:40 Europe/Athens with jitter and the existing backup lock. SQLite backups establish an explicit read transaction, include committed WAL contents, verify SHA256 and test isolated restores with quick_check. Required mount UUIDs and free-space reserves fail closed. Active Seerr data is included and mirrored over SSH. Sunday snapshots add monitoring application databases/configuration. Retention classifies 30 daily days / 12 weekly weeks and is append-only; deletion is disabled. Collector private push tokens and systemd units are included in private backups.

Live scripts, credentials and database snapshots stay in private application backups. Compose templates require host-specific environment values. Existing storage roots are preserved by the live configuration; these examples must not be used to migrate storage. Jellyfin remains at 10.11.11. Seerr 3.5.0 uses the original request appdata path.

Kuma remains at 1.23.17: an isolated 2.5.5 preflight demonstrated expensive migration of 1.53 million heartbeat rows on the low-resource support host, so a separate maintenance window is needed. Navidrome 0.64.2 is deferred until the existing missing music files are located and ID/playlist migration can be validated. Shared reverse-proxy update is deferred to avoid interrupting unrelated routes.

Only verified media/supporting Compose templates were exported. Broad sync-from-live was not run because it modifies unrelated stacks; pre-existing working-tree changes were preserved.
