from pathlib import Path

from pydoover import config

from .alarm import AlarmType


def _optional_value(element):
    """The element's value, or None when it was left blank.

    Sub-elements of an optional Object that was left out stay unset, and an
    unset element with no default raises on ``.value``.
    """
    try:
        return element.value
    except ValueError:
        return None


class OptionalTagRef(config.TagRef):
    """A TagRef that forgets its previous values when loaded blank.

    pydoover skips loading an optional Object sent as null or {}, leaving its
    fields as they were, and config elements are shared between instances of
    a schema. Without this, a blank tag would keep the last loaded one.
    """

    def load_data(self, data):
        if not data:
            for element in self._elements.values():
                element._value = config.NotSet
        super().load_data(data)


class AlarmConfig(config.Object):
    alarm_enabled = config.Boolean(
        "Alarm Enabled",
        default=False,
        description="Send a notification when the reading crosses the alarm point",
    )
    alarm_type = config.Enum(
        "Alarm Type",
        choices=AlarmType,
        default=AlarmType.greater_than,
        description=(
            "Greater Than and Less Than alarm on a single point. Allowed Range "
            "alarms when the reading falls outside a low/high band."
        ),
    )
    slider_min = config.Number(
        "Alarm Slider Minimum",
        default=None,
        description="Lower bound of the alarm point slider. Defaults to Min Range.",
    )
    slider_max = config.Number(
        "Alarm Slider Maximum",
        default=None,
        description="Upper bound of the alarm point slider. Defaults to Max Range.",
    )
    grace_period = config.Number(
        "Alarm Grace Period (s)",
        default=30.0,
        description="How long the reading must stay out of bounds before notifying",
        minimum=0.0,
    )
    renotify_interval = config.Number(
        "Alarm Re-notify Interval (s)",
        default=900.0,
        description=(
            "How often to re-notify while the alarm remains active. 0 sends one "
            "notification per alarm and never re-notifies."
        ),
        minimum=0.0,
    )
    default_low = config.Number(
        "Default Low Setpoint",
        name="default_low",
        default=None,
        description=(
            "Low setpoint used until an operator moves the alarm slider (Less "
            "Than, and the low end of Allowed Range). Leave blank for none."
        ),
    )
    default_high = config.Number(
        "Default High Setpoint",
        name="default_high",
        default=None,
        description=(
            "High setpoint used until an operator moves the alarm slider "
            "(Greater Than, and the high end of Allowed Range). Leave blank for "
            "none."
        ),
    )
    enable_tag = OptionalTagRef(
        "Alarm Enable Tag",
        name="alarm_enable_tag",
        default=None,
        required=False,
        description=(
            "Only alarm while this tag (e.g. another app's engine RPM) is above "
            "the Alarm Enable Threshold. Leave blank to always alarm."
        ),
        # Read directly by the app rather than through a RemoteTag, so the
        # local handle and the cross-agent picker are not needed.
        reference_name__default="alarm_enable",
        reference_name__hidden=True,
        agent_id__hidden=True,
    )
    enable_threshold = config.Number(
        "Alarm Enable Threshold",
        name="alarm_enable_threshold",
        default=0.0,
        description=(
            "The alarm is armed while the Alarm Enable Tag is above this value. "
            "A true/false tag arms on true with the default of 0."
        ),
    )
    enable_delay = config.Number(
        "Alarm Enable Delay (s)",
        name="alarm_enable_delay_s",
        default=0.0,
        minimum=0.0,
        description=(
            "How long the Alarm Enable Tag must stay above the threshold before "
            "the alarm is armed, e.g. to let pressure build after a start."
        ),
    )
    disarmed_reason = config.String(
        "Alarm Disarmed Reason",
        name="alarm_disarmed_reason",
        default=None,
        description=(
            "Shown in the UI while the alarm is disarmed by the Alarm Enable "
            "Tag, e.g. 'engine stopped'. Defaults to the tag and threshold."
        ),
    )


class Sensor420maConfig(config.Schema):
    ai_pin = config.Integer(
        "AI Pin Number",
        default=0,
        description="The analog input pin number for the 4-20mA sensor",
        minimum=0,
        maximum=15,
    )
    input_name = config.String(
        "Input Name",
        description="Name for the Input that appears in the UI e.g. Tank Vol (L)",
    )
    min_range = config.Number(
        "Min Range",
        default=0.0,
        description="The physical value corresponding to 4mA signal (minimum sensor reading)",
    )
    max_range = config.Number(
        "Max Range",
        default=100.0,
        description="The physical value corresponding to 20mA signal (maximum sensor reading)",
    )
    measurement_units = config.String(
        "Measurement Units",
        default=None,
        description="The units for the sensor measurement (e.g., %, °C, PSI, etc.)",
    )
    signal_filter_enabled = config.Boolean(
        "Enable Signal Filtering",
        default=True,
        description="Enable digital filtering to smooth out sensor readings",
    )
    process_variance = config.Number(
        "Process Variance",
        default=0.5,
        description="The process variance for the Kalman Filter running on the input",
    )
    measurement_variance = config.Number(
        "Measurement Variance",
        default=0.5,
        description="The measurement variance for the Kalman Filter running on the input",
    )
    sample_rate = config.Number(
        "Sample Rate (Hz)",
        default=2.0,
        description="The sample rate in Hz for the main loop",
        minimum=0.1,
        maximum=5.0,
    )
    alarm = AlarmConfig("Alarm", description="Alarm configuration")
    sensor_fault_alarm_enabled = config.Boolean(
        "Sensor Fault Alarm Enabled",
        name="sensor_fault_alarm_enabled",
        default=False,
        description=(
            "Notify when the loop current stays below 3.5 mA (broken wire or "
            "failed transmitter) for the Alarm Grace Period"
        ),
    )
    operator_calibration_enabled = config.Boolean(
        "Operator Sensor Calibration",
        name="operator_calibration_enabled",
        default=False,
        description=(
            "Let operators adjust Range Low, Range High and an Offset from the "
            "Sensor Calibration panel and the local HMI. Min Range and Max "
            "Range stay the defaults, and Reset puts them back."
        ),
    )

    @property
    def alarm_type(self) -> AlarmType:
        # config.Enum stringifies its default but maps injected values back to
        # members, so .value is a member or a str depending on whether the
        # deployment config was injected. Normalise to a member either way.
        value = self.alarm.alarm_type.value
        return value if isinstance(value, AlarmType) else AlarmType(value)

    @property
    def alarm_slider_min(self) -> float:
        value = self.alarm.slider_min.value
        return self.min_range.value if value is None else value

    @property
    def alarm_slider_max(self) -> float:
        value = self.alarm.slider_max.value
        return self.max_range.value if value is None else value

    @property
    def alarm_default_point(self) -> float | None:
        """The configured setpoint for the single-sided modes, if any."""
        if self.alarm_type is AlarmType.greater_than:
            return self.alarm.default_high.value
        if self.alarm_type is AlarmType.less_than:
            return self.alarm.default_low.value
        return None

    @property
    def alarm_default_range(self) -> list[float] | None:
        """The configured [low, high] for Allowed Range, if either is set.

        A side left blank takes the slider's end, which is what the dual
        slider shows for it.
        """
        low = self.alarm.default_low.value
        high = self.alarm.default_high.value
        if low is None and high is None:
            return None
        return [
            self.alarm_slider_min if low is None else low,
            self.alarm_slider_max if high is None else high,
        ]

    @property
    def alarm_enable_tag(self) -> tuple[str, str] | None:
        """(app_key, tag_name) of the alarm gate tag, or None when not set."""
        ref = self.alarm.enable_tag
        app_key = _optional_value(ref.app_name)
        tag_name = _optional_value(ref.tag_name)
        if not app_key or not tag_name:
            return None
        return app_key, tag_name

    @property
    def alarm_disarmed_text(self) -> str:
        reason = self.alarm.disarmed_reason.value
        if not reason:
            app_key, tag_name = self.alarm_enable_tag or ("", "")
            threshold = self.alarm.enable_threshold.value
            reason = f"{app_key}.{tag_name} not above {threshold:g}"
        return f"Alarm disarmed ({reason})"


def export():
    Sensor420maConfig.export(Path(__file__).parents[2] / "doover_config.json", "4_20ma_sensor")
