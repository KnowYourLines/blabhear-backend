import asyncio
import logging

import phonenumbers
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from blabhear.exceptions import UserNotAllowedError
from blabhear.models import User, Room

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
            if content.get("command") == "fetch_registered_contacts":
                asyncio.create_task(self.fetch_registered_contacts(content))

    async def fetch_registered_contacts(self, input_payload):
        phone_contacts = input_payload["phone_contacts"]
        valid_phone_numbers = []
        for contact in phone_contacts:
            if contact["phoneNumbers"]:
                phone_number = next(
                    (
                        number["number"]
                        for number in contact["phoneNumbers"]
                        if number["label"] == "mobile"
                    ),
                    contact["phoneNumbers"][0]["number"],
                )
                phone_number = phonenumbers.parse(
                    phone_number, self.user.alpha2_country_code
                )
                if phonenumbers.is_valid_number(phone_number):
                    phone_number = phonenumbers.format_number(
                        phone_number, phonenumbers.PhoneNumberFormat.E164
                    )
                    valid_phone_numbers.append(phone_number)
        registered_contacts = await database_sync_to_async(
            self.find_users_by_phone_numbers
        )(valid_phone_numbers)
        await self.channel_layer.send(
            self.channel_name,
            {"type": "registered_contacts", "registered_contacts": registered_contacts},
        )

    def find_users_by_phone_numbers(self, phone_numbers):
        users = (
            User.objects.filter(phone_number__in=phone_numbers)
            .exclude(phone_number=self.user.phone_number)
            .values("phone_number", "display_name")
            .order_by("display_name")
        )
        return list(users)

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

    async def registered_contacts(self, event):
        # Send message to WebSocket
        await self.send_json(event)


class RoomConsumer(AsyncJsonWebsocketConsumer):
    def get_room(self, room_id):
        room, created = Room.objects.get_or_create(id=room_id)
        if created:
            room.members.add(self.user)
            return room
        else:
            user_allowed = self.user_allowed()
            if user_allowed:
                return room
            else:
                raise UserNotAllowedError("User is not a member of the room")

    def user_allowed(self):
        room = Room.objects.filter(id=self.room_id)
        if room.exists():
            room = room.first()
            return self.user in room.members.all()
        else:
            return False

    async def connect(self):
        await self.accept()
        self.user = self.scope["user"]

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(str(self.room_id), self.channel_name)

    async def initialize_room(self):
        await self.channel_layer.group_add(self.room_id, self.channel_name)
        room = await database_sync_to_async(self.get_room)(self.room_id)

    async def receive_json(self, content, **kwargs):
        if content.get("command") == "connect":
            self.room_id = content.get("room")
            await self.initialize_room()
        if content.get("command") == "disconnect":
            await self.channel_layer.group_discard(str(self.room_id), self.channel_name)
