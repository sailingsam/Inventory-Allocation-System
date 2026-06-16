from django.contrib import admin

from .models import AllocationRun


@admin.register(AllocationRun)
class AllocationRunAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "actor",
        "started_at",
        "finished_at",
        "orders_processed",
        "orders_allocated",
        "orders_backordered",
    )
    readonly_fields = [f.name for f in AllocationRun._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
