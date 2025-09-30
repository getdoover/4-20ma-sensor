"""
Basic tests for an application.

This ensures all modules are importable and that the config is valid.
"""

def test_import_app():
    from sensor_4_20ma.application import Sensor420maApplication
    assert Sensor420maApplication

def test_config():
    from sensor_4_20ma.app_config import Sensor420maConfig

    config = Sensor420maConfig()
    assert isinstance(config.to_dict(), dict)

def test_ui():
    from sensor_4_20ma.app_ui import Sensor420maUI
    assert Sensor420maUI