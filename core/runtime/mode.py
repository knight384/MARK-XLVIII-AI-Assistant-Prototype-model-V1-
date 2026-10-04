from enum import Enum, auto

class RuntimeMode(Enum):
    DESKTOP = auto()
    HEADLESS = auto()
    LOCAL = auto()
    DOCKER = auto()
    CLOUD = auto()
    HYBRID = auto()
