from django.contrib import admin

from .models import SKU, StockLedger


@admin.register(SKU)
class SKUAdmin(admin.ModelAdmin):
    list_display = ("id", "code", "name", "available_quantity", "reserved_quantity")
    search_fields = ("code", "name")


@admin.register(StockLedger)
class StockLedgerAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "sku",
        "reason",
        "available_change",
        "reserved_change",
        "available_after",
        "reserved_after",
        "actor",
        "created_at",
    )
    list_filter = ("reason",)
    search_fields = ("sku__code",)
    # Append-only: ledger rows are never edited or deleted via admin.
    readonly_fields = [f.name for f in StockLedger._meta.fields]

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
