"""
Basic tests for an application.

This ensures all modules are importable and that the config is valid.
"""


def test_import_app():
    from sensor_4_20ma.application import Sensor420maApplication

    assert Sensor420maApplication
    assert Sensor420maApplication.config_cls is not None
    assert Sensor420maApplication.tags_cls is not None
    assert Sensor420maApplication.ui_cls is not None


def test_config():
    from sensor_4_20ma.app_config import Sensor420maConfig

    schema = Sensor420maConfig.to_schema()
    assert isinstance(schema, dict)
    assert len(schema["properties"]) > 0


def test_tags():
    from sensor_4_20ma.app_tags import Sensor420maTags

    assert Sensor420maTags


def test_ui():
    from sensor_4_20ma.app_ui import Sensor420maUI
    from pydoover.ui import UI

    assert issubclass(Sensor420maUI, UI)