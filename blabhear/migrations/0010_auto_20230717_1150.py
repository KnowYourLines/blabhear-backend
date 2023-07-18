# Generated by Django 3.2.18 on 2023-07-17 11:50

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.db.models.expressions
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('blabhear', '0009_auto_20230715_0232'),
    ]

    operations = [
        migrations.CreateModel(
            name='Report',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('reported_at', models.DateTimeField(auto_now_add=True)),
                ('reported_user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reports', to=settings.AUTH_USER_MODEL)),
                ('reporter', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name='report',
            constraint=models.CheckConstraint(check=models.Q(('reporter', django.db.models.expressions.F('reported_user')), _negated=True), name='not_same'),
        ),
    ]