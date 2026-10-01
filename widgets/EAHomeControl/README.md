# Home Control

Touch control for Home Assistant devices on the Xeneon Edge. Connects straight to
Home Assistant's WebSocket API; no companion server.

## Setup

1. In Home Assistant, open your profile > Security and create a long-lived access token.
2. Create a label (default name `xeneon`) and add it to the devices or entities to show.
   A labeled device contributes its main entities; labeling an entity adds just that entity.
3. In the widget settings, set the Home Assistant URL (e.g. `http://homeassistant.local:8123`)
   and paste the token.

Enter `demo` as the URL to try the widget with a fake house.

## Controls

- Tap: toggle lights, switches, fans, covers; play/pause media; run scenes, scripts and buttons.
- Locks: tap locks immediately; unlocking needs a second tap within 3 seconds.
- Press and hold any tile for its detail panel (brightness, fan speed, cover position,
  thermostat set point and mode, media transport and volume, sensor details).

Tiles follow Home Assistant live. Adding or removing the label updates the widget without a restart.

## Notes

- The token is stored in iCUE's widget settings as plain text. Use a token made only for this widget;
  you can revoke it in Home Assistant at any time.
- The token is only ever sent to the Home Assistant URL you enter.
