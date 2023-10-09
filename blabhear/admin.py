from django.contrib import admin

from blabhear.models import Report, Message, User


class ReadOnlyReportModelAdmin(admin.ModelAdmin):
    readonly_fields = ("reporter", "reported_user", "message")


class ReadOnlyMessageModelAdmin(admin.ModelAdmin):
    readonly_fields = ("creator", "room")


admin.site.register(Report, ReadOnlyReportModelAdmin)
admin.site.register(Message, ReadOnlyMessageModelAdmin)
admin.site.register(User)
