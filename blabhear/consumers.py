import asyncio
import logging
import uuid

import phonenumbers
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.postgres.aggregates import ArrayAgg
from django.db.models import Case, When, BooleanField
from phonenumbers.phonenumberutil import NumberParseException

from blabhear.exceptions import UserNotAllowedError
from blabhear.models import (
    User,
    Room,
    Message,
    UserRoomNotification,
    MessageNotification,
    Report,
)
from blabhear.storage import (
    generate_upload_signed_url_v4,
    generate_download_signed_url_v4,
)

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
                try:
                    phone_number = phonenumbers.parse(
                        phone_number, self.user.alpha2_country_code
                    )
                    if phonenumbers.is_valid_number(phone_number):
                        phone_number = phonenumbers.format_number(
                            phone_number, phonenumbers.PhoneNumberFormat.E164
                        )
                        valid_phone_numbers.append(phone_number)
                except NumberParseException:
                    pass
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
            self.user.userroomnotification_set.annotate(
                member_phone_numbers=ArrayAgg("room__members__phone_number")
            )
            .annotate(
                is_own_message=Case(
                    When(message__creator=self.user, then=True),
                    default=False,
                    output_field=BooleanField(),
                )
            )
            .values(
                "member_phone_numbers",
                "room",
                "room__display_name",
                "timestamp",
                "read",
                "message__creator__display_name",
                "is_own_message",
            )
            .order_by("read", "-timestamp")
        )
        for notification in notifications:
            notification["room"] = str(notification["room"])
            notification["timestamp"] = notification["timestamp"].timestamp()
            if len(notification["member_phone_numbers"]) == 2:
                receiver_phone_number = next(
                    phone_number
                    for phone_number in notification["member_phone_numbers"]
                    if phone_number != self.user.phone_number
                )
                notification["room__display_name"] = User.objects.get(
                    phone_number=receiver_phone_number
                ).display_name
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


def serialize_msg_notification(notification):
    notification["id"] = str(notification["id"])
    notification["message__id"] = str(notification["message__id"])
    notification["timestamp"] = notification["timestamp"].timestamp()
    notification["url"] = generate_download_signed_url_v4(notification["message__id"])
    return notification


class RoomConsumer(AsyncJsonWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(args, kwargs)
        self.user = None
        self.room_id = None

    def get_message_notifications(self):
        room = Room.objects.get(id=self.room_id)
        room_member_pks = room.members.all().values_list("pk", flat=True)
        latest_notification = (
            self.user.messagenotification_set.filter(
                room__id=self.room_id, message__creator__id__in=room_member_pks
            )
            .annotate(
                is_own_message=Case(
                    When(message__creator=self.user, then=True),
                    default=False,
                    output_field=BooleanField(),
                )
            )
            .values(
                "id",
                "message__id",
                "timestamp",
                "message__creator__display_name",
                "is_own_message",
            )
            .order_by("timestamp")
            .last()
        )
        notifications = []
        if latest_notification:
            latest_notification = serialize_msg_notification(latest_notification)
            notifications.append(latest_notification)
        return notifications

    def read_unread_room_notification(self):
        room = Room.objects.get(id=self.room_id)
        UserRoomNotification.objects.filter(
            user=self.user, room=room, read=False
        ).update(read=True)

    def get_new_message_notification_event(self, event):
        message = Message.objects.get(id=event["message_id"])
        notification = (
            message.messagenotification_set.filter(receiver=self.user)
            .annotate(
                is_own_message=Case(
                    When(message__creator=self.user, then=True),
                    default=False,
                    output_field=BooleanField(),
                )
            )
            .values(
                "id",
                "message__id",
                "timestamp",
                "message__creator__display_name",
                "is_own_message",
            )
            .first()
        )
        event["message"] = serialize_msg_notification(notification)
        return event

    def update_notifications_for_new_message(self, message):
        room = Room.objects.get(id=self.room_id)
        for user in room.members.all():
            notification = UserRoomNotification.objects.get(user=user, room=room)
            notification.message = message
            notification.read = user == self.user
            notification.save()

    def create_message_notifications_for_new_message(self, message):
        room = Room.objects.get(id=self.room_id)
        for user in room.members.all():
            notification, created = MessageNotification.objects.get_or_create(
                receiver=user, room=room, message=message
            )
            notification.save()

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

    def get_message(self, filename):
        room = Room.objects.get(id=self.room_id)
        message, created = Message.objects.get_or_create(
            id=filename, room=room, creator=self.user
        )
        return message

    def get_all_room_members(self):
        room = Room.objects.filter(id=self.room_id)
        if room.exists():
            room = room.first()
            members = room.members.all().values()
        else:
            members = []
        member_display_names = [user["display_name"] for user in members]
        member_usernames = [user["username"] for user in members]
        return member_display_names, member_usernames

    def delete_message_notification(self, notification_id):
        notification = MessageNotification.objects.get(id=notification_id)
        report = Report.objects.create(
            reporter=self.user,
            reported_user=notification.message.creator,
            message=notification.message,
        )
        notification.delete()

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
        await self.fetch_upload_url()
        await self.fetch_message_notifications()
        await self.channel_layer.send(
            self.channel_name,
            {"type": "room_notified"},
        )

    async def receive_json(self, content, **kwargs):
        if content.get("command") == "connect":
            if self.room_id:
                await self.channel_layer.group_discard(self.room_id, self.channel_name)
            phone_numbers = content.get("phone_numbers", [])
            await self.initialize_room(phone_numbers)
        if content.get("command") == "disconnect":
            if self.room_id:
                await self.channel_layer.group_discard(self.room_id, self.channel_name)
        user_allowed = await database_sync_to_async(self.user_allowed)()
        if user_allowed:
            if content.get("command") == "update_room_name":
                asyncio.create_task(self.update_room_name(content))
            if content.get("command") == "fetch_upload_url":
                asyncio.create_task(self.fetch_upload_url())
            if content.get("command") == "send_message":
                asyncio.create_task(self.send_message(content))
            if content.get("command") == "fetch_message_notifications":
                asyncio.create_task(self.fetch_message_notifications())
            if content.get("command") == "report_message_notification":
                asyncio.create_task(self.report_message_notification(content))

    async def report_message_notification(self, input_payload):
        await database_sync_to_async(self.delete_message_notification)(
            input_payload["message_notification_id"]
        )

    async def send_message(self, input_payload):
        filename = input_payload.get("filename")
        if filename:
            message = await database_sync_to_async(self.get_message)(filename)
            if message:
                await database_sync_to_async(self.update_notifications_for_new_message)(
                    message
                )
                await database_sync_to_async(
                    self.create_message_notifications_for_new_message
                )(message)
                await self.channel_layer.group_send(
                    self.room_id,
                    {"type": "new_message", "message_id": str(message.id)},
                )
                (
                    room_member_display_names,
                    room_member_usernames,
                ) = await database_sync_to_async(self.get_all_room_members)()
                for username in room_member_usernames:
                    await self.channel_layer.group_send(
                        username,
                        {
                            "type": "refresh_notifications",
                        },
                    )
                await self.channel_layer.group_send(
                    self.room_id,
                    {"type": "room_notified"},
                )
                await self.fetch_upload_url()

    async def fetch_message_notifications(self):
        message_notifications = await database_sync_to_async(
            self.get_message_notifications
        )()
        await self.channel_layer.send(
            self.channel_name,
            {
                "type": "message_notifications",
                "message_notifications": message_notifications,
                "refresh_message_notifications_in": 604790000,
            },
        )

    async def fetch_upload_url(self):
        filename = str(uuid.uuid4())
        url = generate_upload_signed_url_v4(filename)
        await self.channel_layer.send(
            self.channel_name,
            {
                "type": "upload_url",
                "upload_url": url,
                "upload_filename": filename,
                "refresh_upload_destination_in": 604790000,
            },
        )

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

    async def upload_url(self, event):
        # Send message to WebSocket
        await self.send_json(event)

    async def room_notified(self, event):
        await database_sync_to_async(self.read_unread_room_notification)()
        await self.channel_layer.group_send(
            self.user.username,
            {
                "type": "refresh_notifications",
            },
        )

    async def message_notifications(self, event):
        # Send message to WebSocket
        await self.send_json(event)

    async def new_message(self, event):
        event = await database_sync_to_async(self.get_new_message_notification_event)(
            event
        )
        await self.send_json(event)
