from pydoover.docker import run_app

from .application import Sensor420maApplication
from .app_config import Sensor420maConfig

def main():
    """
    Run the application.
    """
    run_app(Sensor420maApplication(config=Sensor420maConfig()))
