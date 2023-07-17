from django.contrib import admin

from blabhear.models import Report


class ReadOnlyModelAdmin(admin.ModelAdmin):
    readonly_fields = ("reporter", "reported_user")


admin.site.register(Report, ReadOnlyModelAdmin)
