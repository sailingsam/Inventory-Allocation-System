# Walkthrough — FCFS allocation, end to end

This reproduces the assignment's worked example from a clean database: **SKU-A starts with 12
units**, ten orders dated Apr 1–10 want `5, 10, 4, 4, 3, 2, 1, 2, 1, 2`, and one allocation run
demonstrates **"continue past shortages"**.

> Prefer a video? This same flow is what a 3–5 min Loom would show. The written version is
> reproducible step-by-step below.

---

## 1. Start the stack & seed the demo data

```bash
docker compose up -d db redis          # PostgreSQL + Redis
# (or run Postgres yourself and: export DATABASE_URL=postgres://oms:oms@localhost:5432/oms)

python manage.py migrate
python manage.py seed_demo --fresh
```

`seed_demo --fresh` creates: 1 admin, 1 operator, 3 customers, 5 SKUs (SKU-A = 12), and the ten
SKU-A orders dated Apr 1–10. Demo logins (password `DemoPass123`):

| Role | Email |
|------|-------|
| Admin | `admin@demo.com` |
| Operator | `operator@demo.com` |
| Customer | `customer1@demo.com` … `customer3@demo.com` |

Start the API server (if not already via docker):

```bash
python manage.py runserver
```

---

## 2. Log in as the operator

```bash
curl -s localhost:8000/api/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"operator@demo.com","password":"DemoPass123"}'
```

```json
{
  "refresh": "<refresh-token>",
  "access": "<access-token>",
  "user": {"id": 2, "email": "operator@demo.com", "role": "WAREHOUSE_OPERATOR"}
}
```

Save the access token for the next calls:

```bash
ACCESS="<paste access token>"
```

---

## 3. Check SKU-A before allocation

```bash
curl -s localhost:8000/api/skus/ -H "Authorization: Bearer $ACCESS"
```

SKU-A starts at **available 12, reserved 0**. All ten orders are `PENDING`.

---

## 4. Run the FCFS allocation

```bash
curl -s -X POST localhost:8000/api/allocation/run/ -H "Authorization: Bearer $ACCESS"
```

```json
{
  "id": 1,
  "orders_processed": 10,
  "orders_allocated": 3,
  "orders_backordered": 7,
  "backorder_on_shortage": true,
  "detail": [
    {"order_id": 1, "outcome": "ALLOCATED"},
    {"order_id": 2, "outcome": "BACKORDERED"},
    {"order_id": 3, "outcome": "ALLOCATED"},
    {"order_id": 4, "outcome": "BACKORDERED"},
    {"order_id": 5, "outcome": "ALLOCATED"},
    {"order_id": 6, "outcome": "BACKORDERED"}
    // ... 7–10 BACKORDERED (stock exhausted)
  ]
}
```

---

## 5. The outcome (matches the assignment 1:1)

| Order | Date | Qty | Outcome | SKU-A available after |
|-------|------|-----|---------|-----------------------|
| #1 | Apr 1 | 5 | **ALLOCATED** | 12 → 7 |
| #2 | Apr 2 | 10 | **BACKORDERED** (needs 10, only 7) | 7 |
| #3 | Apr 3 | 4 | **ALLOCATED** | 7 → 3 |
| #4 | Apr 4 | 4 | **BACKORDERED** (needs 4, only 3) | 3 |
| #5 | Apr 5 | 3 | **ALLOCATED** | 3 → 0 |
| #6–#10 | Apr 6–10 | … | **BACKORDERED** (stock exhausted) | 0 |

After the run, SKU-A is **available 0, reserved 12**:

```bash
curl -s localhost:8000/api/skus/ -H "Authorization: Bearer $ACCESS"
# SKU-A -> {"available_quantity": 0, "reserved_quantity": 12}
```

👉 The key behaviour: order #2 (qty 10) is **skipped**, but the later, smaller orders #3 and #5
**still get stock** — "continue past shortages." FCFS priority is by `order_date`, so this is
fair: each earlier order had first claim.

---

## 6. Fulfill an allocated order

```bash
curl -s -X POST localhost:8000/api/orders/1/fulfill/ -H "Authorization: Bearer $ACCESS"
# order #1 -> FULFILLED; SKU-A reserved 12 -> 7 (those 5 units leave stock)
```

A second fulfill of the same order returns **409** (double-fulfillment rejected).

---

## 7. Backorder retry (bonus behaviour)

Backordered orders are re-checked on every run and keep their FCFS priority. Restock SKU-A and
re-run to see #4 (the next-oldest backordered order, qty 4) get filled:

```bash
curl -s -X PATCH localhost:8000/api/skus/1/stock/ \
  -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d '{"available_delta": 4, "reason": "RESTOCK"}'

curl -s -X POST localhost:8000/api/allocation/run/ -H "Authorization: Bearer $ACCESS"
# order #4 (oldest outstanding) -> ALLOCATED, ahead of any newer order
```

---

## 8. Audit log

Every run is recorded:

```bash
curl -s localhost:8000/api/allocation/runs/ -H "Authorization: Bearer $ACCESS"
```

Interactive API docs (full contract): **http://localhost:8000/api/schema/swagger-ui/**

---

## Concurrency note

Two operators clicking "Run allocation" simultaneously cannot oversell: a Postgres advisory lock
makes only one run effective at a time, and `select_for_update` row locks (taken in a consistent
id order to avoid deadlocks) protect stock. This is proven by the threaded test
`apps/allocation/tests/test_concurrency.py` (`pytest -m postgres`).
