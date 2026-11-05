# Native dashboard header

The home dashboard uses a native Markdown header and two entity badges. The
header combines a time-aware greeting and a localized date. The badges show home
status and device activity. Room temperatures remain in their existing climate
cards; room links and phone/presence badges are omitted from the header by user
preference. Existing sections, other views, themes and control actions are
preserved.

Optional display-only phone template sensors retain guarded missing-data labels,
but are not displayed in the current header. Keep the original person and mobile
entities as the source of truth if those helpers are reused elsewhere.

## State handling

- Known presence is translated into a readable home/away label. Missing presence
  displays a waiting label and a neutral icon.
- A numeric battery value is displayed as a percentage, with a corresponding
  battery or charging icon. Missing battery data displays a waiting label.
- The active-device count remains numeric. A separate `summary` attribute supplies
  the badge's label, including the correct singular or plural form. The badge
  uses `state_content: summary`.
- Off, standby, unknown and unavailable devices are excluded from the activity
  count. Use current registered entity IDs for its explicit device list.
- Missing room temperatures display a dash; never substitute zero.

Display fallback states must not be written to the original person, tracker or
numeric mobile sensor. They do not establish someone's location or invent a
battery reading. Existing control and notification automations retain their
original source entities.

## Mobile sensors

Check both the server entity registry and the Companion app's sensor settings.
The app can register a sensor as disabled again after it is enabled on the
server. In that case, enable Battery Level and Battery State in the phone's
Companion app sensor settings. Presence also requires the app to supply a valid
location with the corresponding operating-system permission.

A single supported refresh request can check the existing app connection.
Repeated polling or a fabricated tracker state is not a remedy for disabled
phone sensors. Keep diagnostic exports and device details in private storage.

## Validation and rollback

1. Back up the original dashboard, template YAML and relevant registry records
   before editing. Keep the backup outside Git with restricted permissions.
2. Render all new templates through Home Assistant's template endpoint, including
   the header's user context and missing-data cases.
3. Run Home Assistant's configuration check before reloading templates.
4. Force-load the YAML dashboard through the native Lovelace API; confirm that
   both displayed badge entities exist and preserve the original sections and views.
5. Check the rendered activity summary and the unchanged source tracker state.
6. Refresh the client to pick up the new header.

To roll back, restore the backed-up dashboard and template files, reload the
template integration, and force-load or refresh the dashboard. Restore registry
settings only if they were changed independently of the phone's own settings.

No custom frontend resources or additional card plugins are required.

## Phone onboarding and local DNS

A phone can discover the server but fail to open the advertised internal URL if
its DNS resolver cannot resolve a custom local hostname. Check the error details
before changing credentials. Verify the direct LAN endpoint and the server's
internal URL separately.

Where necessary, use the server's stable numeric LAN address as its internal URL,
leaving the external URL and reverse-proxy routes intact. Back up the core
configuration before changing it. Verify both the stored URL and the mDNS
`internal_url` / `base_url` properties. A controlled Home Assistant restart can be
needed to publish the new discovery properties.

On an affected phone, close the failed onboarding sheet and select the server
again, or enter its complete internal address manually. The app still needs local
network permission. This change does not configure access from outside the LAN.
