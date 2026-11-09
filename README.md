# 4-20mA Sensor

<!-- ![Doover Logo](https://doover.com/wp-content/uploads/Doover-Logo-Landscape-Navy-padded-small.png) -->
<img src="https://doover.com/wp-content/uploads/Doover-Logo-Landscape-Navy-padded-small.png" alt="App Icon" style="max-width: 300px;">

**Convert a 4-20mA signal to a value in the UI.**

**Provide units, measuring range, an analogue input and some ranges to get an analogue value and a loading bar in your UI.**

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/getdoover/4-20ma-sensor)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/getdoover/4-20ma-sensor/blob/main/LICENSE)

[Configuration](#configuration) | [Developer](https://github.com/getdoover/4-20ma-sensor/blob/main/DEVELOPMENT.md) | [Need Help?](#need-help)

<br/>

## Overview

Convert a 4-20mA signal to a value in the UI. Provide units, measuring range, an analogue input and some ranges to get an analogue value and a loading bar in your UI.

<br/>

## Configuration

| Setting | Description | Default |
|---------|-------------|---------|
| **AI Pin Number** | The analog input pin number for the 4-20mA sensor | `0` |
| **Input Name** | Name for the input that appears in the UI | `Required` |
| **Min Range** | The physical value corresponding to 4mA signal | `0.0` |
| **Max Range** | The physical value corresponding to 20mA signal | `100.0` |
| **Measurement Units** | Units for the sensor measurement | `None` |
| **Enable Signal Filtering** | Enable digital filtering to smooth readings | `true` |
| **Operator Sensor Calibration** | Let operators adjust Range Low, Range High and an Offset on site (see below) | `false` |
| **Sensor Fault Alarm Enabled** (`sensor_fault_alarm_enabled`) | Notify when the loop current stays below 3.5 mA (broken wire or failed transmitter) for the Alarm Grace Period. Uses the alarm's grace period and re-notify interval | `false` |

### Alarm

All of these sit under **Alarm** (`alarm`). Every setting below **Alarm Re-notify Interval** is optional and off when left blank, so existing installs behave exactly as before.

| Setting | Description | Default |
|---------|-------------|---------|
| **Alarm Enabled** (`alarm_enabled`) | Send a notification when the reading crosses the alarm setpoint | `false` |
| **Alarm Type** (`alarm_type`) | `Greater Than`, `Less Than` (single setpoint) or `Allowed Range` (low/high band) | `Greater Than` |
| **Alarm Slider Minimum / Maximum** (`alarm_slider_minimum`, `alarm_slider_maximum`) | Ends of the setpoint slider | Min / Max Range |
| **Alarm Grace Period (s)** (`alarm_grace_period_s`) | How long the reading must stay out of bounds before notifying | `30` |
| **Alarm Re-notify Interval (s)** (`alarm_renotify_interval_s`) | How often to re-notify while the alarm stays active. **`0` (or less) means notify once per alarm and never re-notify** | `900` |
| **Default Low Setpoint** (`default_low`) | Low setpoint used until an operator moves the slider (Less Than, and the low end of Allowed Range) | blank |
| **Default High Setpoint** (`default_high`) | High setpoint used until an operator moves the slider (Greater Than, and the high end of Allowed Range) | blank |
| **Alarm Enable Tag** (`alarm_enable_tag`) | Only alarm while this tag (an app install and tag name, e.g. `kensho_controller_1` / `engine_rpm`) is above the threshold. Blank = always alarm | blank |
| **Alarm Enable Threshold** (`alarm_enable_threshold`) | The alarm is armed while the tag is above this value. A true/false tag arms on `true` with the default | `0` |
| **Alarm Enable Delay (s)** (`alarm_enable_delay_s`) | How long the tag must stay above the threshold before the alarm is armed (e.g. let pressure build after a start) | `0` |
| **Alarm Disarmed Reason** (`alarm_disarmed_reason`) | Shown in the UI while disarmed, as "Alarm disarmed (<reason>)", e.g. `engine stopped`. Defaults to the tag and threshold | blank |

**Setpoints.** Operators set the alarm point (or the allowed range) with the slider on the dashboard. Until a slider has been moved, the app uses **Default Low / High Setpoint**, and the slider shows them. Once an operator moves the slider, the slider wins. With neither set, the alarm stays quiet until an operator sets the slider, as before.

**Alarm gate.** With an **Alarm Enable Tag**, the alarm is only evaluated while that tag is above **Alarm Enable Threshold**, and only once it has stayed there for **Alarm Enable Delay**. Any dip below restarts the delay. A missing or non-numeric tag value counts as below the threshold. While disarmed, an active alarm is cleared without a notification, and after re-arming a breach serves its full grace period again. An **Alarm Status** row shows `Alarm armed`, `Alarm arming (N s delay)` or `Alarm disarmed (...)`. The tag must be on the same device.

Example: only alarm on gland water pressure while the engine is running, 30 s after it starts:

```json
"alarm": {
  "alarm_enabled": true,
  "alarm_type": "Allowed Range",
  "default_low": 2.0,
  "default_high": 10.0,
  "alarm_enable_tag": {"app_name": "kensho_controller_1", "tag_name": "engine_rpm"},
  "alarm_enable_threshold": 300.0,
  "alarm_enable_delay_s": 30.0,
  "alarm_disarmed_reason": "engine stopped"
}
```

### Operator Sensor Calibration

With **Operator Sensor Calibration** on, a **Sensor Calibration** panel lets an operator set, without a redeploy:

- **Range Low** - the value at 4 mA (defaults to Min Range)
- **Range High** - the value at 20 mA (defaults to Max Range)
- **Offset** - added after scaling (defaults to 0)

A change applies to the next reading. **Reset to configured values** clears the operator values, so all three go back to the configuration and keep following it: if Min Range or Max Range is changed later, the new value takes effect (and shows in the panel) without pressing Reset again. A value an operator sets, even one equal to the configured value, stays until the next Reset. The same settings are RPCs on `ui_cmds` (`range_low`, `range_high`, `offset`, `reset_calibration`), so a local HMI can set them too. Range High must be above Range Low and the offset within +/- the range; anything else is refused with `INVALID`. With the setting off the panel is hidden, the RPCs are refused with `UNAVAILABLE` and the app behaves exactly as before. Like the other settings, switching it on or off takes effect when the app next starts.

<br/>

## Integrations

### Tags

This app exposes the following tags for integration with other apps:

| Tag | Description |
|-----|-------------|
| `value` | The filtered sensor reading in configured units |
| `raw_value` | The loop current in mA, unfiltered |
| `unfiltered_value` | The unfiltered reading in configured units (with signal filtering on) |
| `range_low`, `range_high`, `offset` | The operator calibration in effect (only with Operator Sensor Calibration on) |
| `operator_calibration` | `true` while Operator Sensor Calibration is on |
| `alarm_armed`, `alarm_status` | Whether the alarm gate is armed, and the status text (only with an Alarm Enable Tag) |
| `sensor_fault`, `sensor_status` | Whether the loop current is below 3.5 mA, and the status text (only with the Sensor Fault Alarm on) |

### Notifications

| Notification | Sent when |
|--------------|-----------|
| **Alarm** | The reading crosses its setpoint for the grace period, and on each re-notify interval while it stays there |
| **Sensor Fault** | The loop current stays below 3.5 mA for the grace period (Sensor Fault Alarm on), and on each re-notify interval |

<br/>
This is a standalone app with no dependencies on other Doover apps.

<br/>

## Need Help?

- Email: support@doover.com
- [Community Forum](https://doover.com/community)
- [Full Documentation](https://docs.doover.com)
- [Developer Documentation](https://github.com/getdoover/4-20ma-sensor/blob/main/DEVELOPMENT.md)

<br/>


## Version History

### Unreleased
- Optional alarm gate: only alarm while another app's tag (e.g. engine RPM) is above a threshold, after a delay.
- Optional default low/high setpoints, used until an operator moves the alarm slider.
- Optional sensor fault alarm when the loop current stays below 3.5 mA.
- **Behaviour change:** an Alarm Re-notify Interval of `0` now means "never re-notify". It used to re-notify on every sample.

### v1.0.0
- Initial release

<br/>

## License

This app is licensed under the [Apache License 2.0](https://github.com/getdoover/4-20ma-sensor/blob/main/LICENSE).