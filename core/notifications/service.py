import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

class NotificationPriority(Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3

@dataclass
class Notification:
    id: str
    category: str
    message: str
    priority: NotificationPriority
    timestamp: float = field(default_factory=time.time)
    security_filtered: bool = False
    delivered: bool = False

class NotificationService:
    """
    MARK-native Notification Service with pluggable destinations.
    Implements cooldowns, frequency limits, quiet hours, and priority handling.
    """
    def __init__(self):
        self.history: List[Notification] = []
        self._last_delivery_by_category: Dict[str, float] = {}
        # Simple configuration
        self.quiet_hours_start = 22 # 10 PM
        self.quiet_hours_end = 8    # 8 AM
        self.cooldown_ms = 60000    # 1 minute default cooldown

    def notify(self, category: str, message: str, priority: NotificationPriority = NotificationPriority.NORMAL) -> bool:
        """
        Generates and attempts to deliver a notification.
        Separates Generation from Delivery.
        """
        now = time.time()
        
        # 1. Cooldown & Frequency Check (unless URGENT)
        if priority != NotificationPriority.URGENT:
            last_time = self._last_delivery_by_category.get(category, 0)
            if (now - last_time) * 1000 < self.cooldown_ms:
                logger.debug(f"[NotificationService] Suppressed {category} notification due to cooldown.")
                return False

        # 2. Quiet Hours Check (unless HIGH/URGENT)
        if priority in (NotificationPriority.LOW, NotificationPriority.NORMAL):
            hour = time.localtime(now).tm_hour
            # Simple boundary check
            if self.quiet_hours_start <= hour or hour < self.quiet_hours_end:
                logger.debug(f"[NotificationService] Suppressed {category} notification due to quiet hours.")
                return False

        # 3. Security filtering (mock implementation for Phase 9)
        # Security-sensitive data must not leak into unauthorized notification destinations
        security_filtered = "[REDACTED]" in message

        notif = Notification(
            id=str(time.time()),
            category=category,
            message=message,
            priority=priority,
            security_filtered=security_filtered
        )
        self.history.append(notif)
        
        # 4. Delivery
        delivered = self._deliver(notif)
        if delivered:
            self._last_delivery_by_category[category] = now
            notif.delivered = True
            
        return delivered

    def _deliver(self, notification: Notification) -> bool:
        """
        Internal delivery logic. Currently supports desktop/runtime path.
        Pluggable destinations can be added here in the future (Telegram, Discord, etc).
        """
        # Phase 9: desktop/runtime notification path
        logger.info(f"[NOTIFICATION - {notification.priority.name}] [{notification.category}] {notification.message}")
        return True

_default_service: Optional[NotificationService] = None

def get_notification_service() -> NotificationService:
    global _default_service
    if _default_service is None:
        _default_service = NotificationService()
    return _default_service
