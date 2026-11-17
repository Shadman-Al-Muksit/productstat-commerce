"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowUpRight,
  ArrowRight,
  Download,
  CalendarDays,
  ChevronDown,
  TrendingUp,
  Layers3,
  Info,
  X,
  Upload,
  FileSpreadsheet,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  BarChart,
  Bar,
} from "recharts";
import { ColumnDef } from "@tanstack/react-table";
import { api, list, money, num, pretty } from "@/lib/api";
import { useApp } from "./commerce-app";
import { DataTable } from "./staff";
import {
  Loading,
  Notice,
  Empty,
  Badge,
  Field,
  SectionTitle,
  DateText,
  useDialogFocus,
} from "./ui";
type Row = Record<string, any>;
function dateString(date: Date) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Dhaka",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}
export function AnalyticsPage() {
  const today = dateString(new Date());
  const last = dateString(new Date(Date.now() - 29 * 86400000));
  const [start, setStart] = useState(last);
  const [end, setEnd] = useState(today);
  const [ids, setIds] = useState<string[]>([]);
  const [products, setProducts] = useState<Row[]>([]);
  const [productSearch, setProductSearch] = useState("");
  const [data, setData] = useState<Row | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState(
    new URLSearchParams({ start: last, end: today }).toString(),
  );
  const [tab, setTab] = useState("overview");
  const [metric, setMetric] = useState("");
  const [drill, setDrill] = useState<Row | null>(null);
  const [drillBusy, setDrillBusy] = useState(false);
  const metricDialog = useRef<HTMLElement>(null);
  useDialogFocus(Boolean(metric), metricDialog, () => setMetric(""));
  useEffect(() => {
    api(
      `catalog/products/?page_size=200&q=${encodeURIComponent(productSearch)}`,
    )
      .then((d) => setProducts(list(d)))
      .catch(() => {});
  }, [productSearch]);
  useEffect(() => {
    let active = true;
    setBusy(true);
    setError("");
    api<Row>(`analytics/?${query}`)
      .then((d) => active && setData(d))
      .catch((e) => active && setError(e.message))
      .finally(() => active && setBusy(false));
    return () => {
      active = false;
    };
  }, [query]);
  useEffect(() => {
    if (!metric) return;
    let active = true;
    setDrillBusy(true);
    setDrill(null);
    api<Row>(`analytics/drilldown/?${query}&metric=${metric}&page_size=50`)
      .then((d) => active && setDrill(d))
      .catch((e) => active && setError(e.message))
      .finally(() => active && setDrillBusy(false));
    return () => {
      active = false;
    };
  }, [metric, query]);
  const s = data?.summary || {};
  const c = data?.cohort || {};
  const changes = data?.comparison?.change_percent || {};
  const trend = (data?.trend || []).map((r: Row) => ({
    ...r,
    delivered_value: Number(r.delivered_value),
    ordered_value: Number(r.ordered_value),
    refunded_amount: Number(r.refunded_amount),
  }));
  const rows = data?.products || [];
  function apply(e: React.FormEvent) {
    e.preventDefault();
    setQuery(
      new URLSearchParams({
        start,
        end,
        ...(ids.length ? { product_ids: ids.join(",") } : {}),
      }).toString(),
    );
  }
  const change = (key: string) =>
    changes[key] === null || changes[key] === undefined
      ? "No comparable prior activity"
      : `${Number(changes[key]) >= 0 ? "+" : ""}${Number(changes[key]).toFixed(1)}% vs previous period`;
  return (
    <>
      <SectionTitle
        eyebrow="PRODUCT INTELLIGENCE"
        title="See the whole picture."
        text="Understand what moves, what arrives, and what comes back."
      >
        <a
          href={`/api/v1/analytics/export/?${query}&metric=delivered_units`}
          className="button secondary"
        >
          <Download size={16} />
          Export report
        </a>
      </SectionTitle>
      <div className="insight-banner">
        <div>
          <span className="insight-icon">
            <Layers3 size={20} />
          </span>
          <span>
            <strong>One connected view of your products.</strong>
            <small>
              Every number connects to a real record. Explore the detail behind
              the trend.
            </small>
          </span>
        </div>
        <span className="badge demo">SYNTHETIC DEMONSTRATION</span>
      </div>
      <form className="analytics-filters" onSubmit={apply}>
        <div className="date-picker">
          <CalendarDays size={17} />
          <input
            aria-label="Start date"
            type="date"
            value={start}
            max={end}
            onChange={(e) => setStart(e.target.value)}
            required
          />
          <span>→</span>
          <input
            aria-label="End date"
            type="date"
            value={end}
            min={start}
            max={today}
            onChange={(e) => setEnd(e.target.value)}
            required
          />
        </div>
        <details className="product-filter">
          <summary>
            <Layers3 size={16} />
            {ids.length ? `${ids.length} selected products` : "All products"}
            <ChevronDown size={15} />
          </summary>
          <div>
            <input
              className="filter-search"
              aria-label="Search comparison products"
              placeholder="Find a product…"
              value={productSearch}
              onChange={(e) => setProductSearch(e.target.value)}
            />
            <button
              type="button"
              className="text-link"
              onClick={() => setIds([])}
            >
              Clear selection
            </button>
            {products.map((p) => (
              <label key={p.id}>
                <input
                  type="checkbox"
                  checked={ids.includes(String(p.id))}
                  onChange={(e) =>
                    setIds(
                      e.target.checked
                        ? [...ids, String(p.id)]
                        : ids.filter((id) => id !== String(p.id)),
                    )
                  }
                />
                {p.name}
              </label>
            ))}
          </div>
        </details>
        <button className="button primary" disabled={busy}>
          Apply filters
          <ArrowRight size={16} />
        </button>
        <span className="filter-timezone">BDT · Asia/Dhaka</span>
      </form>
      <Notice message={error} />
      <div className="page-tabs">
        <button
          className={tab === "overview" ? "selected" : ""}
          onClick={() => setTab("overview")}
        >
          Performance overview
        </button>
        <button
          className={tab === "products" ? "selected" : ""}
          onClick={() => setTab("products")}
        >
          Product comparison
        </button>
        <button
          className={tab === "operations" ? "selected" : ""}
          onClick={() => setTab("operations")}
        >
          Delivery & returns
        </button>
      </div>
      {busy ? (
        <Loading label="Connecting the numbers…" />
      ) : !data ? (
        <Empty
          title="No analytics available"
          text="Please check your access or try again."
        />
      ) : (
        <>
          <div className="stats-grid">
            <MetricCard
              label="Orders placed"
              value={num(s.orders)}
              note={change("orders")}
              onClick={() => setMetric("orders")}
              accent
            />
            <MetricCard
              label="Delivered merchandise"
              value={money(s.delivered_value)}
              note={change("delivered_value")}
              onClick={() => setMetric("delivered_units")}
            />
            <MetricCard
              label="Accepted returned units"
              value={num(s.returned_units)}
              note="Inspected and accepted in this period"
              onClick={() => setMetric("returned_units")}
            />
            <MetricCard
              label="Confirmed refunds"
              value={money(s.refunded_amount)}
              note="Confirmed money events, not obligations"
              onClick={() => setMetric("refunds")}
            />
          </div>
          {tab === "overview" && (
            <>
              <div className="chart-layout">
                <section className="panel revenue-panel">
                  <div className="panel-heading">
                    <div>
                      <p className="eyebrow">THE SHAPE OF YOUR BUSINESS</p>
                      <h2>Merchandise performance</h2>
                    </div>
                    <div className="chart-legend">
                      <span>
                        <i className="dot teal" />
                        Delivered
                      </span>
                      <span>
                        <i className="dot light" />
                        Ordered
                      </span>
                    </div>
                  </div>
                  <div className="chart-container">
                    <ResponsiveContainer
                      width="100%"
                      height="100%"
                      minWidth={0}
                    >
                      <AreaChart
                        data={trend}
                        margin={{ top: 15, right: 8, left: 0, bottom: 0 }}
                      >
                        <defs>
                          <linearGradient
                            id="deliveredFill"
                            x1="0"
                            y1="0"
                            x2="0"
                            y2="1"
                          >
                            <stop
                              offset="0%"
                              stopColor="#168675"
                              stopOpacity={0.22}
                            />
                            <stop
                              offset="100%"
                              stopColor="#168675"
                              stopOpacity={0}
                            />
                          </linearGradient>
                        </defs>
                        <CartesianGrid vertical={false} stroke="#eef0ef" />
                        <XAxis
                          dataKey="date"
                          axisLine={false}
                          tickLine={false}
                          minTickGap={35}
                          tick={{ fontSize: 11, fill: "#85918d" }}
                          tickFormatter={(d) =>
                            new Date(d).toLocaleDateString("en-GB", {
                              day: "numeric",
                              month: "short",
                            })
                          }
                        />
                        <YAxis
                          width={56}
                          axisLine={false}
                          tickLine={false}
                          tick={{ fontSize: 11, fill: "#85918d" }}
                          tickFormatter={(n) =>
                            Number(n) >= 1000
                              ? `${Number(n) / 1000}k`
                              : String(n)
                          }
                        />
                        <Tooltip
                          formatter={(v) => money(v)}
                          labelFormatter={(d) => String(d)}
                          contentStyle={{
                            border: "1px solid #e1e7e3",
                            borderRadius: 10,
                            fontSize: 12,
                          }}
                        />
                        <Area
                          isAnimationActive={false}
                          type="monotone"
                          dataKey="ordered_value"
                          name="Ordered merchandise"
                          stroke="#b5c7bd"
                          strokeWidth={1.5}
                          fill="transparent"
                          strokeDasharray="4 4"
                        />
                        <Area
                          isAnimationActive={false}
                          type="monotone"
                          dataKey="delivered_value"
                          name="Delivered merchandise"
                          stroke="#168675"
                          strokeWidth={2.4}
                          fill="url(#deliveredFill)"
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="chart-footnote">
                    <Info size={14} />
                    Activity uses each event’s date. Merchandise excludes
                    shipping and tax.
                  </div>
                </section>
                <section className="panel net-panel">
                  <p className="eyebrow">AFTER THE RETURNS</p>
                  <h2>
                    Net delivered
                    <br />
                    merchandise value
                  </h2>
                  <strong className="net-number">
                    {money(s.net_delivered_value)}
                  </strong>
                  <p>Delivered merchandise less inspected, accepted returns.</p>
                  <div className="net-divider" />
                  <div className="list-row">
                    <span>Delivered units</span>
                    <strong>{num(s.delivered_units)}</strong>
                  </div>
                  <div className="list-row">
                    <span>Ordered units</span>
                    <strong>{num(s.ordered_units)}</strong>
                  </div>
                  <div className="list-row">
                    <span>Accepted returns</span>
                    <strong>{num(s.returned_units)}</strong>
                  </div>
                  <p className="net-warning">
                    <Info size={14} />
                    Merchandise value is separate from collected cash.
                  </p>
                </section>
              </div>
              <ProductPerformance
                rows={rows.slice(0, 8)}
                setMetric={setMetric}
              />
            </>
          )}
          {tab === "products" && (
            <>
              <div className="comparison-intro">
                <div>
                  <h2>Compare on the same terms.</h2>
                  <p className="muted">
                    All products use the same selected dates and definitions.
                    Order counts across products may overlap.
                  </p>
                </div>
                <span className="badge">{rows.length} products</span>
              </div>
              <ProductPerformance rows={rows} setMetric={setMetric} />
              {rows.length > 0 && (
                <section className="panel comparison-chart">
                  <div className="panel-heading">
                    <h2>Delivered merchandise by product</h2>
                    <span className="muted">
                      Top 8 in the filtered selection
                    </span>
                  </div>
                  <div className="chart-container">
                    <ResponsiveContainer
                      width="100%"
                      height="100%"
                      minWidth={0}
                    >
                      <BarChart
                        data={rows.slice(0, 8).map((p: Row) => ({
                          ...p,
                          value: Number(p.delivered_value),
                          short:
                            p.name.length > 18
                              ? `${p.name.slice(0, 18)}…`
                              : p.name,
                        }))}
                      >
                        <CartesianGrid vertical={false} stroke="#eef0ef" />
                        <XAxis
                          dataKey="short"
                          axisLine={false}
                          tickLine={false}
                          tick={{ fontSize: 10 }}
                        />
                        <YAxis
                          tickFormatter={(n) => `${Number(n) / 1000}k`}
                          axisLine={false}
                          tickLine={false}
                          tick={{ fontSize: 11 }}
                        />
                        <Tooltip formatter={(v) => money(v)} />
                        <Bar
                          isAnimationActive={false}
                          dataKey="value"
                          name="Delivered merchandise"
                          fill="#198573"
                          radius={[5, 5, 0, 0]}
                          maxBarSize={48}
                        />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </section>
              )}
            </>
          )}
          {tab === "operations" && (
            <>
              <div className="workspace-two">
                <section className="panel">
                  <p className="eyebrow">FOLLOW THE SAME GROUP</p>
                  <h2>Delivery & return cohorts</h2>
                  <Badge
                    value={
                      c.preliminary ? "preliminary cohort" : "mature cohort"
                    }
                  />
                  <p className="muted">
                    {c.basis ||
                      data.meta?.basis ||
                      "Follow the selected cohort through delivery and returns."}
                  </p>
                  <div className="cohort-metrics">
                    <div>
                      <span>Terminal delivery success</span>
                      <strong>{data.delivery?.success_rate ?? "—"}%</strong>
                      <small>Open shipments are reported separately.</small>
                    </div>
                    <div>
                      <span>Product return rate</span>
                      <strong>{c.return_rate ?? "—"}%</strong>
                      <small>
                        Returned units from the same delivered cohort.
                      </small>
                    </div>
                  </div>
                  <div className="list-row">
                    <span>Delivered cohort units</span>
                    <strong>{num(c.delivered_units)}</strong>
                  </div>
                  <div className="list-row">
                    <span>Returned cohort units</span>
                    <strong>{num(c.returned_units)}</strong>
                  </div>
                  {c.open_window_units !== undefined && (
                    <div className="list-row">
                      <span>Units with an open return window</span>
                      <strong>{num(c.open_window_units)}</strong>
                    </div>
                  )}
                  <div className="info-note">
                    <Info size={16} />
                    <p>
                      Recent cohorts remain preliminary until their return
                      window has passed and open cases are resolved. Observation
                      cutoff:{" "}
                      <DateText value={c.as_of || data.meta?.generated_at} />.
                    </p>
                  </div>
                </section>
                <section className="panel">
                  <p className="eyebrow">MONEY IS ITS OWN STORY</p>
                  <h2>Reconcile the actual events.</h2>
                  <span className="badge">
                    Company-wide · Product filter does not apply
                  </span>
                  <p className="muted">{data.cash?.basis}</p>
                  <p className="muted">
                    An order can be delivered while money remains unsettled. A
                    return can be accepted while its refund remains pending.
                  </p>
                  {[
                    ["COD collected", data.cash?.cod_collected_amount],
                    ["Courier settlements", data.cash?.settled_amount],
                    ["Online payments", data.cash?.online_collected_amount],
                    [
                      "Sandbox receipts (separate)",
                      data.cash?.sandbox_collected_amount,
                    ],
                    [
                      "Reconciliation exceptions",
                      data.cash?.exception_collected_amount,
                    ],
                  ].map(([label, value]) => (
                    <div className="money-row" key={String(label)}>
                      <span>{label}</span>
                      <strong>
                        {value === undefined ? "Not available" : money(value)}
                      </strong>
                    </div>
                  ))}
                  <button
                    className="button secondary full"
                    onClick={() => setMetric("refunds")}
                  >
                    Inspect confirmed refunds
                    <ArrowUpRight size={16} />
                  </button>
                </section>
              </div>
              {Array.isArray(data.return_reasons) && (
                <section className="panel">
                  <div className="panel-heading">
                    <h2>Why products come back</h2>
                  </div>
                  <DataTable
                    data={data.return_reasons}
                    columns={[
                      {
                        accessorKey: "reason",
                        header: "Reason",
                        cell: ({ getValue }) => pretty(getValue()),
                      },
                      { accessorKey: "units", header: "Accepted units" },
                      { accessorKey: "count", header: "Return cases" },
                    ]}
                  />
                </section>
              )}
            </>
          )}
          <div className="analytics-provenance">
            <span className="live-dot" />
            <span>
              Generated <DateText value={data.meta?.generated_at} />
            </span>
            <span>Customer details excluded</span>
            <span>Source: transactional records</span>
          </div>
        </>
      )}
      {metric && (
        <div className="modal-overlay" onClick={() => setMetric("")}>
          <section
            className="modal wide"
            role="dialog"
            aria-modal="true"
            ref={metricDialog}
            aria-label="Metric contributing records"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="panel-heading">
              <div>
                <p className="eyebrow">THE RECORDS BEHIND THE NUMBER</p>
                <h2>{pretty(metric)}</h2>
                <p className="muted">
                  Same filters, same calculation basis. Customer details
                  excluded.
                </p>
              </div>
              <button
                className="icon-button"
                onClick={() => setMetric("")}
                aria-label="Close contributing records"
              >
                <X />
              </button>
            </div>
            <div className="drill-toolbar">
              <span>
                {drill?.count ?? "—"} contributing records · showing first 50
              </span>
              <a
                href={`/api/v1/analytics/export/?${query}&metric=${metric}`}
                className="button small secondary"
              >
                <Download size={15} />
                Export all filtered rows
              </a>
            </div>
            {drillBusy ? (
              <Loading />
            ) : drill?.results?.length ? (
              <DataTable
                data={drill.results}
                columns={[
                  { accessorKey: "order_number", header: "Order" },
                  { accessorKey: "product_name", header: "Product" },
                  { accessorKey: "sku", header: "SKU" },
                  { accessorKey: "quantity", header: "Units" },
                  {
                    accessorKey: "value",
                    header: "Value",
                    cell: ({ getValue }) => money(getValue()),
                  },
                  {
                    accessorKey: "event_at",
                    header: "Event date",
                    cell: ({ getValue }) => <DateText value={getValue()} />,
                  },
                  {
                    accessorKey: "status",
                    header: "Status",
                    cell: ({ getValue }) => <Badge value={getValue()} />,
                  },
                ]}
              />
            ) : (
              <Empty
                title="No contributing records"
                text="Try another period or product selection."
              />
            )}
          </section>
        </div>
      )}
    </>
  );
}
function MetricCard({
  label,
  value,
  note,
  onClick,
  accent = false,
}: {
  label: string;
  value: string;
  note: string;
  onClick: () => void;
  accent?: boolean;
}) {
  return (
    <button
      className={`stat metric-card ${accent ? "accent" : ""}`}
      onClick={onClick}
    >
      <div className="stat-top">
        <span>{label}</span>
        <ArrowUpRight size={17} />
      </div>
      <strong>{value}</strong>
      <small>{note}</small>
      <span className="inspect-label">
        Inspect records
        <ArrowUpRight size={12} />
      </span>
    </button>
  );
}
function ProductPerformance({
  rows,
  setMetric,
}: {
  rows: Row[];
  setMetric: (metric: string) => void;
}) {
  const columns: ColumnDef<Row, any>[] = [
    {
      accessorKey: "name",
      header: "Product",
      cell: ({ row }) => (
        <div className="table-product">
          <img src={row.original.image_url || "/products/tote.svg"} alt="" />
          <span>
            <strong>{row.original.name}</strong>
            <small>{row.original.category}</small>
          </span>
        </div>
      ),
    },
    {
      accessorKey: "ordered_units",
      header: "Ordered units",
      cell: ({ getValue }) => num(getValue()),
    },
    {
      accessorKey: "delivered_units",
      header: "Delivered",
      cell: ({ getValue }) => num(getValue()),
    },
    {
      accessorKey: "returned_units",
      header: "Returned",
      cell: ({ getValue }) => (
        <span className="return-number">{num(getValue())}</span>
      ),
    },
    {
      accessorKey: "delivered_value",
      header: "Delivered value",
      cell: ({ getValue }) => money(getValue()),
    },
    {
      accessorKey: "net_delivered_value",
      header: "Net delivered",
      cell: ({ getValue }) => (
        <strong className="text-teal">{money(getValue())}</strong>
      ),
    },
  ];
  return (
    <section className="panel product-performance">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">FROM THE COLLECTION</p>
          <h2>Product performance</h2>
        </div>
        <span className="muted">Same period · BDT</span>
      </div>
      {rows.length ? (
        <DataTable data={rows} columns={columns} />
      ) : (
        <Empty
          title="No product activity in this period"
          text="Choose a wider date range or clear the product filter."
        />
      )}
      <div className="table-footer">
        <span>Compare units and merchandise value separately.</span>
        <button
          className="text-link"
          onClick={() => setMetric("delivered_units")}
        >
          Inspect delivery records
          <ArrowUpRight size={15} />
        </button>
      </div>
    </section>
  );
}
export function ImportsPage() {
  const { bootstrap } = useApp();
  const [rows, setRows] = useState<Row[]>([]);
  const [kind, setKind] = useState("history");
  const [selected, setSelected] = useState<Row | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [source, setSource] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [uploadOpen, setUploadOpen] = useState(true);
  const importDialog = useRef<HTMLElement>(null);
  useDialogFocus(Boolean(selected), importDialog, () => setSelected(null));
  const canWrite = ["administrator", "operator", "admin"].includes(
    bootstrap.user?.role || "",
  );
  async function reload() {
    try {
      setRows(list(await api("imports/")));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    reload();
  }, []);
  useEffect(() => {
    if (!selected || ["completed", "failed", "ready"].includes(selected.status))
      return;
    const timer = setInterval(() => {
      api<Row>(`imports/${selected.id}/`)
        .then((b) => {
          setSelected(b);
          if (["completed", "ready", "failed"].includes(b.status)) reload();
        })
        .catch((e) => setError(e.message));
    }, 1500);
    return () => clearInterval(timer);
  }, [selected?.id, selected?.status]);
  async function upload(e: React.FormEvent) {
    e.preventDefault();
    if (!files.length) return;
    setError("");
    setBusy(true);
    try {
      const data = new FormData();
      data.append("kind", kind);
      data.append("source_name", source);
      files.forEach((file) => data.append("files", file));
      const result = await api<Row>("imports/", { method: "POST", body: data });
      setSelected(result);
      await reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const kinds = [
    {
      key: "catalog",
      name: "Product catalogue",
      text: "Validated products and sellable variants.",
    },
    {
      key: "opening_stock",
      name: "Opening inventory",
      text: "A declared opening position before trading.",
    },
    {
      key: "adjustments",
      name: "Stock adjustments",
      text: "Auditable changes to current inventory.",
    },
    {
      key: "history",
      name: "Historical transactions",
      text: "Backfill analytics without live side effects.",
    },
  ];
  return (
    <>
      <SectionTitle
        eyebrow="TRUST STARTS AT THE SOURCE"
        title="Bring your records together."
        text="Preview, validate and reconcile data before it becomes part of your business."
      >
        {canWrite && (
          <button
            className="button primary"
            onClick={() => setUploadOpen(!uploadOpen)}
          >
            <PlusIcon />
            New import
          </button>
        )}
      </SectionTitle>
      <div className="import-principle">
        <ShieldIcon />
        <p>
          <strong>Historical means historical.</strong> Backfilled transactions
          never reserve live stock, charge customers or trigger delivery
          notifications.
        </p>
      </div>
      <Notice message={error} />
      {canWrite && uploadOpen && (
        <form className="panel import-form" onSubmit={upload}>
          <div className="panel-heading">
            <div>
              <p className="eyebrow">START WITH A PREVIEW</p>
              <h2>Import a CSV file</h2>
            </div>
            <span className="badge">UTF-8 · Up to 10 MB</span>
          </div>
          <div className="import-kinds">
            {kinds.map((k) => (
              <label className={kind === k.key ? "selected" : ""} key={k.key}>
                <input
                  type="radio"
                  name="kind"
                  checked={kind === k.key}
                  onChange={() => setKind(k.key)}
                />
                <FileSpreadsheet size={21} />
                <strong>{k.name}</strong>
                <small>{k.text}</small>
              </label>
            ))}
          </div>
          <div className="form-grid">
            <Field
              label="Stable source identity"
              hint="Use the same source name when importing an updated extract."
            >
              <input
                required
                value={source}
                onChange={(e) => setSource(e.target.value)}
                placeholder="legacy-store-2026"
              />
            </Field>
            <Field
              label="CSV file"
              hint="Maximum 25,000 data rows. Use the template for exact columns."
            >
              <input
                required
                type="file"
                multiple={kind === "history"}
                accept=".csv,text/csv"
                onChange={(e) => setFiles(Array.from(e.target.files || []))}
              />
            </Field>
          </div>
          <div className="import-actions">
            <a
              className="text-link"
              href={`/api/v1/imports/templates/?kind=${kind}`}
            >
              <Download size={16} />
              Download {pretty(kind)} template
            </a>
            <button className="button primary" disabled={busy || !files.length}>
              {busy ? "Uploading…" : "Upload & validate"}
              <ArrowRight size={17} />
            </button>
          </div>
        </form>
      )}
      <section className="panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">PROVENANCE & PROGRESS</p>
            <h2>Import history</h2>
          </div>
          <button className="button small secondary" onClick={reload}>
            <RefreshCw size={15} />
            Refresh
          </button>
        </div>
        {rows.length ? (
          <DataTable
            data={rows}
            columns={[
              {
                accessorKey: "filename",
                header: "File",
                cell: ({ row }) => (
                  <button
                    className="link-button"
                    onClick={async () =>
                      setSelected(await api<Row>(`imports/${row.original.id}/`))
                    }
                  >
                    {row.original.filename}
                    <ArrowUpRight size={14} />
                  </button>
                ),
              },
              {
                accessorKey: "kind",
                header: "Purpose",
                cell: ({ getValue }) => pretty(getValue()),
              },
              { accessorKey: "source_name", header: "Source" },
              {
                accessorKey: "status",
                header: "Status",
                cell: ({ getValue }) => <Badge value={getValue()} />,
              },
              { accessorKey: "total_rows", header: "Rows" },
              {
                accessorKey: "created_at",
                header: "Uploaded",
                cell: ({ getValue }) => <DateText value={getValue()} />,
              },
            ]}
          />
        ) : (
          <Empty
            title="A clean start"
            text="Upload a source file to preview its records before committing."
          />
        )}
      </section>
      {selected && (
        <div className="modal-overlay" onClick={() => setSelected(null)}>
          <section
            className="modal wide"
            role="dialog"
            aria-modal="true"
            ref={importDialog}
            aria-label="Import validation report"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="panel-heading">
              <div>
                <p className="eyebrow">VALIDATION & RECONCILIATION</p>
                <h2>{selected.filename}</h2>
                <p className="muted">
                  {selected.source_name} · {pretty(selected.kind)}
                </p>
              </div>
              <button
                className="icon-button"
                onClick={() => setSelected(null)}
                aria-label="Close import report"
              >
                <X />
              </button>
            </div>
            <div className="import-progress">
              <Badge value={selected.status} />
              <progress value={selected.progress || 0} max="100" />
              <strong>{selected.progress || 0}%</strong>
            </div>
            <div className="import-counts">
              <span>
                <strong>{selected.total_rows || 0}</strong>Total rows
              </span>
              <span>
                <strong>{selected.valid_rows || 0}</strong>Valid rows
              </span>
              <span>
                <strong>{selected.error_rows || 0}</strong>Errors
              </span>
            </div>
            {selected.status === "completed" && (
              <Notice
                success
                message={`Import committed. ${JSON.stringify(selected.result || {})}`}
              />
            )}
            <Notice message={error} />
            {selected.errors?.length > 0 && (
              <div className="validation-errors">
                <h3>Resolve these source errors</h3>
                {selected.errors.slice(0, 30).map((e: Row, i: number) => (
                  <p key={i}>
                    <AlertCircle size={15} />
                    <strong>Row {e.row}:</strong> {e.message}
                  </p>
                ))}
              </div>
            )}
            {selected.preview?.length > 0 && (
              <>
                <h3>Record preview</h3>
                <DataTable
                  data={selected.preview.slice(0, 10)}
                  columns={Object.keys(selected.preview[0])
                    .slice(0, 8)
                    .map((key) => ({
                      accessorKey: key,
                      header: pretty(key),
                      cell: ({ getValue }) =>
                        typeof getValue() === "object"
                          ? JSON.stringify(getValue())
                          : String(getValue() ?? "—"),
                    }))}
                />
              </>
            )}
            {selected.status === "ready" && canWrite && (
              <div className="import-actions">
                <p className="muted">
                  Review the preview and source totals before committing.
                </p>
                <button
                  className="button primary"
                  disabled={busy || selected.error_rows > 0}
                  onClick={async () => {
                    setBusy(true);
                    setError("");
                    try {
                      setSelected(
                        await api<Row>(`imports/${selected.id}/commit/`, {
                          method: "POST",
                          body: "{}",
                        }),
                      );
                      await reload();
                    } catch (e) {
                      setError((e as Error).message);
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  Commit validated import
                  <CheckCircle2 size={17} />
                </button>
              </div>
            )}
          </section>
        </div>
      )}
    </>
  );
}
function PlusIcon() {
  return <Upload size={17} />;
}
function ShieldIcon() {
  return (
    <span className="insight-icon">
      <CheckCircle2 size={21} />
    </span>
  );
}
