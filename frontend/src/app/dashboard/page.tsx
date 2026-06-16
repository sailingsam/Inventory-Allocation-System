"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { AllocationRun, Order, Paginated, SKU } from "@/lib/types";

const STATUS_STYLES: Record<string, string> = {
  PENDING: "bg-slate-100 text-slate-600",
  ALLOCATED: "bg-blue-100 text-blue-700",
  FULFILLED: "bg-green-100 text-green-700",
  CANCELLED: "bg-slate-200 text-slate-500 line-through",
  BACKORDERED: "bg-amber-100 text-amber-700",
};

function Badge({ status }: { status: string }) {
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[status] ?? ""}`}>
      {status}
    </span>
  );
}

export default function Dashboard() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();

  const [skus, setSkus] = useState<SKU[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [lastRun, setLastRun] = useState<AllocationRun | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const isPrivileged = user?.role === "WAREHOUSE_OPERATOR" || user?.role === "ADMIN";

  const refresh = useCallback(async () => {
    const [s, o] = await Promise.all([
      api<Paginated<SKU>>("/skus/"),
      api<Paginated<Order>>("/orders/"),
    ]);
    if (s.ok) setSkus(s.data.results);
    if (o.ok) setOrders(o.data.results);
  }, []);

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    refresh();
  }, [user, loading, router, refresh]);

  async function runAllocation() {
    setMsg(null);
    const res = await api<AllocationRun>("/allocation/run/", { method: "POST" });
    if (res.ok) {
      setLastRun(res.data);
      setMsg(
        `Allocation run #${res.data.id}: ${res.data.orders_allocated} allocated, ${res.data.orders_backordered} backordered.`,
      );
      await refresh();
    } else {
      setMsg(`Allocation failed (${res.status}). Is the engine implemented?`);
    }
  }

  async function act(orderId: number, action: "cancel" | "fulfill") {
    const res = await api(`/orders/${orderId}/${action}/`, { method: "POST" });
    setMsg(res.ok ? `Order #${orderId} ${action}led.` : `Could not ${action} order #${orderId}.`);
    await refresh();
  }

  if (loading || !user) {
    return (
      <main className="flex flex-1 items-center justify-center">
        <p className="text-slate-500">Loading…</p>
      </main>
    );
  }

  return (
    <div className="flex flex-1 flex-col">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
        <div>
          <h1 className="font-semibold">Order Management</h1>
          <p className="text-xs text-slate-500">
            {user.email} · <span className="font-medium">{user.role}</span>
          </p>
        </div>
        <div className="flex items-center gap-3">
          {isPrivileged && (
            <button
              onClick={runAllocation}
              className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-700"
            >
              ▶ Run allocation
            </button>
          )}
          <button
            onClick={async () => {
              await logout();
              router.replace("/login");
            }}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm hover:bg-slate-100"
          >
            Logout
          </button>
        </div>
      </header>

      {msg && (
        <div className="border-b border-slate-200 bg-blue-50 px-6 py-2 text-sm text-blue-800">
          {msg}
        </div>
      )}

      <main className="grid flex-1 gap-6 p-6 lg:grid-cols-3">
        <section className="lg:col-span-1">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Inventory
          </h2>
          <div className="space-y-2">
            {skus.map((sku) => (
              <div key={sku.id} className="rounded-xl bg-white p-3 shadow-sm ring-1 ring-slate-200">
                <div className="flex items-center justify-between">
                  <span className="font-medium">{sku.code}</span>
                  <span className="text-xs text-slate-400">{sku.name}</span>
                </div>
                <div className="mt-1 flex gap-4 text-sm">
                  <span>
                    available <b className="text-green-700">{sku.available_quantity}</b>
                  </span>
                  <span>
                    reserved <b className="text-blue-700">{sku.reserved_quantity}</b>
                  </span>
                </div>
              </div>
            ))}
          </div>
          {user.role === "CUSTOMER" && <PlaceOrder skus={skus} onPlaced={refresh} setMsg={setMsg} />}
          {lastRun && (
            <div className="mt-4 rounded-xl bg-white p-3 text-sm shadow-sm ring-1 ring-slate-200">
              <p className="font-medium">Last run #{lastRun.id}</p>
              <p className="text-slate-500">
                processed {lastRun.orders_processed} · allocated {lastRun.orders_allocated} ·
                backordered {lastRun.orders_backordered}
              </p>
            </div>
          )}
        </section>

        <section className="lg:col-span-2">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Orders {isPrivileged ? "(all)" : "(yours)"}
          </h2>
          <div className="overflow-hidden rounded-xl bg-white shadow-sm ring-1 ring-slate-200">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase text-slate-400">
                <tr>
                  <th className="px-3 py-2">#</th>
                  <th className="px-3 py-2">Order date</th>
                  {isPrivileged && <th className="px-3 py-2">Customer</th>}
                  <th className="px-3 py-2">Lines</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => (
                  <tr key={o.id} className="border-t border-slate-100">
                    <td className="px-3 py-2">{o.id}</td>
                    <td className="px-3 py-2">{o.order_date.slice(0, 10)}</td>
                    {isPrivileged && <td className="px-3 py-2 text-slate-500">{o.customer_email}</td>}
                    <td className="px-3 py-2">
                      {o.lines.map((l) => `${l.quantity}×${l.sku_code}`).join(", ")}
                    </td>
                    <td className="px-3 py-2">
                      <Badge status={o.status} />
                    </td>
                    <td className="px-3 py-2 text-right">
                      {o.status === "PENDING" && (
                        <button
                          onClick={() => act(o.id, "cancel")}
                          className="text-xs text-red-600 hover:underline"
                        >
                          cancel
                        </button>
                      )}
                      {isPrivileged && o.status === "ALLOCATED" && (
                        <span className="flex justify-end gap-2">
                          <button
                            onClick={() => act(o.id, "fulfill")}
                            className="text-xs text-green-700 hover:underline"
                          >
                            fulfill
                          </button>
                          <button
                            onClick={() => act(o.id, "cancel")}
                            className="text-xs text-red-600 hover:underline"
                          >
                            cancel
                          </button>
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
                {orders.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-3 py-6 text-center text-slate-400">
                      No orders yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </div>
  );
}

function PlaceOrder({
  skus,
  onPlaced,
  setMsg,
}: {
  skus: SKU[];
  onPlaced: () => Promise<void>;
  setMsg: (m: string) => void;
}) {
  const [skuId, setSkuId] = useState<number | "">("");
  const [qty, setQty] = useState(1);
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!skuId) return;
    setBusy(true);
    const res = await api("/orders/", {
      method: "POST",
      body: JSON.stringify({ lines: [{ sku: skuId, quantity: qty }] }),
    });
    setBusy(false);
    setMsg(res.ok ? "Order placed (PENDING — run allocation to reserve stock)." : "Order failed.");
    if (res.ok) await onPlaced();
  }

  return (
    <div className="mt-4 rounded-xl bg-white p-3 shadow-sm ring-1 ring-slate-200">
      <p className="mb-2 text-sm font-semibold">Place an order</p>
      <div className="flex gap-2">
        <select
          value={skuId}
          onChange={(e) => setSkuId(e.target.value ? Number(e.target.value) : "")}
          className="flex-1 rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
        >
          <option value="">Select SKU…</option>
          {skus.map((s) => (
            <option key={s.id} value={s.id}>
              {s.code}
            </option>
          ))}
        </select>
        <input
          type="number"
          min={1}
          value={qty}
          onChange={(e) => setQty(Math.max(1, Number(e.target.value)))}
          className="w-20 rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
        />
        <button
          onClick={submit}
          disabled={busy || !skuId}
          className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
        >
          Add
        </button>
      </div>
    </div>
  );
}
