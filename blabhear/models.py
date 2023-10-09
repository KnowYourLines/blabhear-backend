import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q, F


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone_number = models.CharField(max_length=150, unique=True)
    alpha2_country_code = models.CharField(max_length=2, null=False, blank=False)
    display_name = models.CharField(max_length=150)
    blocked_users = models.ManyToManyField("self", blank=True, null=True)


class Room(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    members = models.ManyToManyField(User)
    display_name = models.CharField(max_length=150, blank=True)

    def __str__(self):
        return str(self.id)


class Message(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creator = models.ForeignKey(User, on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.id)


class UserRoomNotification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now=True)
    read = models.BooleanField(default=False)
    message = models.ForeignKey(
        Message, blank=True, null=True, on_delete=models.SET_NULL
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["room", "user"], name="unique_notification"
            ),
        ]


class MessageNotification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    receiver = models.ForeignKey(User, on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now=True)
    message = models.ForeignKey(Message, on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["room", "receiver", "message"], name="unique_msg_notification"
            ),
        ]


class Report(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reporter = models.ForeignKey(User, on_delete=models.CASCADE, editable=False)
    reported_at = models.DateTimeField(auto_now_add=True)
    reported_user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="reports", editable=False
    )
    message = models.ForeignKey(Message, on_delete=models.CASCADE, editable=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                name="not_same", check=~Q(reporter=F("reported_user"))
            )
        ]

    def __str__(self):
        return str(self.id)
