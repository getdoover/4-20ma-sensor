"""
Basic tests for an application.

This ensures all modules are importable and that the config is valid.
"""

def test_import_app():
    from 4_20ma_sensor.application import 420maSensorApplication
    assert 420maSensorApplication

def test_config():
    from 4_20ma_sensor.app_config import 420maSensorConfig

    config = 420maSensorConfig()
    assert isinstance(config.to_dict(), dict)

def test_ui():
    from 4_20ma_sensor.app_ui import 420maSensorUI
    assert 420maSensorUI

def test_state():
    from 4_20ma_sensor.app_state import 420maSensorState
    assert 420maSensorState