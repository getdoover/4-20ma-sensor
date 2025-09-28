from pydoover.docker import run_app

from .application import 420maSensorApplication
from .app_config import 420maSensorConfig

def main():
    """
    Run the application.
    """
    run_app(420maSensorApplication(config=420maSensorConfig()))
