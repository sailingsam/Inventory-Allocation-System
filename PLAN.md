# Plan: Order Management with FCFS Inventory Allocation (Django)

## Context

This is a take-home backend assignment that decides an internship / full-time offer, so the
bar is "everything handled, clean, defensible." Build a Django + DRF service with user auth,
role-based authorization, order placement, and a concurrency-safe **First-Come-First-Serve
(FCFS) inventory allocation engine** driven by `order_date`.

Two hard constraints that shape *how* we work:

1. **Commits are authored as the candidate (saksham), NEVER as an AI assistant.** No
   `Co-Authored-By` AI trailer. Meaningful, staged commits. **The repo is pushed to a public
   GitHub repository by the candidate only** — the build process never pushes.
2. **The core allocation engine is NOT AI-generated** (explicit ground rule) and the candidate
   must be able to **walk through it on a follow-up call.** => The engine is built LAST, as a
   guided session where the candidate writes the algorithm + README design note themselves, and
   verifies they can narrate the worked example unaided. AI assistance is used only for
   boilerplate, test scaffolding, and docs.

Grade weights: FCFS correctness 25%, concurrency 20%, auth 15%, code structure 15%,
tests 15%, API/docs 10%.

## Tech stack

- Python 3.12, Django 4.2 (LTS) + Django REST Framework
- PostgreSQL via docker-compose (real row-level locking)
- SimpleJWT (access + refresh + blacklist for logout)
- pytest-django for tests
- drf-spectacular for OpenAPI (bonus, free)
- Celery + Redis for periodic allocation (bonus, free, local)
- Next.js (App Router + TypeScript + Tailwind) frontend demo (brownie points)
- All bonuses are free/open-source/local — no paid services, no API keys.

## Architecture (clean separation of concerns — 15% of grade)

```
fableroom/
  PLAN.md                     # this file
  docker-compose.yml          # postgres + redis + web (+ celery worker/beat)
  Dockerfile
  requirements.txt
  .env.example
  manage.py
  pytest.ini
  README.md
  config/                     # Django project
    settings.py  urls.py  wsgi.py  asgi.py  celery.py
  apps/
    accounts/                 # custom User (email login, role), auth, permissions
      models.py serializers.py views.py permissions.py urls.py tests/
    inventory/                # SKU, StockLedger + stock service
      models.py serializers.py views.py services.py urls.py tests/
    orders/                   # Order, OrderLine + cancel/fulfill
      models.py serializers.py views.py services.py urls.py tests/
    allocation/               # THE ENGINE (built last, by candidate) + AllocationRun audit
      models.py services.py views.py urls.py tests/
  scripts/
    seed.py                   # reproduces the PDF worked example exactly
  frontend/                   # Next.js app (login + order + allocation demo)
```

Key rule: **business logic lives in `services.py`, not in views.** Views = thin HTTP layer;
serializers = validation; models = data + invariants.

## Frontend (Next.js — brownie points)

A Next.js (App Router) + TypeScript app under `frontend/` that demos the full flow against the
API: register/login (JWT stored client-side, refresh handling), customer places an order,
operator triggers `POST /api/allocation/run/`, and a results view showing each order's status
(ALLOCATED / BACKORDERED / FULFILLED) + live SKU available/reserved counts. Tailwind for quick
clean styling. This is what the Loom demo walks through end-to-end. Built after the backend +
tests are green, so it's a thin client over a proven API.

## Data model

- **User** (custom): email (unique, USERNAME_FIELD), role in {CUSTOMER, WAREHOUSE_OPERATOR,
  ADMIN}, default Django PBKDF2 hashing.
- **SKU**: code (unique), name, available_quantity, reserved_quantity.
- **StockLedger** (append-only): sku, change (delta), reason, actor, balance snapshot,
  created_at. Written on every stock mutation.
- **Order**: customer (FK), order_date (immutable, default now, backdate ONLY via seed/admin —
  customer serializer rejects it), status, created_at, allocated_at, fulfilled_at.
  Statuses: PENDING, ALLOCATED, FULFILLED, CANCELLED, BACKORDERED.
- **OrderLine**: order, sku, quantity.
- **AllocationRun** (audit/bonus): actor, started_at, finished_at, counts
  (processed/allocated/backordered), JSON detail.

## API surface

```
POST /api/auth/register/                       public
POST /api/auth/login/                          public  -> access + refresh
POST /api/auth/refresh/                        public
POST /api/auth/logout/                         auth    -> blacklist refresh
GET  /api/me/                                  auth

POST  /api/skus/                               Operator, Admin
GET   /api/skus/                               any authenticated
PATCH /api/skus/{id}/stock/                     Operator, Admin   (adjust, ledger-written)

POST  /api/orders/                             Customer
GET   /api/orders/                             own (Customer) / all (Operator, Admin)
GET   /api/orders/{id}/
POST  /api/orders/{id}/cancel/                  Customer if PENDING, Operator/Admin if ALLOCATED
POST  /api/allocation/run/                      Operator, Admin
POST  /api/orders/{id}/fulfill/                 Operator
```

Auth/authz: custom DRF permission classes per role. Unauthenticated -> 401,
authenticated-but-wrong-role -> 403.

## API contract (explicit deliverable)

An API contract is the precise written specification of the interface: for every endpoint, the
method + URL, required role/auth, request body schema (fields, types, required/optional,
validation), success response schema, and all status codes + a consistent JSON error format.
It is the "promise" the backend makes to the frontend and the graders, and it lets the Next.js
app be built in parallel.

**Delivered as an auto-generated OpenAPI (Swagger) spec via `drf-spectacular`** — the
industry-standard, machine-readable contract that always stays in sync with the code:
- Schema (YAML/JSON) at `/api/schema/`
- Interactive Swagger UI at `/api/schema/swagger-ui/`

Endpoints are annotated with `@extend_schema` (request/response examples, status codes) so the
generated contract is complete and accurate. No separate hand-maintained markdown is needed.

Status code conventions: 201 create, 200 ok, 400 validation, 401 unauthenticated,
403 wrong role, 404 not found, 409 conflict (e.g. double-fulfill / cancel of non-cancellable
order). Errors share one JSON shape (`{ "detail": ... }` or field-keyed validation errors).

## Concurrency strategy (20% — decided deliberately)

- **Whole allocation run wrapped in one `transaction.atomic()`**, with a
  `pg_advisory_xact_lock(<constant>)` acquired at the top so only ONE effective run executes at
  a time (the lock auto-releases at transaction end — this composes correctly, unlike acquiring
  it inside per-order blocks). Per-order work uses nested `atomic()` savepoints.
- **`select_for_update()` on SKU rows, always `.order_by('id')`** to prevent deadlocks — applied
  to cancel/fulfill/stock-adjust too, not just the engine.
- No overselling: order *creation* never touches stock (only allocation reserves), so the only
  oversell vector is concurrent runs, which the advisory lock serializes.
- README documents this choice + the "strict stop vs continue-past-shortages" decision.

## The allocation engine (built LAST, guided, candidate-authored)

Behaviour (FCFS): select PENDING orders ordered by `order_date ASC, created_at ASC`; for each,
lock its SKU rows; if EVERY line fits in `available_quantity` -> reserve (available--,
reserved++), mark ALLOCATED, write ledger; else (all-or-nothing, no partial) -> BACKORDERED (or
stay PENDING if `ALLOCATION_BACKORDER_ON_SHORTAGE=False`) and continue to next order. The
~40-line loop is small and readable on purpose. The candidate writes this and the README design
note; reviews verify they can narrate the worked example
(12 -> 5 ALLOCATED -> 10 BACKORDERED -> 4 ALLOCATED).

## Testing (15% — mandatory coverage)

pytest-django. Cover: auth (register/login/refresh/logout/invalid/expired); authz (customer
can't run allocation, can't see others' orders, operator can't register admins); FCFS backdated
order_date ordering; FCFS shortage skip + later smaller order still allocated; **concurrency**
(TransactionTestCase + threads, each thread its own DB connection, assert no oversell); cancel
of ALLOCATED returns stock; double-fulfillment rejected.

## Commit plan (staged, authored as the candidate)

**STRICT GIT POLICY:** only `git add` + `git commit` locally. **NEVER `git push`**, never add a
remote, never create or touch any GitHub repo. All pushing is done by the candidate, manually.
Git identity is configured locally as **saksham <jainsaksham1004@gmail.com>**; no AI co-author
trailer is ever added. Each stage = one meaningful commit:

0. `docs: project plan` (this PLAN.md)
1. `chore: project scaffold (django, drf, docker-compose, postgres, settings)`
2. `feat: accounts — custom user, JWT auth, role permissions`
3. `feat: inventory — SKU, append-only StockLedger, stock service`
4. `feat: orders — order/orderline, create/cancel/fulfill`
5. `feat: allocation — FCFS engine + advisory-lock concurrency` (CANDIDATE-AUTHORED)
6. `test: comprehensive auth/authz/FCFS/concurrency suite`
7. `docs: README, seed script, OpenAPI (drf-spectacular) schema + Swagger UI`
8. bonuses: `feat: celery periodic allocation`, `feat: audit log summary endpoint`, etc.
9. `feat: next.js frontend demo (login + order + allocation flow)`

## Verification

- `docker-compose up` brings up postgres + web; `python manage.py migrate` + `seed.py`.
- `pytest` green, including the threaded concurrency test on Postgres.
- Manual/curl walkthrough of the worked example matches the PDF 1:1.
- OpenAPI served at `/api/schema/swagger-ui/`.
- Frontend demo flow: login -> place orders -> run allocation -> see ALLOCATED/BACKORDERED.

## Build order

Backend scaffold -> accounts -> inventory -> orders -> **engine (guided, candidate writes)** ->
tests green -> docs/seed/OpenAPI -> bonuses (celery, audit) -> Next.js frontend.
