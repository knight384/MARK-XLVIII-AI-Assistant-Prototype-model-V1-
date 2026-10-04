from enum import Enum

class ModelTier(str, Enum):
    FAST = "fast"
    STANDARD = "standard"
    REASONING = "reasoning"
    CODING = "coding"
    VISION = "vision"
    REALTIME = "realtime"
    EMBEDDING = "embedding"
    LOCAL = "local"
