import asyncio
import logging
from operator import itemgetter

import phonenumbers
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from blabhear.exceptions import UserNotAllowedError
from blabhear.models import User, Room, UserRoomNotification

logger = logging.getLogger(__name__)


class UserConsumer(AsyncJsonWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(args, kwargs)
        self.user = None
        self.username = None

    async def connect(self):
        self.username = str(self.scope["url_route"]["kwargs"]["user_id"])
        self.user = self.scope["user"]
        if self.username == self.user.username:
            await self.channel_layer.group_add(self.username, self.channel_name)
            await self.accept()
            await self.fetch_display_name()
            await self.fetch_notifications()
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
        await self.channel_layer.group_send(
            self.username,
            {"type": "display_name", "display_name": display_name},
        )

    def change_display_name(self, new_name):
        self.user.display_name = new_name
        self.user.save()
        return new_name

    def get_notifications(self):
        notifications = list(
            self.user.userroomnotification_set.values(
                "room",
                "room__display_name",
                "timestamp",
            ).order_by("room", "-timestamp")
        )
        notifications.sort(key=itemgetter("timestamp"), reverse=True)
        for notification in notifications:
            notification["room"] = str(notification["room"])
            notification["timestamp"] = notification["timestamp"].strftime(
                "%d-%m-%Y %H:%M:%S"
            )
        return notifications

    async def update_display_name(self, input_payload):
        if len(input_payload["name"].strip()) > 0:
            display_name = await database_sync_to_async(self.change_display_name)(
                input_payload["name"].strip()
            )
            await self.channel_layer.group_send(
                self.username,
                {"type": "display_name", "display_name": display_name},
            )
        else:
            await self.fetch_display_name()

    async def fetch_notifications(self):
        notifications = await database_sync_to_async(self.get_notifications)()
        await self.channel_layer.group_send(
            self.username,
            {
                "type": "notifications",
                "notifications": notifications,
            },
        )

    async def notifications(self, event):
        # Send message to WebSocket
        await self.send_json(event)

    async def display_name(self, event):
        # Send message to WebSocket
        await self.send_json(event)

    async def registered_contacts(self, event):
        # Send message to WebSocket
        await self.send_json(event)

    async def refresh_notifications(self, event):
        # Send message to WebSocket
        await self.fetch_notifications()


class RoomConsumer(AsyncJsonWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(args, kwargs)
        self.user = None
        self.room_id = None

    def get_room(self, phone_numbers):
        usernames_to_notify = []
        phone_numbers.append(self.user.phone_number)
        members_to_be_added = User.objects.filter(phone_number__in=phone_numbers)
        rooms_with_members = Room.objects.filter(
            members__in=members_to_be_added
        ).distinct()
        room = None
        for room_with_members in rooms_with_members:
            existing_room_members = set(room_with_members.members.all())
            if existing_room_members == set(members_to_be_added):
                room = room_with_members
                break
        if not room:
            room = Room.objects.create(display_name="Change the group name")
            room.members.add(*members_to_be_added)
            for user in room.members.all():
                UserRoomNotification.objects.create(user=user, room=room)
            usernames_to_notify = [
                notification.user.username
                for notification in room.userroomnotification_set.all()
            ]
        self.room_id = str(room.id)
        user_allowed = self.user_allowed()
        if user_allowed:
            members = list(room.members.all().values("display_name"))
            if len(members) == 2:
                display_name = (
                    room.members.exclude(phone_number=self.user.phone_number)
                    .first()
                    .display_name
                )
            else:
                display_name = room.display_name
            return room, members, display_name, usernames_to_notify
        else:
            raise UserNotAllowedError("User is not a member of the room")

    def user_allowed(self):
        room = Room.objects.filter(id=self.room_id)
        if room.exists():
            room = room.first()
            return self.user in room.members.all()
        else:
            return False

    def change_room_name(self, new_name):
        usernames_to_notify = []
        room = Room.objects.get(id=self.room_id)
        if len(room.members.all()) > 2:
            room.display_name = new_name
            room.save()
            usernames_to_notify = [
                notification.user.username
                for notification in room.userroomnotification_set.all()
            ]
        return room.display_name, usernames_to_notify

    async def connect(self):
        await self.accept()
        self.user = self.scope["user"]
        self.room_id = None

    async def disconnect(self, close_code):
        if self.room_id:
            await self.channel_layer.group_discard(self.room_id, self.channel_name)

    async def initialize_room(self, members):
        (
            room,
            members,
            room_name,
            usernames_to_notify,
        ) = await database_sync_to_async(
            self.get_room
        )(members)
        await self.channel_layer.send(
            self.channel_name,
            {"type": "new_room", "room_name": room_name, "room_members": members},
        )
        await self.channel_layer.group_add(self.room_id, self.channel_name)
        for username in usernames_to_notify:
            await self.channel_layer.group_send(
                username, {"type": "refresh_notifications"}
            )

    async def receive_json(self, content, **kwargs):
        if content.get("command") == "connect":
            if self.room_id:
                await self.channel_layer.group_discard(self.room_id, self.channel_name)
            phone_numbers = content.get("phone_numbers", [])
            await self.initialize_room(phone_numbers)
        user_allowed = await database_sync_to_async(self.user_allowed)()
        if user_allowed:
            if content.get("command") == "update_room_name":
                asyncio.create_task(self.update_room_name(content))

    async def update_room_name(self, input_payload):
        new_room_name = input_payload["name"].strip()
        if new_room_name:
            room_name, usernames_to_notify = await database_sync_to_async(
                self.change_room_name
            )(new_room_name)
            await self.channel_layer.group_send(
                self.room_id,
                {"type": "updated_room_name", "room_name": room_name},
            )
            for username in usernames_to_notify:
                await self.channel_layer.group_send(
                    username, {"type": "refresh_notifications"}
                )

    async def new_room(self, event):
        # Send message to WebSocket
        await self.send_json(event)

    async def updated_room_name(self, event):
        # Send message to WebSocket
        await self.send_json(event)
