"""Seed a clean FCFS demo dataset.

Reproduces the assignment's worked example exactly: SKU-A starts with available_quantity=12 and
ten orders dated 1–10 April (one per day, all for SKU-A) with quantities chosen so a FCFS run
demonstrates "continue past shortages":

    #1 (Apr 1, qty 5)  -> ALLOCATED   (12 -> 7)
    #2 (Apr 2, qty 10) -> BACKORDERED (needs 10, only 7 left)
    #3 (Apr 3, qty 4)  -> ALLOCATED   (7 -> 3)
    #4 (Apr 4, qty 4)  -> BACKORDERED (needs 4, only 3)
    #5 (Apr 5, qty 3)  -> ALLOCATED   (3 -> 0)
    #6..#10            -> BACKORDERED  (stock exhausted)

Also creates 1 admin, 1 operator, 3 customers, and 5 SKUs total.

Usage:
    python manage.py seed_demo            # create if not present
    python manage.py seed_demo --fresh    # wipe orders/skus/runs first, then create
"""

from datetime import timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role
from apps.allocation.models import AllocationRun
from apps.inventory.models import SKU, StockLedger
from apps.orders.models import Order, OrderLine
from apps.orders.services import create_order

User = get_user_model()

DEMO_PASSWORD = "DemoPass123"

# Worked-example quantities for the ten daily SKU-A orders (Apr 1..10).
SKU_A_ORDER_QTYS = [5, 10, 4, 4, 3, 2, 1, 2, 1, 2]


class Command(BaseCommand):
    help = "Seed a clean FCFS demo dataset reproducing the assignment's worked example."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fresh",
            action="store_true",
            help="Delete existing orders, SKUs, ledger and runs before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["fresh"]:
            StockLedger.objects.all().delete()
            OrderLine.objects.all().delete()
            Order.objects.all().delete()
            AllocationRun.objects.all().delete()
            SKU.objects.all().delete()
            self.stdout.write(self.style.WARNING("Wiped existing orders/SKUs/ledger/runs."))

        admin = self._user("admin@demo.com", Role.ADMIN, is_staff=True, is_superuser=True)
        operator = self._user("operator@demo.com", Role.WAREHOUSE_OPERATOR)
        customers = [self._user(f"customer{i}@demo.com", Role.CUSTOMER) for i in range(1, 4)]

        # Five SKUs; SKU-A is the worked-example one starting at 12.
        sku_a = self._sku("SKU-A", "Widget A", 12)
        self._sku("SKU-B", "Widget B", 30)
        self._sku("SKU-C", "Widget C", 0)
        self._sku("SKU-D", "Widget D", 100)
        self._sku("SKU-E", "Widget E", 7)

        if Order.objects.exists() and not options["fresh"]:
            self.stdout.write(
                self.style.WARNING("Orders already exist — skipping order creation (use --fresh).")
            )
        else:
            self._create_demo_orders(sku_a, customers)

        self.stdout.write(self.style.SUCCESS("\nSeed complete."))
        self.stdout.write(f"  Admin:     admin@demo.com / {DEMO_PASSWORD}")
        self.stdout.write(f"  Operator:  operator@demo.com / {DEMO_PASSWORD}")
        self.stdout.write(f"  Customers: customer1..3@demo.com / {DEMO_PASSWORD}")
        self.stdout.write(
            "\nRun allocation: POST /api/allocation/run/ as the operator, "
            "then inspect SKU-A and the orders' statuses."
        )

    # -- helpers ----------------------------------------------------------------------
    def _user(self, email, role, **extra):
        user, created = User.objects.get_or_create(
            email=email, defaults={"role": role, **extra}
        )
        # Always (re)set the known demo password and role for a predictable demo.
        user.role = role
        for k, v in extra.items():
            setattr(user, k, v)
        user.set_password(DEMO_PASSWORD)
        user.save()
        return user

    def _sku(self, code, name, available):
        sku, _ = SKU.objects.get_or_create(
            code=code, defaults={"name": name, "available_quantity": available}
        )
        return sku

    def _create_demo_orders(self, sku_a, customers):
        # Ten orders dated Apr 1..10 of the current year, round-robin across the 3 customers.
        year = timezone.now().year
        for day, qty in enumerate(SKU_A_ORDER_QTYS, start=1):
            order_date = timezone.datetime(year, 4, day, 9, 0, tzinfo=dt_timezone.utc)
            customer = customers[(day - 1) % len(customers)]
            create_order(customer=customer, lines=[(sku_a, qty)], order_date=order_date)
        self.stdout.write(
            self.style.SUCCESS(f"Created {len(SKU_A_ORDER_QTYS)} SKU-A orders (Apr 1..10).")
        )
