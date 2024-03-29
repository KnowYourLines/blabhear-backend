# Generated by Django 3.2.18 on 2023-05-29 16:47

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('blabhear', '0005_room'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserRoomNotification',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('timestamp', models.DateTimeField(auto_now=True)),
                ('room', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='blabhear.room')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name='userroomnotification',
            constraint=models.UniqueConstraint(fields=('room', 'user'), name='unique_notification'),
        ),
    ]
