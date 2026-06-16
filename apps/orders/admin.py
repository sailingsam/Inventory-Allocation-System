from django.contrib import admin

from .models import Order, OrderLine


class OrderLineInline(admin.TabularInline):
    model = OrderLine
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "order_date", "status", "created_at", "allocated_at")
    list_filter = ("status",)
    search_fields = ("customer__email",)
    # order_date is editable in admin so demos can be backdated; immutable via the API only.
    inlines = [OrderLineInline]
