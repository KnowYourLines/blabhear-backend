import asyncio
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

logger = logging.getLogger(__name__)


class UserConsumer(AsyncJsonWebsocketConsumer):
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
            if content.get("command") == "update_display_name":
                asyncio.create_task(self.update_display_name(content))

    async def fetch_display_name(self):
        display_name = self.user.display_name
        await self.channel_layer.send(
            self.channel_name,
            {"type": "display_name", "display_name": display_name},
        )

    def change_display_name(self, new_name):
        self.user.display_name = new_name
        self.user.save()
        return new_name

    async def update_display_name(self, input_payload):
        if len(input_payload["name"].strip()) > 0:
            display_name = await database_sync_to_async(self.change_display_name)(
                input_payload["name"]
            )
            await self.channel_layer.send(
                self.channel_name,
                {"type": "display_name", "display_name": display_name},
            )
        else:
            await self.fetch_display_name()

    async def display_name(self, event):
        # Send message to WebSocket
        await self.send_json(event)
