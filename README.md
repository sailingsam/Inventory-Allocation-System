# Order Management with FCFS Inventory Allocation

A Django + DRF backend for user auth, role-based authorization, order placement, and a
**concurrency-safe First-Come-First-Serve (FCFS) inventory allocation engine** driven by
`order_date`.

> Allocation priority is decided by each order's `order_date` (then `created_at` as a
> tiebreaker) — **not** by who hit the API first.

---

## Tech stack

- Python 3.12, Django 4.2, Django REST Framework
- PostgreSQL (required — the FCFS engine relies on real row-level + advisory locking)
- SimpleJWT (access + refresh + blacklist)
- drf-spectacular (OpenAPI / Swagger — the API contract)
- Celery + Redis (bonus: periodic allocation)
- pytest-django

## Architecture

Clean separation of concerns — business logic lives in `services.py`, never in views:

```
config/                 # Django project (settings, urls, celery)
apps/
  accounts/             # custom email User + Role, JWT auth, role permissions
  inventory/            # SKU, append-only StockLedger, locked stock service
  orders/               # Order/OrderLine, create/cancel/fulfill lifecycle
  allocation/           # FCFS engine (services.py) + AllocationRun audit
```

- **models** — data + invariants (e.g. non-negative stock check constraints)
- **services** — transactional business logic (stock mutations, order lifecycle, FCFS engine)
- **serializers** — validation + representation
- **views** — thin HTTP layer + permission wiring

---

## Quickstart (Docker)

```bash
cp .env.example .env                 # defaults are fine for local
docker compose up --build            # postgres + redis + web + celery worker/beat
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_demo --fresh
docker compose exec web python manage.py createsuperuser   # optional, for /admin
```

App: http://localhost:8000 · Swagger UI: http://localhost:8000/api/schema/swagger-ui/

## Local dev (without Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# PostgreSQL is required. Start one (e.g. via docker compose up -d db) and point to it:
export DATABASE_URL=postgres://oms:oms@localhost:5432/oms

python manage.py migrate
python manage.py seed_demo --fresh
python manage.py runserver
```

## Running tests

```bash
pytest                       # full suite (needs a running Postgres)
pytest -m postgres           # just the threaded concurrency tests
```

---

## Roles & permissions

| Role | Can |
|------|-----|
| **Customer** | create own orders, view own orders, cancel own PENDING orders |
| **Warehouse Operator** | view all orders, run allocation, fulfill orders, manage SKU stock |
| **Admin** | all of the above + user management |

Unauthenticated requests → `401`; authenticated-but-wrong-role → `403`.

## API surface

| Method | Path | Role |
|--------|------|------|
| POST | `/api/auth/register/` | public (creates Customer) |
| POST | `/api/auth/login/` | public |
| POST | `/api/auth/refresh/` | public |
| POST | `/api/auth/logout/` | auth (blacklists refresh) |
| GET | `/api/me/` | auth |
| POST/GET | `/api/users/` `…/{id}/` | Admin |
| GET | `/api/skus/` | any auth |
| POST | `/api/skus/` | Operator, Admin |
| PATCH | `/api/skus/{id}/stock/` | Operator, Admin |
| POST | `/api/orders/` | Customer |
| GET | `/api/orders/` `…/{id}/` | own (Customer) / all (Operator, Admin) |
| POST | `/api/orders/{id}/cancel/` | Customer if PENDING, Operator/Admin if ALLOCATED |
| POST | `/api/orders/{id}/fulfill/` | Operator, Admin |
| POST | `/api/allocation/run/` | Operator, Admin |
| GET | `/api/allocation/runs/` `…/{id}/` | Operator, Admin (audit log) |

Full request/response schemas: **Swagger UI** at `/api/schema/swagger-ui/`.

### Example: log in and place an order

```bash
# login
curl -s localhost:8000/api/auth/login/ -H 'Content-Type: application/json' \
  -d '{"email":"customer1@demo.com","password":"DemoPass123"}'
# -> {"access":"...","refresh":"...","user":{...}}

# place an order (use the access token)
curl -s localhost:8000/api/orders/ -H "Authorization: Bearer $ACCESS" \
  -H 'Content-Type: application/json' \
  -d '{"lines":[{"sku":1,"quantity":3}]}'
```

---

## Demo: the worked example

`python manage.py seed_demo --fresh` creates SKU-A with `available_quantity=12` and ten orders
dated Apr 1–10 wanting `5, 10, 4, 4, 3, 2, 1, 2, 1, 2`. After `POST /api/allocation/run/`:

| Order | Date | Qty | Outcome | SKU-A available after |
|-------|------|-----|---------|-----------------------|
| #1 | Apr 1 | 5 | ALLOCATED | 7 |
| #2 | Apr 2 | 10 | BACKORDERED | 7 |
| #3 | Apr 3 | 4 | ALLOCATED | 3 |
| #4 | Apr 4 | 4 | BACKORDERED | 3 |
| #5 | Apr 5 | 3 | ALLOCATED | 0 |
| #6–#10 | Apr 6–10 | … | BACKORDERED | 0 |

The big order (#2) is skipped, but later smaller orders (#3, #5) still get stock — "continue
past shortages."

---

## Design notes

### Data model
- `SKU` tracks two non-negative counters: `available_quantity` (free) and `reserved_quantity`
  (committed to ALLOCATED orders). DB `CheckConstraint`s forbid negative stock.
- `StockLedger` is **append-only**: every stock movement writes one row (signed deltas,
  resulting balances, reason, actor, and the causing order). Full audit trail, never mutated.
- `Order.order_date` is the immutable FCFS priority key. It defaults to `now()` and can only be
  backdated via seed/admin — the customer API never accepts it (verified by test).

### Allocation strategy — "continue past shortages" (chosen) vs "strict stop"

When an order in the FCFS queue cannot be fully satisfied, there are two reasonable behaviours:

- **Strict stop** — halt the whole run at the first order that doesn't fit. Every later order
  stays unallocated even if stock remains.
- **Continue past shortages** (what I chose) — skip the order that doesn't fit (mark it
  `BACKORDERED`) and keep going, so later, smaller orders can still use the remaining stock.

I chose **continue past shortages** because:

1. **It maximises stock utilisation.** Leftover stock isn't wasted just because one large order
   couldn't be filled. In the worked example SKU-A=12: order #2 (qty 10) can't fit in the
   remaining 7, but #3 (qty 4) and #5 (qty 3) still allocate — 12 units fully used.
2. **It avoids head-of-line blocking.** Under strict stop, a single oversized or
   never-fulfillable order would block *every* subsequent order indefinitely — bad for
   throughput and for every other customer.
3. **FCFS fairness is still preserved.** Orders are always processed in `order_date` (then
   `created_at`) order; "continue" only means one unfillable order doesn't halt the queue. And
   a backordered order keeps its priority — it is re-checked on every run and, once enough
   stock arrives, is filled before newer orders.

All-or-nothing per order is still strictly enforced — an order never gets a partial allocation.

**Trade-off:** a very large order can keep being skipped while smaller, later orders get stock
first. That is the intended behaviour for FCFS-by-availability, and the backordered order never
loses its place in line. If a stricter "nobody after a shortage gets stock until that order is
filled" policy were ever required, it could be added behind a setting without touching the rest
of the engine.

### Backorders & retry
A shortage never causes partial allocation. The order stays outstanding (marked `BACKORDERED`,
or left `PENDING` if `ALLOCATION_BACKORDER_ON_SHORTAGE=False`) and is **re-checked on every
subsequent run** — so once stock is replenished it gets filled automatically. Because the queue
is sorted by `order_date`, an older backordered order keeps its FCFS priority and is served
before a newer order when limited stock arrives.

### Concurrency & data integrity
- Every stock mutation runs inside `transaction.atomic()` and takes `select_for_update()` row
  locks, always acquired in a consistent order (`ORDER BY id`) to avoid deadlocks — in the
  engine **and** in cancel/fulfill/stock-adjust.
- An **advisory lock** (`pg_advisory_xact_lock`) ensures only one allocation run is effective at
  a time; the lock auto-releases at transaction end.
- Order creation never touches stock (reservation happens only at allocation), so the only
  oversell vector is concurrent runs — which the advisory lock serializes. No overselling.

### Known trade-offs
- The whole allocation run is one transaction (simple + strongly consistent) at the cost of no
  partial progress if it aborts mid-run. A per-order-transaction variant (configurable) would
  trade that off the other way.

---

## Bonuses included
- OpenAPI / Swagger schema (drf-spectacular)
- Celery + Redis periodic allocation task
- Allocation audit log + summary endpoint
- Rate limiting on auth endpoints
- docker-compose for the full stack

## Project assumptions
- Registration always creates a **Customer**; operators/admins are provisioned by an Admin (or
  the seed) — operators cannot self-promote.
- Cancelling an `ALLOCATED` order is an Operator/Admin action (it releases reserved stock).
- Customers may cancel their own `PENDING` **or** `BACKORDERED` orders. (The brief mentions only
  PENDING; we extend this to BACKORDERED because such an order holds no reserved stock and is
  merely waiting — a customer should be able to cancel it.)
