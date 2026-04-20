import asyncio
import logging

logger = logging.getLogger("wzml.core.events")

class EventBus:
    def __init__(self):
        self.subscribers = []

    def subscribe(self, queue: asyncio.Queue):
        self.subscribers.append(queue)
        logger.debug(f"EventBus: New subscriber. Total: {len(self.subscribers)}")

    def unsubscribe(self, queue: asyncio.Queue):
        if queue in self.subscribers:
            self.subscribers.remove(queue)
            logger.debug(f"EventBus: Subscriber removed. Total: {len(self.subscribers)}")

    async def publish(self, event_type: str, data: dict):
        for queue in self.subscribers:
            try:
                await queue.put({"type": event_type, "data": data})
            except Exception as e:
                logger.error(f"EventBus: Failed to publish to a subscriber: {e}")

event_bus = EventBus()
