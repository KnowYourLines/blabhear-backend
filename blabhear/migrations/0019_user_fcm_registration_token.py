# Generated by Django 3.2.18 on 2023-10-22 16:04

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('blabhear', '0018_alter_user_blocked_users'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='fcm_registration_token',
            field=models.TextField(blank=True, null=True, unique=True),
        ),
    ]
