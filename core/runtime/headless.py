import logging

logger = logging.getLogger(__name__)

class HeadlessUI:
    """A mock UI for running JarvisLive in headless mode."""
    def __init__(self):
        self.muted = False
        self.on_text_command = None
        self.on_remote_clicked = None
        self.on_interrupt = None
        self._state = "SLEEPING"
        
        # mock window object for wait_for_api_key loop
        class DummyWin:
            _ready = True
        self._win = DummyWin()
        self.root = None
        
    def write_log(self, msg: str):
        logger.info(f"[Headless] {msg}")
        
    def set_state(self, state: str):
        self._state = state
        logger.debug(f"[Headless] State -> {state}")
        
    def prompt_reconfig(self):
        logger.error("[Headless] API Key invalid. Cannot prompt in headless mode.")
        
    def wait_for_api_key(self):
        # We assume the key is in the env or config already.
        pass
        
    def notify_phone_connected(self):
        logger.info("[Headless] Phone connected.")
        
    def stop_camera_stream(self):
        pass
