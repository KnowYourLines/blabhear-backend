# Generated by Django 3.2.18 on 2023-07-17 13:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('blabhear', '0011_auto_20230717_1306'),
    ]

    operations = [
        migrations.AddField(
            model_name='report',
            name='message_uuid',
            field=models.UUIDField(default=1, editable=False),
            preserve_default=False,
        ),
    ]
