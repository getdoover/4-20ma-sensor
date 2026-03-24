from pydoover.docker import run_app

from .application import Sensor420maApplication


def main():
    """
    Run the application.
    """
    run_app(Sensor420maApplication())
