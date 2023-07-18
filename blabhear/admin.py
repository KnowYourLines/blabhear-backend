from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib import admin

from blabhear.models import Report, Message


class ReadOnlyReportModelAdmin(admin.ModelAdmin):
    readonly_fields = ("reporter", "reported_user", "message")


class ReadOnlyMessageModelAdmin(admin.ModelAdmin):
    readonly_fields = ("creator", "room")

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        room_id = obj.room.id
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            str(room_id), {"type": "refresh_notifications"}
        )

    def delete_queryset(self, request, queryset):
        super().delete_queryset(request, queryset)
        for room_id in list(queryset.order_by().values_list("room__id").distinct()):
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                str(room_id), {"type": "refresh_notifications"}
            )


admin.site.register(Report, ReadOnlyReportModelAdmin)
admin.site.register(Message, ReadOnlyMessageModelAdmin)
