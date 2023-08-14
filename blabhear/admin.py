from django.contrib import admin

from blabhear.models import Report, Message


class ReadOnlyReportModelAdmin(admin.ModelAdmin):
    readonly_fields = ("reporter", "reported_user", "message", "reported_at")
    list_display = ("reporter", "reported_user", "message", "reported_at")


class ReadOnlyMessageModelAdmin(admin.ModelAdmin):
    readonly_fields = ("creator", "room", "created_at")
    list_display = ("creator", "room", "created_at")


admin.site.register(Report, ReadOnlyReportModelAdmin)
admin.site.register(Message, ReadOnlyMessageModelAdmin)
