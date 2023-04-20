import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone_number = models.CharField(max_length=150)
    alpha2_country_code = models.CharField(max_length=2)
    display_name = models.CharField(max_length=150)
