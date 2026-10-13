# Weiguang · 微光

[简体中文](README.md) | English

A quiet StackChan desk companion for coding: glance at active Codex tasks, spot a question waiting for you, pet its head, and settle into a focus session.

Firmware + a local Mac bridge + a native control panel. Task sync works over USB or Bluetooth without office Wi-Fi or cloud model calls. This independent project is not affiliated with M5Stack or OpenAI.

**v0.46 experimental build.** Deployed on the development device. Mac send/dismiss/restore, on-device layout and note persistence across a device reboot have been checked. Manual hold gestures, more devices and long-running use still need hands-on feedback.

<img src="docs/screenshots/robot-note.png" width="480" alt="Actual robot display showing a cat face and a sample sticky note" />

An actual device framebuffer capture, not a concept render or a photo of the physical robot.

<details>
<summary>Focus setup and native Mac console</summary>

<img src="docs/screenshots/robot-focus-ready.png" width="480" alt="Actual focus setup page" />
<img src="docs/screenshots/mac-console.png" width="620" alt="Actual native Mac console" />

</details>

A separate [timer render preview](docs/preview/focus.png) uses the actual drawing code with sample time data.

## Features

- Up to eight recently active local Codex conversations, with running / waiting / completed / interrupted states and short progress excerpts.
- Silent amber waiting indicators. Hold the waiting card for about 0.9 seconds to ask the Mac to open the conversation, without waiting for release; no automatic reply.
- Default and cat faces, blush on head touch, optional small nods, slow blinks and closed-eye rest without dimming.
- An immersive 15/25/45-minute timer, a remaining-time ring and a five-minute break. The next focus round starts manually. Waiting indicators never pause the timer.
- Daily focus time and completed rounds stored on the device. Pauses and breaks are excluded.
- One short sticky note, up to 32 Unicode scalar values, edited on the Mac, shown on a warm yellow paper card with a folded corner, and dismissed by a hold on the robot; Mac operations and device persistence have been checked.
- Shared settings on Mac and device, local persistence, reconnect handling and user-level login startup.

## Requirements and setup

Development target: **M5Stack StackChan K151 / CoreS3 / ESP32-S3 with 16 MB Flash**, macOS 12+, Python 3.9+, Xcode Command Line Tools and a USB data cable. The app UI is primarily Chinese. Other boards are not verified.

This replaces the stock application. Stock voice / AI Agent mode is not included. Back up **your own** complete factory Flash, partition table and calibration before flashing. No signed or notarized Mac installer or prebuilt firmware is distributed yet.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install platformio==6.2.0
.venv/bin/python -m pip install --no-index --require-hashes -r bridge/requirements.txt --find-links bridge/wheels
.venv/bin/pio run
python3 macos/build.py
python3 macos/build_icon.py
python3 macos/build_panel.py
```

The first firmware build downloads pinned dependencies. Native build scripts create universal development binaries with ad-hoc local signatures, not a notarized release. Read [hardware notes](docs/HARDWARE.md) before flashing: the development device updates only its application at `0x10000`, preserving partitions, NVS and servo calibration. Do not blindly run a full PlatformIO upload or erase Flash on an unknown factory layout.

After installing compatible firmware, connect the robot over USB:

```sh
./weiguang install
./weiguang status
./weiguang panel
./weiguang bind-bluetooth
```

Allow Bluetooth access for the helper when macOS asks. No sudo is needed. `pause` / `resume` manage task sync. Tap the home screen for tasks; swipe to browse. Tap the focus screen to show controls: Exit returns home while the timer continues, End cancels the cycle. Head-pet and focus-end motion have separate switches; ordinary task notification motion is off by default.

## Data and limitations

The bridge reads local Codex task files; it does not send them to a server. Task titles and excerpts are transmitted to the paired robot and appear on its screen. Bluetooth uses a USB-provisioned key with application-layer AES-256-GCM, per-connection derived keys and replay checks; the implementation has not had an independent security audit. See [privacy details](docs/PRIVACY.md).

Task tracking depends on evolving local Codex formats rather than a stable API. Hardware validation covers one development device. Automated checks do not establish long-term reliability, every firmware layout or physical backup restoration. Manual hold-gesture feel is not claimed as verified. Existing counters cannot reconstruct focus sessions from older firmware.

[Development](docs/DEVELOPMENT.md) · [Daily use](DAILY_USE.md) · [Migration](MIGRATION.md) · [Changelog](CHANGELOG.md) · [Third-party notices](THIRD_PARTY.md)

## License

Original code: [MIT](LICENSE). Bundled drivers and pyserial retain their own licenses. Firmware dependencies are fetched during the build.
