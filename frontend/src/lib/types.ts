export type Role = "CUSTOMER" | "WAREHOUSE_OPERATOR" | "ADMIN";

export interface User {
  id: number;
  email: string;
  role: Role;
}

export interface AdminUser {
  id: number;
  email: string;
  role: Role;
  is_active: boolean;
  date_joined: string;
}

export interface SKU {
  id: number;
  code: string;
  name: string;
  available_quantity: number;
  reserved_quantity: number;
}

export interface OrderLine {
  id: number;
  sku: number;
  sku_code: string;
  quantity: number;
}

export type OrderStatus =
  | "PENDING"
  | "ALLOCATED"
  | "FULFILLED"
  | "CANCELLED"
  | "BACKORDERED";

export interface Order {
  id: number;
  customer: number;
  customer_email: string;
  order_date: string;
  status: OrderStatus;
  created_at: string;
  allocated_at: string | null;
  fulfilled_at: string | null;
  cancelled_at: string | null;
  lines: OrderLine[];
}

export interface Paginated<T> {
  count: number;
  results: T[];
}

export interface AllocationRun {
  id: number;
  orders_processed: number;
  orders_allocated: number;
  orders_backordered: number;
}
