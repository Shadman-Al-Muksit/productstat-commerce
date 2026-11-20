"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowUpRight,
  ArrowRight,
  Plus,
  Search,
  Download,
  X,
  Package,
  Truck,
  RefreshCw,
  Edit3,
  SlidersHorizontal,
  AlertTriangle,
  ShieldCheck,
} from "lucide-react";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  ColumnDef,
  SortingState,
} from "@tanstack/react-table";
import { api, list, money, num, pretty, Order } from "@/lib/api";
import { useApp } from "./commerce-app";
import { ProductImagePicker } from "./product-image-picker";
import {
  colourHexError,
  defaultProductImage,
  imageSourceError,
  skuAttributes,
} from "@/lib/product-images";
import {
  Loading,
  Notice,
  Empty,
  Badge,
  Field,
  SectionTitle,
  Stat,
  DateText,
  Pagination,
  useDialogFocus,
} from "./ui";
type Row = Record<string, any>;
export function DataTable({
  data,
  columns,
}: {
  data: Row[];
  columns: ColumnDef<Row, any>[];
}) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });
  return (
    <div className="table-wrap">
      <table>
        <thead>
          {table.getHeaderGroups().map((g) => (
            <tr key={g.id}>
              {g.headers.map((h) => (
                <th key={h.id}>
                  <button
                    className="table-sort"
                    onClick={h.column.getToggleSortingHandler()}
                  >
                    {flexRender(h.column.columnDef.header, h.getContext())}
                    {h.column.getIsSorted() === "asc"
                      ? " ↑"
                      : h.column.getIsSorted() === "desc"
                        ? " ↓"
                        : ""}
                  </button>
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id}>
              {row.getVisibleCells().map((c) => (
                <td key={c.id}>
                  {flexRender(c.column.columnDef.cell, c.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function useRows(endpoint: string) {
  const [rows, setRows] = useState<Row[]>([]);
  const [count, setCount] = useState(0);
  const generation = useRef(0);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const reload = useCallback(async () => {
    const request = ++generation.current;
    setError("");
    setBusy(true);
    try {
      const response = await api<Row>(endpoint);
      if (request !== generation.current) return;
      const records = list<Row>(response);
      setRows(records);
      setCount(response.count ?? records.length);
    } catch (e) {
      if (request === generation.current) setError((e as Error).message);
    } finally {
      if (request === generation.current) setBusy(false);
    }
  }, [endpoint]);
  useEffect(() => {
    reload();
  }, [reload]);
  return { rows, count, busy, error, reload };
}
export function StaffPage({ section }: { section: string }) {
  if (section === "products") return <Products />;
  if (section === "orders") return <Orders />;
  if (section === "returns") return <Returns />;
  if (section === "users") return <Team />;
  if (section === "settings") return <Settings />;
  return <Overview />;
}
function OperationsHealth() {
  const [data, setData] = useState<Row | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const reload = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      setData(await api<Row>("staff/operations-health/"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, []);
  useEffect(() => {
    reload();
  }, [reload]);
  return (
    <section className="panel" aria-label="Operations health">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">REVIEW BEFORE IT BECOMES A PROBLEM</p>
          <h2>Operations health</h2>
        </div>
        <button
          className="button small secondary"
          onClick={reload}
          disabled={busy}
        >
          <RefreshCw size={15} /> Refresh
        </button>
      </div>
      <Notice message={error} />
      {busy ? (
        <Loading />
      ) : (
        data && (
          <>
            <div className="stats-grid">
              <Stat
                label="COD orders waiting 48+ hours"
                value={num(data.counts.overdue_cod_orders)}
                note="Undispatched; review before proceeding"
              />
              <Stat
                label="Exhausted background jobs"
                value={num(data.counts.failed_outbox_jobs)}
                note="Retries exhausted; administrator review"
              />
              <Stat
                label="Failed imports"
                value={num(data.counts.failed_imports)}
                note="Inspect validation and recovery reports"
              />
              <Stat
                label="Payment exceptions"
                value={num(data.counts.payment_exceptions)}
                note="Captured funds still need reconciliation"
              />
            </div>
            {data.overdue_cod_orders?.length > 0 && (
              <DataTable
                data={data.overdue_cod_orders}
                columns={[
                  { accessorKey: "number", header: "Order" },
                  {
                    accessorKey: "status",
                    header: "Status",
                    cell: ({ getValue }) => <Badge value={getValue()} />,
                  },
                  { accessorKey: "age_hours", header: "Hours waiting" },
                  {
                    accessorKey: "created_at",
                    header: "Placed",
                    cell: ({ getValue }) => <DateText value={getValue()} />,
                  },
                ]}
              />
            )}
            <p className="muted">
              Review flags do not cancel orders or change payment states. Up to{" "}
              {data.sample_limit} overdue orders are shown; counts cover all
              matching records.
            </p>
          </>
        )
      )}
    </section>
  );
}
function Overview() {
  const { bootstrap } = useApp();
  const [data, setData] = useState<Row | null>(null);
  const [error, setError] = useState("");
  const { rows, busy } = useRows("staff/orders/?page_size=8");
  useEffect(() => {
    api<Row>("analytics/")
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);
  const s = data?.summary || {};
  return (
    <>
      <SectionTitle
        eyebrow="YOUR BUSINESS AT A GLANCE"
        title="A clearer view of commerce."
        text="Orders, products and operations — connected in one place."
      >
        <Link href="/analytics" className="button primary">
          Explore intelligence
          <ArrowUpRight size={17} />
        </Link>
      </SectionTitle>
      <div className="workspace-welcome">
        <div>
          <span className="live-dot" />
          <strong>
            {String(bootstrap.company?.name || "ProductStat Commerce")}
          </strong>
          <span>Single company · Bangladesh · BDT</span>
        </div>
        <span className="badge demo">SYNTHETIC DEMONSTRATION</span>
      </div>
      <Notice message={error} />
      <div className="stats-grid">
        <Stat
          label="Orders placed"
          value={data ? num(s.orders) : "—"}
          note="Selected activity period"
          accent
        />
        <Stat
          label="Delivered merchandise"
          value={data ? money(s.delivered_value) : "—"}
          note="After allocated product discounts"
        />
        <Stat
          label="Units returned"
          value={data ? num(s.returned_units) : "—"}
          note="Inspected and accepted"
        />
        <Stat
          label="Merchandise refunds"
          value={data ? money(s.refunded_amount) : "—"}
          note="Confirmed; excludes tax and shipping"
        />
      </div>
      <OperationsHealth />
      <div className="workspace-two">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">OPERATIONAL PULSE</p>
              <h2>Recent orders</h2>
            </div>
            <Link href="/staff/orders" className="text-link">
              View all
              <ArrowRight size={16} />
            </Link>
          </div>
          {busy ? (
            <Loading />
          ) : rows.length ? (
            <DataTable
              data={rows.slice(0, 7)}
              columns={[
                {
                  accessorKey: "number",
                  header: "Order",
                  cell: ({ row }) => (
                    <strong>
                      {row.original.order_number ||
                        row.original.number ||
                        row.original.id.slice(0, 8)}
                    </strong>
                  ),
                },
                {
                  accessorKey: "status",
                  header: "Status",
                  cell: ({ getValue }) => <Badge value={getValue()} />,
                },
                {
                  accessorKey: "grand_total",
                  header: "Total",
                  cell: ({ getValue }) => money(getValue()),
                },
                {
                  accessorKey: "created_at",
                  header: "Placed",
                  cell: ({ getValue }) => <DateText value={getValue()} />,
                },
              ]}
            />
          ) : (
            <Empty
              title="Ready for the first order"
              text="New storefront orders will appear here."
            />
          )}
        </section>
        <section className="panel workflow-panel">
          <p className="eyebrow">THE EVERYDAY WORKFLOW</p>
          <h2>
            From good choice
            <br />
            to clear insight.
          </h2>
          {[
            [
              "01",
              "Receive & confirm",
              "Review new orders and available stock.",
            ],
            [
              "02",
              "Prepare & dispatch",
              "Record the courier and tracking reference.",
            ],
            [
              "03",
              "Reconcile & understand",
              "Connect delivery, returns and money.",
            ],
          ].map(([n, t, d]) => (
            <div className="workflow-step" key={n}>
              <span>{n}</span>
              <div>
                <strong>{t}</strong>
                <p>{d}</p>
              </div>
            </div>
          ))}
          <Link className="button secondary full" href="/staff/orders">
            Manage orders
            <ArrowRight size={16} />
          </Link>
        </section>
      </div>
    </>
  );
}
function Orders() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const { rows, count, busy, error, reload } = useRows(
    `staff/orders/?${new URLSearchParams({ q: search, status, page: String(page), page_size: "25" })}`,
  );
  useEffect(() => setPage(1), [search, status]);
  const [selected, setSelected] = useState<Row | null>(null);
  const filtered = rows;
  return (
    <>
      <SectionTitle
        eyebrow="COMMERCE OPERATIONS"
        title="Every order has a story."
        text="Follow each order from confirmation to delivery and reconciliation."
      >
        <button className="button secondary" onClick={reload}>
          <RefreshCw size={16} />
          Refresh
        </button>
      </SectionTitle>
      <div className="stats-grid three">
        <Stat
          label="Loaded orders"
          value={num(rows.length)}
          note="Use search to find a specific order"
        />
        <Stat
          label="Awaiting dispatch"
          value={num(
            rows.filter((r) => r.status === "confirmed" && !r.shipments?.length)
              .length,
          )}
          note="Confirmed and reserved"
        />
        <Stat
          label="Historical records"
          value={num(rows.filter((r) => r.is_historical).length)}
          note="Read-only imported observations"
        />
      </div>
      <Notice message={error} />
      <section className="panel">
        <div className="table-toolbar">
          <label className="search-box">
            <Search size={17} />
            <input
              placeholder="Search order or customer…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <select
            aria-label="Filter order status"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="">All statuses</option>
            {[
              "pending_payment",
              "confirmed",
              "preparing",
              "dispatched",
              "delivered",
              "failed",
              "returned_to_origin",
              "cancelled",
            ].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
          <span className="muted">{count.toLocaleString("en-BD")} records</span>
        </div>
        {busy ? (
          <Loading />
        ) : filtered.length ? (
          <DataTable
            data={filtered}
            columns={[
              {
                accessorKey: "number",
                header: "Order",
                cell: ({ row }) => (
                  <button
                    className="link-button"
                    onClick={() => setSelected(row.original)}
                  >
                    {row.original.order_number ||
                      row.original.number ||
                      row.original.id.slice(0, 8)}
                    <ArrowUpRight size={14} />
                  </button>
                ),
              },
              {
                accessorKey: "customer_name",
                header: "Customer",
                cell: ({ row }) => (
                  <>
                    <strong>
                      {row.original.customer_name || "Historical record"}
                    </strong>
                    <small className="cell-sub">
                      {row.original.is_historical
                        ? "Imported history"
                        : row.original.email || row.original.phone}
                    </small>
                  </>
                ),
              },
              {
                accessorKey: "status",
                header: "Order status",
                cell: ({ getValue }) => <Badge value={getValue()} />,
              },
              {
                accessorKey: "payment_method",
                header: "Payment",
                cell: ({ getValue }) => <Badge value={getValue()} />,
              },
              {
                accessorKey: "grand_total",
                header: "Total",
                cell: ({ getValue }) => money(getValue()),
              },
              {
                accessorKey: "created_at",
                header: "Placed",
                cell: ({ getValue }) => <DateText value={getValue()} />,
              },
            ]}
          />
        ) : (
          <Empty
            title="No matching orders"
            text="Try another search or status."
          />
        )}
        <Pagination page={page} count={count} pageSize={25} onPage={setPage} />
      </section>
      {selected && (
        <OrderDrawer
          order={selected}
          close={() => setSelected(null)}
          onChange={reload}
        />
      )}
    </>
  );
}
function Drawer({
  title,
  subtitle,
  children,
  close,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  close: () => void;
}) {
  const container = useRef<HTMLElement>(null);
  useDialogFocus(true, container, close);
  return (
    <div className="drawer-overlay" onClick={close}>
      <section
        ref={container}
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <header>
          <div>
            <p className="eyebrow">{subtitle || "RECORD DETAILS"}</p>
            <h2>{title}</h2>
          </div>
          <button
            className="icon-button"
            onClick={close}
            aria-label="Close details"
          >
            <X size={21} />
          </button>
        </header>
        <div className="drawer-content">{children}</div>
      </section>
    </div>
  );
}
function OrderDrawer({
  order,
  close,
  onChange,
}: {
  order: Row;
  close: () => void;
  onChange: () => Promise<void>;
}) {
  const { bootstrap } = useApp();
  const [o, setO] = useState(order);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);
  const [action, setAction] = useState("dispatch");
  const [fields, setFields] = useState<Row>({
    carrier: "Demo courier",
    tracking_number: "",
    amount: "",
    reference: "",
  });
  const [cancelQuantities, setCancelQuantities] = useState<
    Record<string, string>
  >({});
  async function perform(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSuccess("");
    setBusy(true);
    try {
      const lines = Object.entries(cancelQuantities)
        .filter(([, quantity]) => Number(quantity) > 0)
        .map(([order_line_id, quantity]) => ({
          order_line_id,
          quantity: Number(quantity),
        }));
      if (action === "cancel" && !lines.length)
        throw new Error(
          "Choose at least one remaining item quantity to cancel.",
        );
      const result = await api<Row>(`staff/orders/${o.id}/action/`, {
        method: "POST",
        body: JSON.stringify({
          action,
          ...(action === "dispatch"
            ? {
                carrier: fields.carrier,
                tracking_number: fields.tracking_number,
              }
            : {}),
          ...(["collect_cod", "settle_cod"].includes(action)
            ? { amount: fields.amount, reference: fields.reference }
            : {}),
          ...(action === "cancel" ? { lines } : {}),
        }),
      });
      setO(result.order || result);
      await onChange();
      setSuccess("Order event recorded with an audit trail.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Drawer
      title={o.order_number || o.number || o.id.slice(0, 8)}
      subtitle="ORDER OPERATIONS"
      close={close}
    >
      <div className="inline-badges">
        <Badge value={o.status} />
        <Badge value={o.payment_method} />
        {o.is_historical && <Badge value="historical" />}
      </div>
      <div className="record-grid">
        <div>
          <small>Customer</small>
          <strong>{o.customer_name || "—"}</strong>
          <p>
            {o.email}
            <br />
            {o.phone}
          </p>
        </div>
        <div>
          <small>Total</small>
          <strong>{money(o.grand_total)}</strong>
          <p>Remaining amount due: {money(o.amount_due)}</p>
          <p>Collection confirmed: {money(o.collected_total)}</p>
          <p>Courier settlement received: {money(o.settled_total)}</p>
          <p>
            <DateText value={o.created_at} />
          </p>
        </div>
      </div>
      <h3>Items</h3>
      {(o.lines || []).map((l: Row) => (
        <div className="list-row" key={l.id}>
          <span>
            <strong>{l.product_name || l.sku_code}</strong>
            <small className="cell-sub">
              {l.sku_code} · {l.quantity} units · {l.cancelled_quantity || 0}{" "}
              cancelled
            </small>
          </span>
          <strong>{money(l.line_total)}</strong>
        </div>
      ))}
      {o.shipments?.length > 0 && (
        <div className="record-box">
          <strong>Shipment</strong>
          <p>
            <Badge value={o.shipments[0].state} />
          </p>
          <p>
            {o.shipments[0].carrier} · {o.shipments[0].tracking_number}
          </p>
        </div>
      )}
      <h3>Recorded payments</h3>
      {(o.payments || []).map((p: Row) => (
        <div className="list-row" key={p.id}>
          <span>
            {pretty(p.kind || p.method)}
            <small className="cell-sub">{p.reference}</small>
          </span>
          <span>
            {money(p.amount)} <Badge value={p.status} />
          </span>
        </div>
      ))}
      {!(o.payments || []).length && (
        <p className="muted">No confirmed money event recorded.</p>
      )}
      <Notice message={error} />
      <Notice message={success} success />
      {!o.is_historical && (
        <form className="action-form" onSubmit={perform}>
          <h3>Record the next event</h3>
          <Field label="Operation">
            <select value={action} onChange={(e) => setAction(e.target.value)}>
              <option value="prepare">Mark preparation started</option>
              <option value="dispatch">Dispatch shipment</option>
              <option value="deliver">Confirm delivery</option>
              <option value="fail">Mark failed delivery</option>
              <option value="return_to_origin">Returned to origin</option>
              <option value="collect_cod">Confirm COD collection</option>
              {["administrator", "admin"].includes(
                bootstrap.user?.role || "",
              ) && (
                <option value="settle_cod">Confirm courier settlement</option>
              )}
              <option value="cancel">Cancel before dispatch</option>
            </select>
          </Field>
          {action === "dispatch" && (
            <>
              <Field label="Courier / carrier">
                <input
                  value={fields.carrier}
                  onChange={(e) =>
                    setFields({ ...fields, carrier: e.target.value })
                  }
                  required
                />
              </Field>
              <Field label="Tracking reference">
                <input
                  value={fields.tracking_number}
                  onChange={(e) =>
                    setFields({ ...fields, tracking_number: e.target.value })
                  }
                  required
                />
              </Field>
            </>
          )}
          {["collect_cod", "settle_cod"].includes(action) && (
            <>
              <Field label="Amount (BDT)">
                <input
                  type="number"
                  min="0.01"
                  step="0.01"
                  value={fields.amount}
                  onChange={(e) =>
                    setFields({ ...fields, amount: e.target.value })
                  }
                  required
                />
              </Field>
              <Field label="Evidence / payment reference">
                <input
                  value={fields.reference}
                  onChange={(e) =>
                    setFields({ ...fields, reference: e.target.value })
                  }
                  required
                />
              </Field>
            </>
          )}
          {action === "cancel" && (
            <div className="variant-editor">
              <h3>Quantities to cancel</h3>
              {(o.lines || []).map((line: Row) => (
                <Field
                  key={line.id}
                  label={`${line.product_name} · ${line.quantity - line.cancelled_quantity} remaining`}
                >
                  <input
                    aria-label={`Cancel quantity ${line.sku_code}`}
                    type="number"
                    min="0"
                    max={line.quantity - line.cancelled_quantity}
                    step="1"
                    value={cancelQuantities[line.id] || "0"}
                    onChange={(e) =>
                      setCancelQuantities({
                        ...cancelQuantities,
                        [line.id]: e.target.value,
                      })
                    }
                  />
                </Field>
              ))}
            </div>
          )}
          <button className="button primary full" disabled={busy}>
            {busy ? "Recording…" : "Record event"}
            <ArrowRight size={16} />
          </button>
          <small className="muted">
            Operations are validated against the current order state.
          </small>
        </form>
      )}
    </Drawer>
  );
}
function Products() {
  const [tab, setTab] = useState("catalog");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const endpoint = `${tab === "catalog" ? "staff/products/" : "staff/inventory/"}?${new URLSearchParams({ q: search, page: String(page), page_size: "25" })}`;
  const { rows, count, busy, error, reload } = useRows(endpoint);
  useEffect(() => setPage(1), [search, tab]);
  const [edit, setEdit] = useState<Row | null>(null);
  const [stock, setStock] = useState<Row | null>(null);
  const filtered = rows;
  return (
    <>
      <SectionTitle
        eyebrow="CATALOGUE & INVENTORY"
        title="Good products. Well managed."
        text="Maintain your collection and keep every stock movement accountable."
      >
        <button
          className="button primary"
          onClick={() =>
            setEdit({
              name: "",
              slug: "",
              category: "",
              description: "",
              image_url: defaultProductImage,
              is_active: true,
              skus: [
                {
                  code: "",
                  label: "Black",
                  price: "0.00",
                  attributes: { color: "Black", color_hex: "#252b32" },
                  is_active: true,
                },
              ],
            })
          }
        >
          <Plus size={17} />
          Add product
        </button>
      </SectionTitle>
      <div className="page-tabs">
        <button
          className={tab === "catalog" ? "selected" : ""}
          onClick={() => setTab("catalog")}
        >
          Product catalogue
        </button>
        <button
          className={tab === "inventory" ? "selected" : ""}
          onClick={() => setTab("inventory")}
        >
          Stock positions
        </button>
        <Link href="/imports">
          Import catalogue
          <ArrowUpRight size={15} />
        </Link>
      </div>
      <Notice message={error} />
      <section className="panel">
        <div className="table-toolbar">
          <label className="search-box">
            <Search size={17} />
            <input
              placeholder="Search products or SKUs…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <span className="muted">{filtered.length} records</span>
        </div>
        {busy ? (
          <Loading />
        ) : filtered.length ? (
          <DataTable
            data={filtered}
            columns={
              tab === "catalog"
                ? [
                    {
                      accessorKey: "name",
                      header: "Product",
                      cell: ({ row }) => (
                        <div className="table-product">
                          <img
                            src={row.original.image_url || defaultProductImage}
                            alt=""
                          />
                          <span>
                            <strong>{row.original.name}</strong>
                            <small>{row.original.category}</small>
                          </span>
                        </div>
                      ),
                    },
                    {
                      accessorKey: "skus",
                      header: "Variants",
                      cell: ({ getValue }) => (getValue() || []).length,
                    },
                    {
                      accessorKey: "min_price",
                      header: "From",
                      cell: ({ row }) =>
                        money(
                          row.original.min_price ||
                            row.original.skus?.[0]?.price,
                        ),
                    },
                    {
                      accessorKey: "is_active",
                      header: "Publication",
                      cell: ({ getValue }) => (
                        <Badge value={getValue() ? "published" : "archived"} />
                      ),
                    },
                    {
                      id: "edit",
                      header: "",
                      cell: ({ row }) => (
                        <button
                          className="button small secondary"
                          onClick={() => setEdit(row.original)}
                        >
                          <Edit3 size={14} />
                          Edit
                        </button>
                      ),
                    },
                  ]
                : [
                    {
                      accessorKey: "product_name",
                      header: "Product",
                      cell: ({ getValue }) => <strong>{getValue()}</strong>,
                    },
                    { accessorKey: "code", header: "SKU" },
                    { accessorKey: "on_hand", header: "On hand" },
                    { accessorKey: "reserved", header: "Reserved" },
                    {
                      accessorKey: "available",
                      header: "Available",
                      cell: ({ getValue }) => (
                        <span
                          className={
                            getValue() <= 0 ? "text-danger" : "text-teal"
                          }
                        >
                          {getValue()}
                        </span>
                      ),
                    },
                    {
                      id: "adjust",
                      header: "",
                      cell: ({ row }) => (
                        <button
                          className="button small secondary"
                          onClick={() => setStock(row.original)}
                        >
                          <SlidersHorizontal size={14} />
                          Adjust
                        </button>
                      ),
                    },
                  ]
            }
          />
        ) : (
          <Empty
            title="Your catalogue starts here"
            text="Add a product or import a validated catalogue."
          />
        )}
        <Pagination page={page} count={count} pageSize={25} onPage={setPage} />
      </section>
      {edit && (
        <ProductEditor
          product={edit}
          close={() => setEdit(null)}
          saved={async () => {
            setEdit(null);
            await reload();
          }}
        />
      )}
      {stock && (
        <StockEditor
          sku={stock}
          close={() => setStock(null)}
          saved={async () => {
            setStock(null);
            await reload();
          }}
        />
      )}
    </>
  );
}
function ProductEditor({
  product,
  close,
  saved,
}: {
  product: Row;
  close: () => void;
  saved: () => Promise<void>;
}) {
  const [p, setP] = useState<Row>(() => {
    const draft = JSON.parse(JSON.stringify(product));
    return {
      ...draft,
      skus: (Array.isArray(draft.skus) ? draft.skus : []).map((sku: Row) => ({
        ...sku,
        attributes: skuAttributes(sku.attributes),
      })),
    };
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  function updateVariant(index: number, values: Row) {
    setP((current: Row) => ({
      ...current,
      skus: current.skus.map((sku: Row, position: number) =>
        position === index ? { ...sku, ...values } : sku,
      ),
    }));
  }
  function updateVariantAttributes(index: number, values: Row) {
    setP((current: Row) => ({
      ...current,
      skus: current.skus.map((sku: Row, position: number) => {
        if (position !== index) return sku;
        const attributes = skuAttributes(sku.attributes);
        const nextColour = values.color;
        const syncLabel =
          typeof nextColour === "string" &&
          nextColour &&
          (!sku.label || sku.label === attributes.color);
        return {
          ...sku,
          label: syncLabel ? nextColour : sku.label,
          attributes: { ...attributes, ...values },
        };
      }),
    }));
  }
  return (
    <Drawer
      title={product.id ? "Edit product" : "Add electronics product"}
      close={close}
      subtitle="PRODUCT CATALOGUE"
    >
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setError("");
          const productImageError = imageSourceError(p.image_url || "");
          if (productImageError) {
            setError(`Product image: ${productImageError}`);
            return;
          }
          for (const [index, variant] of p.skus.entries()) {
            const attributes = skuAttributes(variant.attributes);
            const imageError = imageSourceError(
              typeof attributes.image_url === "string"
                ? attributes.image_url
                : "",
            );
            const colourError = colourHexError(
              typeof attributes.color_hex === "string"
                ? attributes.color_hex
                : "",
            );
            if (imageError || colourError) {
              setError(`Variant ${index + 1}: ${imageError || colourError}`);
              return;
            }
          }
          setBusy(true);
          try {
            await api(`staff/products/${product.id ? `${product.id}/` : ""}`, {
              method: product.id ? "PATCH" : "POST",
              body: JSON.stringify(p),
            });
            await saved();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field label="Product name">
          <input
            required
            value={p.name}
            onChange={(e) =>
              setP({
                ...p,
                name: e.target.value,
                slug: !product.id
                  ? e.target.value
                      .toLowerCase()
                      .replace(/[^a-z0-9]+/g, "-")
                      .replace(/-$/g, "")
                  : p.slug,
              })
            }
          />
        </Field>
        <div className="form-grid">
          <Field label="URL slug">
            <input
              required
              value={p.slug}
              onChange={(e) => setP({ ...p, slug: e.target.value })}
            />
          </Field>
          <Field label="Category">
            <input
              required
              value={p.category}
              onChange={(e) => setP({ ...p, category: e.target.value })}
            />
          </Field>
        </div>
        <Field label="Description">
          <textarea
            rows={4}
            required
            value={p.description}
            onChange={(e) => setP({ ...p, description: e.target.value })}
          />
        </Field>
        <ProductImagePicker
          label="Product image"
          value={typeof p.image_url === "string" ? p.image_url : ""}
          onChange={(image_url) => setP({ ...p, image_url })}
        />
        <label className="checkbox-field">
          <input
            type="checkbox"
            checked={p.is_active}
            onChange={(e) => setP({ ...p, is_active: e.target.checked })}
          />
          Published on storefront
        </label>
        <h3>Sellable variants</h3>
        {p.skus.map((s: Row, i: number) => (
          <fieldset
            className="variant-editor"
            key={s.id || i}
            aria-label={`Variant ${i + 1}: ${s.code || "New SKU"}`}
          >
            <legend className="variant-editor-title">
              Variant {i + 1} · {s.code || "New SKU"}
            </legend>
            <div className="form-grid">
              {[
                ["code", "SKU code"],
                ["label", "Variant label"],
                ["price", "Price (BDT)"],
              ].map(([key, label]) => (
                <Field label={label} key={key}>
                  <input
                    required
                    type={key === "price" ? "number" : "text"}
                    min={key === "price" ? "0.01" : undefined}
                    step={key === "price" ? "0.01" : undefined}
                    value={s[key]}
                    onChange={(e) =>
                      updateVariant(i, { [key]: e.target.value })
                    }
                  />
                </Field>
              ))}
            </div>
            <div className="form-grid variant-colour-fields">
              <Field label="Colour name" hint="Shown with the variant image.">
                <input
                  aria-label="Colour name"
                  value={
                    typeof skuAttributes(s.attributes).color === "string"
                      ? String(skuAttributes(s.attributes).color)
                      : ""
                  }
                  maxLength={120}
                  placeholder="For example, Ocean blue"
                  onChange={(event) =>
                    updateVariantAttributes(i, { color: event.target.value })
                  }
                />
              </Field>
              <Field label="Colour hex" hint="Optional: #416d94 or #369.">
                <div className="colour-preview">
                  <span
                    aria-hidden="true"
                    style={{
                      backgroundColor:
                        typeof skuAttributes(s.attributes).color_hex ===
                          "string" &&
                        !colourHexError(
                          String(skuAttributes(s.attributes).color_hex),
                        )
                          ? String(skuAttributes(s.attributes).color_hex) ||
                            "transparent"
                          : "transparent",
                    }}
                  />
                  <input
                    aria-label="Colour hex"
                    value={
                      typeof skuAttributes(s.attributes).color_hex === "string"
                        ? String(skuAttributes(s.attributes).color_hex)
                        : ""
                    }
                    maxLength={7}
                    placeholder="#416d94"
                    pattern="#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?"
                    title="Use a three- or six-digit hex colour, such as #416d94."
                    onChange={(event) =>
                      updateVariantAttributes(i, {
                        color_hex: event.target.value,
                      })
                    }
                  />
                </div>
              </Field>
            </div>
            <ProductImagePicker
              label="Variant image"
              value={
                typeof skuAttributes(s.attributes).image_url === "string"
                  ? String(skuAttributes(s.attributes).image_url)
                  : ""
              }
              fallback={p.image_url || ""}
              allowInherit
              onChange={(image_url, choice) =>
                updateVariantAttributes(i, {
                  image_url,
                  ...(choice
                    ? { color: choice.colour, color_hex: choice.hex }
                    : {}),
                })
              }
            />
          </fieldset>
        ))}
        <button
          type="button"
          className="text-link"
          onClick={() =>
            setP({
              ...p,
              skus: [
                ...p.skus,
                {
                  code: "",
                  label: "",
                  price: "0.00",
                  attributes: {},
                  is_active: true,
                },
              ],
            })
          }
        >
          <Plus size={16} />
          Add variant
        </button>
        <p className="muted">
          New variants start with zero stock. Add opening stock through an
          audited adjustment.
        </p>
        <Notice message={error} />
        <button className="button primary full" disabled={busy}>
          {busy ? "Saving…" : "Save product"}
          <CheckIcon />
        </button>
      </form>
    </Drawer>
  );
}
function CheckIcon() {
  return <ShieldCheck size={17} />;
}
function StockEditor({
  sku,
  close,
  saved,
}: {
  sku: Row;
  close: () => void;
  saved: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <Drawer title={sku.code} subtitle="AUDITED STOCK ADJUSTMENT" close={close}>
      <p>
        {sku.product_name} · {sku.label}
      </p>
      <div className="record-grid">
        <div>
          <small>On hand</small>
          <strong>{sku.on_hand}</strong>
        </div>
        <div>
          <small>Reserved</small>
          <strong>{sku.reserved}</strong>
        </div>
      </div>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          const d = Object.fromEntries(new FormData(e.currentTarget));
          try {
            await api("staff/inventory/", {
              method: "POST",
              body: JSON.stringify({
                sku_id: sku.id,
                delta: Number(d.delta),
                reason: d.reason,
              }),
            });
            await saved();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field
          label="Quantity change"
          hint="Positive adds stock; negative removes unreserved stock."
        >
          <input
            required
            name="delta"
            type="number"
            step="1"
            placeholder="10 or -2"
          />
        </Field>
        <Field label="Reason / reference">
          <textarea required name="reason" rows={3} />
        </Field>
        <Notice message={error} />
        <button className="button primary full" disabled={busy}>
          Record adjustment
          <ArrowRight size={17} />
        </button>
      </form>
    </Drawer>
  );
}
function Returns() {
  const [tab, setTab] = useState("returns");
  const [page, setPage] = useState(1);
  const { rows, count, busy, error, reload } = useRows(
    `staff/${tab}/?page=${page}&page_size=25`,
  );
  useEffect(() => setPage(1), [tab]);
  const [selected, setSelected] = useState<Row | null>(null);
  const [message, setMessage] = useState("");
  const { bootstrap } = useApp();
  const admin = ["administrator", "admin"].includes(bootstrap.user?.role || "");
  return (
    <>
      <SectionTitle
        eyebrow="AFTER THE DELIVERY"
        title="Make the resolution clear."
        text="Review returned items, inspect stock and reconcile refund obligations."
      />
      <div className="page-tabs">
        <button
          className={tab === "returns" ? "selected" : ""}
          onClick={() => setTab("returns")}
        >
          Return requests
        </button>
        <button
          className={tab === "refunds" ? "selected" : ""}
          onClick={() => setTab("refunds")}
        >
          Refund obligations
        </button>
      </div>
      <Notice message={error || message} />
      <section className="panel">
        {busy ? (
          <Loading />
        ) : rows.length ? (
          <DataTable
            data={rows}
            columns={
              tab === "returns"
                ? [
                    {
                      accessorKey: "order_number",
                      header: "Order",
                      cell: ({ row }) => (
                        <strong>
                          {row.original.order_number ||
                            row.original.order_id?.slice(0, 8)}
                        </strong>
                      ),
                    },
                    {
                      accessorKey: "reason",
                      header: "Reason",
                      cell: ({ getValue }) => pretty(getValue()),
                    },
                    {
                      accessorKey: "status",
                      header: "Status",
                      cell: ({ getValue }) => <Badge value={getValue()} />,
                    },
                    {
                      accessorKey: "created_at",
                      header: "Requested",
                      cell: ({ getValue }) => <DateText value={getValue()} />,
                    },
                    {
                      id: "review",
                      header: "",
                      cell: ({ row }) => (
                        <button
                          className="button small secondary"
                          onClick={() => setSelected(row.original)}
                        >
                          Review
                          <ArrowUpRight size={15} />
                        </button>
                      ),
                    },
                  ]
                : [
                    {
                      accessorKey: "order_number",
                      header: "Order",
                      cell: ({ row }) => (
                        <strong>
                          {row.original.order_number ||
                            row.original.order_id?.slice(0, 8)}
                        </strong>
                      ),
                    },
                    {
                      accessorKey: "amount",
                      header: "Amount",
                      cell: ({ getValue }) => money(getValue()),
                    },
                    {
                      accessorKey: "status",
                      header: "Status",
                      cell: ({ getValue }) => <Badge value={getValue()} />,
                    },
                    { accessorKey: "reference", header: "Evidence reference" },
                    {
                      id: "confirm",
                      header: "",
                      cell: ({ row }) =>
                        admin &&
                        row.original.status !== "paid" &&
                        row.original.status !== "confirmed" ? (
                          <button
                            className="button small secondary"
                            onClick={async () => {
                              const reference = prompt(
                                "Verified refund evidence / transaction reference:",
                              );
                              if (!reference) return;
                              try {
                                await api(
                                  `staff/refunds/${row.original.id}/confirm/`,
                                  {
                                    method: "POST",
                                    body: JSON.stringify({ reference }),
                                  },
                                );
                                await reload();
                              } catch (e) {
                                setMessage((e as Error).message);
                              }
                            }}
                          >
                            Confirm paid
                            <CheckIcon />
                          </button>
                        ) : null,
                    },
                  ]
            }
          />
        ) : (
          <Empty
            title={
              tab === "returns"
                ? "No returns to review"
                : "No refund obligations"
            }
            text="Return and refund records will appear here as events are recorded."
          />
        )}
        <Pagination page={page} count={count} pageSize={25} onPage={setPage} />
      </section>
      {selected && (
        <ReturnDrawer
          record={selected}
          close={() => setSelected(null)}
          saved={reload}
        />
      )}
    </>
  );
}
function ReturnDrawer({
  record,
  close,
  saved,
}: {
  record: Row;
  close: () => void;
  saved: () => Promise<void>;
}) {
  const [r, setR] = useState(record);
  const [action, setAction] = useState("approve");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [lines, setLines] = useState<Row[]>(
    (record.lines || []).map((l: Row) => ({
      ...l,
      accepted_quantity: l.quantity,
      restock_quantity: l.quantity,
      disposition: "restock",
    })),
  );
  return (
    <Drawer
      title={r.order_number || r.order_id?.slice(0, 8) || "Return request"}
      subtitle="RETURN INSPECTION"
      close={close}
    >
      <div className="inline-badges">
        <Badge value={r.status} />
        <Badge value={r.reason} />
      </div>
      <p className="muted">
        Receive and inspect each quantity. Sellable stock and refund obligations
        are recorded separately.
      </p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          try {
            const result = await api<Row>(`staff/returns/${r.id}/action/`, {
              method: "POST",
              body: JSON.stringify({
                action,
                lines: lines.map((l) => ({
                  id: l.id,
                  accepted_quantity: Number(l.accepted_quantity),
                  restock_quantity: Number(l.restock_quantity),
                  disposition: l.disposition,
                })),
              }),
            });
            setR(result.return || result);
            await saved();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field label="Next action">
          <select value={action} onChange={(e) => setAction(e.target.value)}>
            <option value="approve">Approve request</option>
            <option value="reject">Reject request</option>
            <option value="receive">Record physical receipt</option>
            <option value="inspect">Complete inspection</option>
          </select>
        </Field>
        {lines.map((l, i) => (
          <div className="variant-editor" key={l.id}>
            <strong>{l.product_name || l.order_line_id}</strong>
            <p className="muted">Requested quantity: {l.quantity}</p>
            {action === "inspect" && (
              <>
                <div className="form-grid">
                  <Field label="Accepted quantity">
                    <input
                      type="number"
                      min="0"
                      max={l.quantity}
                      value={l.accepted_quantity}
                      onChange={(e) =>
                        setLines(
                          lines.map((a, j) =>
                            i === j
                              ? {
                                  ...a,
                                  accepted_quantity: Number(e.target.value),
                                }
                              : a,
                          ),
                        )
                      }
                    />
                  </Field>
                  <Field label="Restock quantity">
                    <input
                      type="number"
                      min="0"
                      max={l.accepted_quantity}
                      value={l.restock_quantity}
                      onChange={(e) =>
                        setLines(
                          lines.map((a, j) =>
                            i === j
                              ? {
                                  ...a,
                                  restock_quantity: Number(e.target.value),
                                }
                              : a,
                          ),
                        )
                      }
                    />
                  </Field>
                </div>
                <Field label="Disposition">
                  <select
                    value={l.disposition}
                    onChange={(e) =>
                      setLines(
                        lines.map((a, j) =>
                          i === j
                            ? {
                                ...a,
                                disposition: e.target.value,
                                restock_quantity:
                                  e.target.value === "restock"
                                    ? a.accepted_quantity
                                    : 0,
                              }
                            : a,
                        ),
                      )
                    }
                  >
                    <option value="restock">Restock sellable items</option>
                    <option value="quarantine">Quarantine</option>
                    <option value="dispose">Dispose</option>
                  </select>
                </Field>
              </>
            )}
          </div>
        ))}
        <Notice message={error} />
        <button className="button primary full" disabled={busy}>
          {busy ? "Recording…" : "Record return action"}
          <ArrowRight size={16} />
        </button>
      </form>
    </Drawer>
  );
}
function Team() {
  const { rows, busy, error, reload } = useRows("staff/users/");
  const [notice, setNotice] = useState("");
  const [open, setOpen] = useState(false);
  return (
    <>
      <SectionTitle
        eyebrow="PEOPLE & PERMISSIONS"
        title="The right access. For every role."
        text="Company access is enforced across the backend, not just the interface."
      >
        <button className="button primary" onClick={() => setOpen(true)}>
          <Plus size={17} />
          Add team member
        </button>
      </SectionTitle>
      <Notice message={error || notice} />
      <section className="panel">
        {busy ? (
          <Loading />
        ) : (
          <DataTable
            data={rows}
            columns={[
              {
                accessorKey: "username",
                header: "Team member",
                cell: ({ row }) => (
                  <>
                    <strong>{row.original.username}</strong>
                    <small className="cell-sub">{row.original.email}</small>
                  </>
                ),
              },
              {
                accessorKey: "role",
                header: "Role",
                cell: ({ row }) => (
                  <select
                    aria-label={`Role for ${row.original.username}`}
                    value={row.original.role}
                    onChange={async (e) => {
                      try {
                        await api(`staff/users/${row.original.id}/`, {
                          method: "PATCH",
                          body: JSON.stringify({ role: e.target.value }),
                        });
                        await reload();
                      } catch (e) {
                        setNotice((e as Error).message);
                      }
                    }}
                  >
                    {["administrator", "operator", "analyst", "customer"].map(
                      (role) => (
                        <option key={role}>{role}</option>
                      ),
                    )}
                  </select>
                ),
              },
              {
                accessorKey: "is_active",
                header: "Account",
                cell: ({ getValue }) => (
                  <Badge value={getValue() === false ? "inactive" : "active"} />
                ),
              },
            ]}
          />
        )}
      </section>
      {open && (
        <Drawer title="Add team member" close={() => setOpen(false)}>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              try {
                await api("staff/users/", {
                  method: "POST",
                  body: JSON.stringify(
                    Object.fromEntries(new FormData(e.currentTarget)),
                  ),
                });
                setOpen(false);
                await reload();
              } catch (e) {
                setNotice((e as Error).message);
              }
            }}
          >
            <Field label="Username">
              <input name="username" required />
            </Field>
            <Field label="Email">
              <input name="email" type="email" required />
            </Field>
            <Field label="Temporary password">
              <input name="password" type="password" minLength={10} required />
            </Field>
            <Field label="Role">
              <select name="role">
                <option>operator</option>
                <option>analyst</option>
                <option>administrator</option>
              </select>
            </Field>
            <Notice message={notice} />
            <button className="button primary full">
              Create account
              <Plus size={16} />
            </button>
          </form>
        </Drawer>
      )}
    </>
  );
}
function Settings() {
  const [settings, setSettings] = useState<Row | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  useEffect(() => {
    api<Row>("staff/settings/")
      .then(setSettings)
      .catch((e) => setError(e.message));
  }, []);
  return (
    <>
      <SectionTitle
        eyebrow="YOUR OPERATING DEFAULTS"
        title="A consistent foundation."
        text="Keep company details, delivery rules and policies explicit."
      />
      <Notice message={error} />
      <Notice message={success} success />
      {!settings ? (
        <Loading />
      ) : (
        <form
          className="panel settings-form"
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              const result = await api<Row>("staff/settings/", {
                method: "PATCH",
                body: JSON.stringify(settings),
              });
              setSettings(result);
              setSuccess("Company settings saved.");
            } catch (e) {
              setError((e as Error).message);
            }
          }}
        >
          <h2>Company profile</h2>
          <div className="form-grid">
            {[
              ["name", "Company name"],
              ["tax_rate", "Tax rate (%)"],
              ["support_email", "Support email"],
              ["return_window_days", "Return window (days)"],
            ].map(([key, label]) => (
              <Field label={label} key={key}>
                <input
                  type={
                    key === "return_window_days" || key === "tax_rate"
                      ? "number"
                      : key === "support_email"
                        ? "email"
                        : "text"
                  }
                  min={key === "tax_rate" ? "0" : undefined}
                  max={key === "tax_rate" ? "100" : undefined}
                  step={key === "tax_rate" ? "0.01" : undefined}
                  required
                  value={settings[key] ?? ""}
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      [key]:
                        key === "return_window_days"
                          ? Number(e.target.value)
                          : e.target.value,
                    })
                  }
                />
              </Field>
            ))}
          </div>
          <div className="record-box">
            <strong>Bangladesh · BDT · Asia/Dhaka</strong>
            <p>
              One company, one warehouse. Sandbox transactions remain separate
              from real fulfilment.
            </p>
          </div>
          <h2>Delivery zones</h2>
          {(settings.delivery_zones || []).map((z: Row, i: number) => (
            <div className="form-grid" key={z.id}>
              <Field label="Zone name">
                <input
                  value={z.name}
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      delivery_zones: settings.delivery_zones.map(
                        (a: Row, j: number) =>
                          j === i ? { ...a, name: e.target.value } : a,
                      ),
                    })
                  }
                />
              </Field>
              <Field label="Delivery charge (BDT)">
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={z.charge}
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      delivery_zones: settings.delivery_zones.map(
                        (a: Row, j: number) =>
                          j === i ? { ...a, charge: e.target.value } : a,
                      ),
                    })
                  }
                />
              </Field>
            </div>
          ))}
          <button className="button primary">
            Save company settings
            <CheckIcon />
          </button>
        </form>
      )}
    </>
  );
}
