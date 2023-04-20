import logging
from channels.generic.websocket import AsyncJsonWebsocketConsumer

logger = logging.getLogger(__name__)


class UserConsumer(AsyncJsonWebsocketConsumer):
    async def fetch_display_name(self):
        display_name = self.user.display_name
        await self.channel_layer.send(
            self.channel_name,
            {"type": "display_name", "display_name": display_name},
        )

    async def connect(self):
        self.username = str(self.scope["url_route"]["kwargs"]["user_id"])
        self.user = self.scope["user"]
        if self.username == self.user.username:
            await self.channel_layer.group_add(self.username, self.channel_name)
            await self.accept()
            await self.fetch_display_name()
        else:
            await self.close()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.username, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if self.username == self.user.username:
            pass

    async def display_name(self, event):
        # Send message to WebSocket
        await self.send_json(event)
