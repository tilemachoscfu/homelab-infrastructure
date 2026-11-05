# Temporary Bluetooth receiver

A receiver computer with a working BlueZ adapter supplies Bluetooth advertisements
to the Home Assistant host through an encrypted SSH reverse tunnel. Home Assistant
uses its native ESPHome and Xiaomi BLE integrations, preserving existing devices,
entity IDs, history and automation references.

The receiver must stay powered on, awake and connected to the network. The
Home Assistant server continues to run on the server host. The old Home Assistant
container on the receiver remains stopped.

## Installed components

- `btproxy` version 0.6.0, Linux amd64, installed under
  `~/.local/share/hp-ble-proxy/v0.6.0/`.
- Two user services from `automation/bluetooth-bridge/`, enabled for
  `default.target`. User lingering must be enabled for startup without login.
- Private configuration under `~/.config/hp-ble-proxy/`, directory mode 700;
  configuration, SSH target environment and encryption key files mode 600.
- Native ESPHome integration configured for `127.0.0.1:6053` on the server host,
  using the receiver's encryption key and Active Bluetooth scanning mode.

The downloaded release archive was checked against its GitHub release digest:

```text
btproxy-linux-amd64.tar.gz
sha256:6957ffc69fbbedc708ebc32204c9e5de2687b7ecb55054f1dd1b1d3d38ee06eb
```

Upstream: <https://github.com/yuzi-co/btproxy/releases/tag/v0.6.0>.
The BlueZ backend is pinned because the receiver also runs desktop Bluetooth.
Do not automatically replace it with the upstream kernel backend or stop BlueZ.

## Private configuration

Copy `proxy.json.example` to `~/.config/hp-ble-proxy/proxy.json`, replace its
placeholder addresses with the receiver adapter MAC and the two thermometer MACs,
and keep those values out of Git. The allowlist forwards only those thermometers.
The proxy binds only to the receiver's loopback address, with mDNS disabled.

Create `~/.config/hp-ble-proxy/noise.key` containing a random 32-byte base64
ESPHome Noise key. Enter this same key when configuring the ESPHome integration.
The key stays in its own private file and is passed using `-encryption-key-file`.

Create `~/.config/hp-ble-proxy/tunnel.env` containing:

```text
HOME_ASSISTANT_SSH_HOST=your-existing-server-ssh-alias
```

The SSH alias must already have verified host keys and working key authentication.
The tunnel listens only on server loopback and forwards to receiver loopback.
It needs no additional LAN listener, router port forward or firewall exception.
Both services restart after a failure; SSH keepalives detect a lost connection.

## Verification

```sh
systemd-analyze --user verify ~/.config/systemd/user/hp-ble-proxy*.service
systemctl --user is-enabled hp-ble-proxy.service hp-ble-proxy-tunnel.service
systemctl --user is-active hp-ble-proxy.service hp-ble-proxy-tunnel.service
journalctl --user -u hp-ble-proxy.service -u hp-ble-proxy-tunnel.service -n 30
```

Verify that both original temperature and humidity entities are numeric. In
Bluetooth diagnostics, check that the ESPHome scanner is actively scanning and
receives fresh advertisements from both thermometers. An unchanged temperature
can retain its earlier state timestamp even while fresh advertisements arrive.

Restart the bridge and tunnel, then confirm automatic reconnection and fresh
advertisements. This checks service recovery without rebooting either computer.
Keep before-change configuration backups and runtime evidence private.

## When the server gets its own Bluetooth adapter

Configure the new adapter on the Home Assistant host. Keep the existing Xiaomi
BLE entries and their bind keys. Confirm fresh readings from both rooms using
the new adapter, then disable the temporary receiver services:

```sh
systemctl --user disable --now hp-ble-proxy-tunnel.service hp-ble-proxy.service
```

Remove only the temporary ESPHome bridge entry if it is no longer needed. Keep
the Xiaomi device entries, entities and existing automations. Treat the receiver's
other DNS and network responsibilities separately before powering it off.
