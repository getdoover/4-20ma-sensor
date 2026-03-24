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

<br/>

## Integrations

### Tags

This app exposes the following tags for integration with other apps:

| Tag | Description |
|-----|-------------|
| `value` | The filtered sensor reading in configured units |
| `raw_value` | The raw unfiltered sensor reading |

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

### v1.0.0 (Current)
- Initial release

<br/>

## License

This app is licensed under the [Apache License 2.0](https://github.com/getdoover/4-20ma-sensor/blob/main/LICENSE).
