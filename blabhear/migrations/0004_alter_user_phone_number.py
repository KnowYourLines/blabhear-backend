# Generated by Django 3.2.18 on 2023-04-21 19:35

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('blabhear', '0003_user_display_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='phone_number',
            field=models.CharField(max_length=150, unique=True),
        ),
    ]
