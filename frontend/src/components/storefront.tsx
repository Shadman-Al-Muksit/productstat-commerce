"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  ArrowUpRight,
  Search,
  SlidersHorizontal,
  ShoppingBag,
  Plus,
  Minus,
  Trash2,
  Truck,
  ShieldCheck,
  RotateCcw,
  Check,
  LockKeyhole,
  Package,
  ChevronRight,
} from "lucide-react";
import { api, list, money, pretty, Product, SKU, Order } from "@/lib/api";
import { useApp } from "./commerce-app";
import { translate } from "@/lib/i18n";
function useStoreText() {
  const { language } = useApp();
  return (value: string) => translate(language, value);
}
import {
  Loading,
  Notice,
  Empty,
  Badge,
  Field,
  SectionTitle,
  DateText,
  Pagination,
} from "./ui";
type Row = Record<string, any>;
const catName = (p: Product) => p.category;
function pName(p: Product, bn: boolean) {
  return p.name;
}
export function Storefront() {
  const { language } = useApp();
  const t = useStoreText();
  const bn = language === "bn";
  const [products, setProducts] = useState<Product[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [sort, setSort] = useState("name");
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [count, setCount] = useState(0);
  useEffect(() => {
    let alive = true;
    setBusy(true);
    const timer = setTimeout(() => {
      const params = new URLSearchParams({
        q: search,
        category,
        sort,
        page: String(page),
        page_size: "24",
      });
      api<Row>(`catalog/products/?${params}`)
        .then((d) => {
          if (!alive) return;
          const rows = list<Product>(d);
          setProducts(rows);
          setCount(Number(d.count ?? rows.length));
          setCategories(d.categories || []);
          setError("");
        })
        .catch((e) => alive && setError(e.message))
        .finally(() => alive && setBusy(false));
    }, 200);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [search, category, sort, page]);
  useEffect(() => setPage(1), [search, category, sort]);
  return (
    <>
      <section className="store-hero">
        <div className="hero-copy">
          <p className="eyebrow">
            <span className="tiny-line" />
            {bn ? "দৈনন্দিন জীবনের জন্য বাছাই করা" : "THE EVERYDAY, CONSIDERED"}
          </p>
          <h1>
            {bn ? (
              <>
                প্রতিদিনের পণ্য।
                <br />
                <em>অসাধারণ অনুভূতি।</em>
              </>
            ) : (
              <>
                Everyday essentials.
                <br />
                <em>Extraordinary details.</em>
              </>
            )}
          </h1>
          <p>
            {bn
              ? "আপনার জীবনকে একটু সহজ, সুন্দর ও অর্থবহ করতে চিন্তাভাবনা করে বেছে নেওয়া পণ্য।"
              : "Objects you’ll reach for again and again. Discover thoughtful design, honest quality, and a little more joy in the everyday."}
          </p>
          <a href="#collection" className="button primary">
            {bn ? "পণ্য দেখুন" : "Explore the collection"}
            <ArrowRight size={18} />
          </a>
          <div className="hero-trust">
            <span>
              <ShieldCheck size={16} />
              {bn ? "নিরাপদ কেনাকাটা" : "Considered quality"}
            </span>
            <span>
              <Truck size={17} />
              {bn ? "সারাদেশে ডেলিভারি" : "Delivery across Bangladesh"}
            </span>
          </div>
        </div>
        <div className="hero-art">
          <div className="hero-circle" />
          <span className="hero-index">01 / EVERYDAY OBJECTS</span>
          <img
            src="/products/headphones.svg"
            alt="Sculptural over-ear headphones in a warm neutral finish"
          />
          <div className="hero-caption">
            <span>
              Good design.
              <br />
              <strong>Better everyday.</strong>
            </span>
            <a
              href="#collection"
              className="round-arrow"
              aria-label={t("Explore collection")}
            >
              <ArrowUpRight size={24} />
            </a>
          </div>
          <div className="hero-floating">
            <span className="live-dot" />
            CURATED WITH INTENTION
          </div>
        </div>
      </section>
      <section className="benefits">
        <span>
          <Truck size={20} />
          {bn ? "দেশজুড়ে ডেলিভারি" : "Nationwide delivery"}
        </span>
        <span>
          <ShoppingBag size={20} />
          {bn ? "ক্যাশ অন ডেলিভারি" : "Cash on delivery"}
        </span>
        <span>
          <RotateCcw size={19} />
          {bn ? "সহজ রিটার্ন প্রক্রিয়া" : "Considered return support"}
        </span>
        <span>
          <ShieldCheck size={19} />
          {bn ? "স্বচ্ছ অর্ডার ট্র্যাকিং" : "Transparent order tracking"}
        </span>
      </section>
      <section className="collection" id="collection">
        <div className="collection-heading">
          <div>
            <p className="eyebrow">
              {bn ? "আপনার প্রতিদিনের জন্য" : "FIND YOUR EVERYDAY"}
            </p>
            <h2>{bn ? "চিন্তাভাবনা করে বাছাই।" : "Thoughtfully selected."}</h2>
          </div>
          <p>
            {bn
              ? "উপকারী। সুন্দর। দীর্ঘস্থায়ী।"
              : "Useful. Beautiful. Made for the way you live."}
          </p>
        </div>
        <div className="catalog-controls">
          <div className="category-tabs">
            <button
              className={!category ? "selected" : ""}
              onClick={() => setCategory("")}
            >
              {bn ? "সব পণ্য" : "All goods"}
            </button>
            {categories.slice(0, 7).map((c) => (
              <button
                key={c}
                className={category === c ? "selected" : ""}
                onClick={() => setCategory(c)}
              >
                {c}
              </button>
            ))}
          </div>
          <div className="catalog-tools">
            <label className="search-box">
              <Search size={17} />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                aria-label={t("Search products")}
                placeholder={bn ? "পণ্য খুঁজুন" : "Find something good…"}
              />
            </label>
            <label className="sort-label">
              <SlidersHorizontal size={16} />
              <select
                aria-label={t("Sort products")}
                value={sort}
                onChange={(e) => setSort(e.target.value)}
              >
                <option value="newest">Newest additions</option>
                <option value="price_asc">Price: low to high</option>
                <option value="price_desc">Price: high to low</option>
                <option value="name">Name: A–Z</option>
              </select>
            </label>
          </div>
        </div>
        <div className="result-caption">
          {busy
            ? "Finding thoughtful goods…"
            : `${count} considered ${count === 1 ? "find" : "finds"}`}
        </div>
        <Notice message={error} />
        {busy ? (
          <Loading label={bn ? "পণ্য লোড হচ্ছে…" : "Gathering the collection…"} />
        ) : products.length ? (
          <div className="product-grid">
            {products.map((p, i) => (
              <ProductCard product={p} key={p.id} index={i} />
            ))}
          </div>
        ) : (
          !error && (
            <Empty
              title={bn ? "কোনো পণ্য পাওয়া যায়নি" : "No goods found"}
              text={t("Try a different search or collection.")}
            />
          )
        )}
        <Pagination
          page={page}
          count={count}
          pageSize={24}
          onPage={(p) => {
            setPage(p);
            document
              .getElementById("collection")
              ?.scrollIntoView({ behavior: "smooth" });
          }}
        />
        <div className="collection-end">
          <span>GOOD THINGS, CHOSEN WELL.</span>
          <span>
            Designed for everyday living
            <ArrowUpRight size={16} />
          </span>
        </div>
      </section>
      <section className="story-banner">
        <div>
          <p className="eyebrow">MORE THAN A STOREFRONT</p>
          <h2>
            Good products.
            <br />
            <em>Better understanding.</em>
          </h2>
          <p>
            Behind every order is a story. Our company workspace connects
            products, deliveries and returns into a clear picture of
            performance.
          </p>
          <Link className="text-link" href="/analytics">
            Explore product intelligence
            <ArrowUpRight size={18} />
          </Link>
        </div>
        <div className="story-graphic">
          <span className="story-label">THE COMPLETE PICTURE</span>
          {[
            ["01", "Products & variants"],
            ["02", "Orders & delivery"],
            ["03", "Returns & insights"],
          ].map(([a, b]) => (
            <div key={a}>
              <span>{a}</span>
              <strong>{b}</strong>
              <ArrowUpRight size={20} />
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
function ProductCard({
  product: p,
  index,
}: {
  product: Product;
  index: number;
}) {
  const { language } = useApp();
  const t = useStoreText();
  const available = p.total_available;
  return (
    <Link
      href={`/products/${p.slug}`}
      className="product-card"
      data-testid="product-card"
    >
      <div className={`product-image tone-${index % 6}`}>
        <img
          src={p.image_url || "/products/tote.svg"}
          alt={pName(p, language === "bn")}
        />
        <span className="product-category">{catName(p)}</span>
        <span className="product-open">
          <ArrowUpRight size={20} />
        </span>
        {available <= 0 && (
          <span className="stock-label">{t("Currently unavailable")}</span>
        )}
      </div>
      <div className="product-info">
        <div>
          <h3>{pName(p, language === "bn")}</h3>
          <p>
            {p.skus?.length || 1} considered{" "}
            {p.skus?.length === 1 ? "option" : "options"}
          </p>
        </div>
        <strong>{money(p.min_price || p.skus?.[0]?.price)}</strong>
      </div>
    </Link>
  );
}
export function ProductDetail({ slug }: { slug: string }) {
  const { language, refreshCart } = useApp();
  const t = useStoreText();
  const [p, setP] = useState<Product | null>(null);
  const [sku, setSku] = useState<SKU | null>(null);
  const [quantity, setQuantity] = useState(1);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api<Product>(`catalog/products/${slug}/`)
      .then((d) => {
        setP(d);
        setSku(d.skus.find((s) => s.available > 0) || d.skus[0]);
      })
      .catch((e) => setError(e.message));
  }, [slug]);
  if (!p)
    return (
      <div className="page-shell">
        <Notice message={error} />
        {!error && <Loading />}
      </div>
    );
  return (
    <div className="page-shell">
      <div className="crumbs">
        <Link href="/">Collection</Link>
        <ChevronRight size={14} />
        <span>{catName(p)}</span>
        <ChevronRight size={14} />
        <span>{pName(p, language === "bn")}</span>
      </div>
      <div className="product-detail">
        <div className="detail-art">
          <img src={p.image_url || "/products/tote.svg"} alt={p.name} />
          <span className="art-note">DESIGNED FOR YOUR EVERYDAY</span>
        </div>
        <div className="detail-copy">
          <p className="eyebrow">{catName(p)}</p>
          <h1>{pName(p, language === "bn")}</h1>
          <p className="detail-price">{money(sku?.price || p.min_price)}</p>
          <p className="description">{p.description}</p>
          <div className="variant-picker">
            <span className="field-title">{t("Choose your variant")}</span>
            <div>
              {p.skus.map((s) => (
                <button
                  key={s.id}
                  onClick={() => {
                    setSku(s);
                    setSuccess("");
                  }}
                  className={sku?.id === s.id ? "selected" : ""}
                >
                  {s.label ||
                    Object.values(s.attributes || {}).join(" / ") ||
                    s.code}
                  {sku?.id === s.id && <Check size={14} />}
                </button>
              ))}
            </div>
          </div>
          <p className={`availability ${!sku?.available ? "unavailable" : ""}`}>
            <span className="live-dot" />
            {sku?.available
              ? `${sku.available} available · Ready for a new everyday`
              : "Currently out of stock"}
          </p>
          <div className="purchase-row">
            <Quantity
              value={quantity}
              max={sku?.available || 1}
              onChange={setQuantity}
            />
            <button
              className="button primary"
              data-testid="add-to-cart"
              disabled={!sku?.available || busy}
              onClick={async () => {
                if (!sku) return;
                setBusy(true);
                setError("");
                setSuccess("");
                try {
                  await api("cart/", {
                    method: "POST",
                    body: JSON.stringify({ sku_id: sku.id, quantity }),
                  });
                  await refreshCart();
                  setSuccess("Added to your bag. Ready when you are.");
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              {busy
                ? "Adding…"
                : language === "bn"
                  ? "ব্যাগে যোগ করুন"
                  : "Add to bag"}
              <ShoppingBag size={18} />
            </button>
          </div>
          <Notice message={error} />
          <Notice message={success} success />
          {success && (
            <Link href="/cart" className="text-link">
              {t("View your bag")}
              <ArrowRight size={17} />
            </Link>
          )}
          <div className="detail-benefits">
            <p>
              <Truck size={19} />
              Domestic delivery · charges shown at checkout
            </p>
            <p>
              <ShieldCheck size={19} />
              Cash on delivery available
            </p>
            <p>
              <RotateCcw size={19} />
              Return requests within 7 days of delivery
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
function Quantity({
  value,
  onChange,
  max = 99,
}: {
  value: number;
  onChange: (n: number) => void;
  max?: number;
}) {
  const t = useStoreText();
  return (
    <div className="quantity">
      <button
        type="button"
        aria-label={t("Decrease quantity")}
        onClick={() => onChange(Math.max(1, value - 1))}
        disabled={value <= 1}
      >
        <Minus size={14} />
      </button>
      <span>{value}</span>
      <button
        type="button"
        aria-label={t("Increase quantity")}
        onClick={() => onChange(Math.min(max, value + 1))}
        disabled={value >= max}
      >
        <Plus size={14} />
      </button>
    </div>
  );
}
export function CartPage() {
  const { cart, refreshCart, bootstrap } = useApp();
  const t = useStoreText();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function update(sku: unknown, quantity: number) {
    setBusy(true);
    try {
      await api("cart/", {
        method: "POST",
        body: JSON.stringify({ sku_id: sku, quantity }),
      });
      await refreshCart();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="page-shell">
      <SectionTitle
        eyebrow="GOOD CHOICES START HERE"
        title={t("Your shopping bag")}
        text={`${cart.items.reduce((s, i) => s + i.quantity, 0)} items, thoughtfully chosen.`}
      />
      <Notice message={error} />
      {!cart.items.length ? (
        <Empty
          title={t("Your next everyday favourite is waiting.")}
          text={t(
            "Explore our considered collection and find something that feels right.",
          )}
          href="/"
        />
      ) : (
        <div className="checkout-grid">
          <div className="cart-items">
            {cart.items.map((item, i) => {
              const sku = typeof item.sku === "object" ? item.sku : null;
              return (
                <div className="cart-item" key={item.sku_id || i}>
                  <img
                    src={item.product.image_url || "/products/tote.svg"}
                    alt=""
                  />
                  <div className="cart-item-copy">
                    <h3>{item.product.name}</h3>
                    <p>{sku?.label || sku?.code}</p>
                    <strong>{money(item.sku.price)}</strong>
                    <Quantity
                      value={item.quantity}
                      max={sku?.available || 99}
                      onChange={(n) => update(item.sku_id, n)}
                    />
                  </div>
                  <div className="cart-item-end">
                    <strong>{money(item.line_total)}</strong>
                    <button
                      className="icon-button"
                      disabled={busy}
                      aria-label={t("Remove item")}
                      onClick={() => update(item.sku_id, 0)}
                    >
                      <Trash2 size={18} />
                    </button>
                  </div>
                </div>
              );
            })}
            <Link href="/" className="text-link">
              {t("Continue exploring")}
              <ArrowRight size={17} />
            </Link>
          </div>
          <aside className="order-summary">
            <h2>{t("A little summary")}</h2>
            <div>
              <span>{t("Merchandise subtotal")}</span>
              <strong>{money(cart.subtotal)}</strong>
            </div>
            <div>
              <span>{t("Delivery")}</span>
              <span>{t("Calculated at checkout")}</span>
            </div>
            <div className="summary-total">
              <span>{t("Subtotal")}</span>
              <strong>{money(cart.subtotal)}</strong>
            </div>
            <Link href="/checkout" className="button primary full">
              {t("Continue to checkout")}
              <ArrowRight size={18} />
            </Link>
            <p>
              <LockKeyhole size={14} />
              {t("Secure checkout · BDT")}
            </p>
            {bootstrap.demo && (
              <small>Demonstration store. Use synthetic contact details.</small>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}
export function CheckoutPage() {
  const { bootstrap, cart, refreshCart } = useApp();
  const t = useStoreText();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [zone, setZone] = useState(
    String(bootstrap.delivery_zones?.[0]?.id || ""),
  );
  const [method, setMethod] = useState("cod");
  const [key] = useState(() =>
    typeof crypto !== "undefined" ? crypto.randomUUID() : String(Date.now()),
  );
  const selectedZone = bootstrap.delivery_zones?.find(
    (z) => String(z.id) === zone,
  );
  const taxEstimate = cart.items.reduce(
    (sum, item) =>
      sum +
      Math.round(
        Number(item.line_total) * Number(bootstrap.company.tax_rate || 0),
      ) /
        100,
    0,
  );
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const data = Object.fromEntries(new FormData(e.currentTarget));
    try {
      const result = await api<Row>("checkout/", {
        method: "POST",
        headers: { "Idempotency-Key": key },
        body: JSON.stringify({
          customer_name: data.customer_name,
          email: data.email,
          phone: data.phone,
          address: {
            line1: data.line1,
            area: data.area,
            city: data.city,
            postal_code: data.postal_code,
          },
          delivery_zone_id: Number(zone),
          payment_method: method,
        }),
      });
      const order = result.order as Order;
      const token = result.access_token;
      sessionStorage.setItem(`productstat-order-${order.id}`, token);
      await refreshCart();
      if (result.payment_url) {
        window.location.assign(result.payment_url);
        return;
      }
      router.push(
        `/orders/${order.id}${token ? `?token=${encodeURIComponent(token)}` : ""}`,
      );
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }
  return (
    <div className="page-shell">
      <SectionTitle
        eyebrow="ONE LAST DETAIL"
        title={t("Make it yours")}
        text={t("Tell us where your new everyday favourites should go.")}
      />
      <Notice message={error} />
      {!cart.items.length ? (
        <Empty title={t("Your bag is empty")} href="/" />
      ) : (
        <form onSubmit={submit} className="checkout-grid">
          <div className="panel checkout-form">
            <h2>{t("Delivery details")}</h2>
            {bootstrap.demo && (
              <div className="demo-note">
                This is a demonstration. Please use fictional contact and
                address details.
              </div>
            )}
            <div className="form-grid">
              <Field label={t("Full name")}>
                <input
                  name="customer_name"
                  required
                  autoComplete="name"
                  placeholder="Demo Customer"
                />
              </Field>
              <Field label={t("Phone number")}>
                <input
                  name="phone"
                  required
                  autoComplete="tel"
                  type="tel"
                  placeholder="01700000000"
                />
              </Field>
              <Field label={t("Email (optional)")}>
                <input
                  name="email"
                  type="email"
                  autoComplete="email"
                  placeholder="customer@example.test"
                />
              </Field>
              <Field label={t("Delivery zone")}>
                <select
                  value={zone}
                  onChange={(e) => setZone(e.target.value)}
                  required
                >
                  {bootstrap.delivery_zones?.map((z) => (
                    <option value={z.id} key={z.id}>
                      {z.name} — {money(z.charge)}
                    </option>
                  ))}
                </select>
              </Field>
              <div className="form-span">
                <Field label={t("Street address")}>
                  <input
                    name="line1"
                    required
                    autoComplete="street-address"
                    placeholder="House 10, Road 2"
                  />
                </Field>
              </div>
              <Field label={t("Area / neighbourhood")}>
                <input name="area" required placeholder="Your delivery area" />
              </Field>
              <Field label={t("City / district")}>
                <input name="city" required placeholder="Dhaka" />
              </Field>
              <Field label={t("Postal code")}>
                <input name="postal_code" placeholder="1200" />
              </Field>
            </div>
            <h2 className="form-section">{t("Payment preference")}</h2>
            <label
              className={`payment-option ${method === "cod" ? "selected" : ""}`}
            >
              <input
                type="radio"
                name="method"
                value="cod"
                checked={method === "cod"}
                onChange={() => setMethod("cod")}
              />
              <span>
                <strong>{t("Cash on delivery")}</strong>
                <small>{t("Pay when your order arrives.")}</small>
              </span>
              <ShoppingBag size={20} />
            </label>
            <label
              className={`payment-option ${method === "sslcommerz" ? "selected" : ""}`}
            >
              <input
                type="radio"
                name="method"
                value="sslcommerz"
                checked={method === "sslcommerz"}
                onChange={() => setMethod("sslcommerz")}
              />
              <span>
                <strong>
                  {t("Online payment")}{" "}
                  <span className="badge demo">SANDBOX</span>
                </strong>
                <small>
                  {bootstrap.payment?.sslcommerz_enabled
                    ? "Continue to SSLCOMMERZ’s secure test checkout."
                    : "SSLCOMMERZ sandbox is not configured for this store yet."}
                </small>
              </span>
              <ShieldCheck size={21} />
            </label>
          </div>
          <aside className="order-summary">
            <h2>{t("Your order")}</h2>
            {cart.items.map((i, index) => (
              <div className="summary-item" key={index}>
                <span>
                  {i.product.name}
                  <small>Quantity {i.quantity}</small>
                </span>
                <strong>{money(i.line_total)}</strong>
              </div>
            ))}
            <div>
              <span>{t("Merchandise")}</span>
              <strong>{money(cart.subtotal)}</strong>
            </div>
            <div>
              <span>{t("Delivery")}</span>
              <strong>{money(selectedZone?.charge)}</strong>
            </div>
            <div>
              <span>Tax ({bootstrap.company.tax_rate || "0"}%)</span>
              <strong>{money(taxEstimate)}</strong>
            </div>
            <div className="summary-total">
              <span>{t("Total")}</span>
              <strong>
                {money(
                  Number(cart.subtotal || 0) +
                    Number(selectedZone?.charge || 0) +
                    taxEstimate,
                )}
              </strong>
            </div>
            <button
              type="submit"
              data-testid="checkout-submit"
              className="button primary full"
              disabled={busy}
            >
              {busy
                ? t("Placing your order…")
                : bootstrap.demo
                  ? t("Place demo order")
                  : t("Place order")}
              <ArrowRight size={18} />
            </button>
            <p>
              <LockKeyhole size={14} />
              {bootstrap.demo
                ? t("No real payment or fulfilment")
                : t("Secure checkout · BDT")}
            </p>
            <small>
              Final charges and availability are validated before your order is
              placed.
            </small>
          </aside>
        </form>
      )}
    </div>
  );
}
export function AccountPage({ staffOnly = false }: { staffOnly?: boolean }) {
  const { bootstrap, refresh } = useApp();
  const t = useStoreText();
  const router = useRouter();
  const [mode, setMode] = useState("login");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [orders, setOrders] = useState<Order[]>([]);
  useEffect(() => {
    if (bootstrap.user)
      api("orders/")
        .then((d) => setOrders(list<Order>(d)))
        .catch((e) => setError(e.message));
  }, [bootstrap.user]);
  if (bootstrap.user && !staffOnly)
    return (
      <div className="page-shell">
        <SectionTitle
          eyebrow="YOUR EVERYDAY"
          title={`Hello, ${bootstrap.user.username}.`}
          text={t("Your orders, all in one place.")}
        >
          <button
            className="button secondary"
            onClick={async () => {
              await api("auth/logout/", { method: "POST", body: "{}" });
              await refresh();
            }}
          >
            {t("Sign out")}
          </button>
        </SectionTitle>
        {["admin", "administrator", "operator", "analyst"].includes(
          bootstrap.user.role || "",
        ) && (
          <p>
            <Link
              className="button primary"
              href={bootstrap.user.role === "analyst" ? "/analytics" : "/staff"}
            >
              Open company workspace
              <ArrowUpRight size={17} />
            </Link>
          </p>
        )}
        <Notice message={error} />
        {orders.length ? (
          <div className="panel table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t("Order")}</th>
                  <th>{t("Placed")}</th>
                  <th>{t("Status")}</th>
                  <th>{t("Total")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => (
                  <tr key={o.id}>
                    <td>{o.number}</td>
                    <td>
                      <DateText value={o.created_at} />
                    </td>
                    <td>
                      <Badge value={o.status} />
                    </td>
                    <td>{money(o.grand_total)}</td>
                    <td>
                      <Link className="text-link" href={`/orders/${o.id}`}>
                        {t("View")}
                        <ArrowUpRight size={15} />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title={t("Your first good choice awaits.")}
            text={t("Orders linked to your account will appear here.")}
            href="/"
          />
        )}
      </div>
    );
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const data = Object.fromEntries(new FormData(e.currentTarget));
    try {
      const result = await api<Row>(`auth/${mode}/`, {
        method: "POST",
        body: JSON.stringify(data),
      });
      await refresh();
      if (!staffOnly) {
        router.push("/account");
      } else if (result.user?.role === "analyst") {
        router.push("/analytics");
      } else if (
        ["administrator", "operator"].includes(result.user?.role || "")
      ) {
        const entered = window.location.pathname;
        const permitted =
          entered.startsWith("/analytics") ||
          entered.startsWith("/imports") ||
          entered.startsWith("/staff");
        const adminPage =
          entered.startsWith("/staff/users") ||
          entered.startsWith("/staff/settings");
        router.push(
          permitted && (!adminPage || result.user.role === "administrator")
            ? entered
            : "/staff",
        );
      } else {
        router.push("/account");
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="auth-shell">
      <div className="auth-art">
        <p className="eyebrow">THE EVERYDAY, CONNECTED</p>
        <h1>
          Good to
          <br />
          <em>have you here.</em>
        </h1>
        <img src="/products/tote.svg" alt="Everyday tote bag" />
        <p>
          Your purchases. Your preferences.
          <br />A more thoughtful everyday.
        </p>
      </div>
      <div className="auth-form">
        <p className="eyebrow">
          {staffOnly ? "COMPANY WORKSPACE" : "YOUR ACCOUNT"}
        </p>
        <h2>
          {mode === "register"
            ? t("Make yourself at home.")
            : t("Welcome back.")}
        </h2>
        <p className="muted">
          {staffOnly
            ? "Sign in with your company account to continue."
            : "A little less effort. A little more everyday."}
        </p>
        <Notice message={error} />
        <form onSubmit={submit}>
          <Field label={t("Username")}>
            <input name="username" required autoComplete="username" />
          </Field>
          {mode === "register" && (
            <Field label={t("Email")}>
              <input name="email" required type="email" autoComplete="email" />
            </Field>
          )}
          <Field label={t("Password")}>
            <input
              name="password"
              required
              type="password"
              autoComplete={
                mode === "register" ? "new-password" : "current-password"
              }
              minLength={mode === "register" ? 10 : 1}
            />
          </Field>
          <button className="button primary full" disabled={busy}>
            {busy
              ? t("One moment…")
              : mode === "register"
                ? t("Create account")
                : t("Sign in")}
            <ArrowRight size={17} />
          </button>
        </form>
        {!staffOnly && (
          <p className="auth-toggle">
            {mode === "register"
              ? t("Already feel at home?")
              : t("New around here?")}{" "}
            <button
              onClick={() => {
                setMode(mode === "login" ? "register" : "login");
                setError("");
              }}
            >
              {mode === "register" ? t("Sign in") : t("Create an account")}
            </button>
          </p>
        )}
        <Link href="/" className="text-link">
          {t("Back to the collection")}
          <ArrowUpRight size={16} />
        </Link>
      </div>
    </div>
  );
}
export function TrackingPage() {
  const t = useStoreText();
  const router = useRouter();
  return (
    <div className="narrow-shell">
      <SectionTitle
        eyebrow="FOLLOW YOUR GOOD CHOICES"
        title={t("Track your order")}
        text={t(
          "Use the order ID and secure access token from your confirmation link.",
        )}
      />
      <form
        className="panel"
        onSubmit={(e) => {
          e.preventDefault();
          const d = new FormData(e.currentTarget);
          router.push(
            `/orders/${encodeURIComponent(String(d.get("id")))}?token=${encodeURIComponent(String(d.get("token")))}`,
          );
        }}
      >
        <Field label={t("Order ID")}>
          <input name="id" required placeholder="Your order ID" />
        </Field>
        <Field label={t("Secure access token")}>
          <input
            name="token"
            required
            placeholder="From your order confirmation"
          />
        </Field>
        <button className="button primary full">
          {t("Find my order")}
          <ArrowRight size={17} />
        </button>
      </form>
    </div>
  );
}
export function OrderPage({ id }: { id: string }) {
  const t = useStoreText();
  const [o, setO] = useState<Row | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const t =
      new URLSearchParams(window.location.search).get("token") ||
      sessionStorage.getItem(`productstat-order-${id}`) ||
      "";
    setToken(t);
    api<Row>(`orders/${id}/?token=${encodeURIComponent(t)}`)
      .then(setO)
      .catch((e) => setError(e.message));
  }, [id]);
  const reload = async () =>
    setO(await api<Row>(`orders/${id}/?token=${encodeURIComponent(token)}`));
  async function cancel() {
    if (!confirm("Cancel the remaining undispatched items in this order?"))
      return;
    setBusy(true);
    try {
      await api(`orders/${id}/cancel/?token=${encodeURIComponent(token)}`, {
        method: "POST",
        body: "{}",
      });
      await reload();
      setSuccess("Order cancellation recorded.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (!o)
    return (
      <div className="page-shell">
        <Notice message={error} />
        {!error && <Loading />}
      </div>
    );
  const lines = (o.lines || []) as Row[];
  return (
    <div className="page-shell">
      <div className="order-confirm">
        <span className="confirmation-check">
          <Check size={27} />
        </span>
        <p className="eyebrow">YOUR ORDER, ALL IN ONE PLACE</p>
        <h1>{t("Good choices are on their way.")}</h1>
        <p>
          {t("Order")} <strong>{o.order_number || o.number || o.id}</strong> ·{" "}
          <DateText value={o.created_at} />
        </p>
        <div className="inline-badges">
          <Badge value={o.status} />
          <Badge value={o.payment_method} />
          {o.shipments?.length > 0 && <Badge value={o.shipments[0].state} />}
        </div>
      </div>
      <Notice message={error} />
      <Notice message={success} success />
      <div className="checkout-grid">
        <div className="panel">
          <h2>{t("Your thoughtful finds")}</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t("Product")}</th>
                  <th>{t("Quantity")}</th>
                  <th>{t("Cancelled")}</th>
                  <th>{t("Unit price")}</th>
                  <th>{t("Amount")}</th>
                </tr>
              </thead>
              <tbody>
                {lines.map((l) => (
                  <tr key={l.id}>
                    <td>
                      <strong>{l.product_name || l.name || l.sku_code}</strong>
                      <small className="cell-sub">{l.sku_code || l.sku}</small>
                    </td>
                    <td>{l.quantity}</td>
                    <td>{l.cancelled_quantity || 0}</td>
                    <td>{money(l.unit_price)}</td>
                    <td>{money(l.line_total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!o.shipments?.length &&
            !["cancelled", "expired"].includes(o.status) && (
              <button
                className="button secondary"
                disabled={busy}
                onClick={cancel}
              >
                {t("Cancel before dispatch")}
              </button>
            )}
          {o.shipments?.length > 0 && (
            <div className="order-shipment">
              <Truck size={21} />
              <div>
                <strong>{pretty(o.shipments[0].state)}</strong>
                <p>
                  {o.shipments[0].carrier || "Delivery partner"} ·{" "}
                  {o.shipments[0].tracking_number || "Tracking update pending"}
                </p>
              </div>
            </div>
          )}
          {o.shipments?.[0]?.state === "delivered" && (
            <ReturnForm
              order={o}
              token={token}
              onSuccess={async () => {
                await reload();
                setSuccess(
                  "Return request received. Your items will be reviewed by the store.",
                );
              }}
            />
          )}
          {(o.returns || []).length > 0 && (
            <div className="returns-summary">
              <h3>{t("Return requests")}</h3>
              {o.returns.map((r: Row) => (
                <div className="list-row" key={r.id}>
                  <span>{r.reason || "Return request"}</span>
                  <Badge value={r.status} />
                </div>
              ))}
            </div>
          )}
        </div>
        <aside className="order-summary">
          <h2>{t("Order summary")}</h2>
          <div>
            <span>{t("Merchandise")}</span>
            <strong>{money(o.subtotal)}</strong>
          </div>
          <div>
            <span>{t("Delivery")}</span>
            <strong>{money(o.shipping_total)}</strong>
          </div>
          <div>
            <span>{t("Tax")}</span>
            <strong>{money(o.tax_total)}</strong>
          </div>
          <div className="summary-total">
            <span>{t("Total")}</span>
            <strong>{money(o.grand_total)}</strong>
          </div>
          <div>
            <span>{t("Payment")}</span>
            <Badge value={o.payment_method} />
          </div>
          <div>
            <span>{t("Amount due")}</span>
            <strong>{money(o.amount_due)}</strong>
          </div>
          {token && (
            <div className="tracking-save">
              <LockKeyhole size={17} />
              <p>
                Keep this confirmation link safe. It is your private access to
                this order.
              </p>
            </div>
          )}
          <Link className="button secondary full" href="/">
            {t("Keep exploring")}
            <ArrowRight size={16} />
          </Link>
        </aside>
      </div>
    </div>
  );
}
function ReturnForm({
  order,
  token,
  onSuccess,
}: {
  order: Row;
  token: string;
  onSuccess: () => Promise<void>;
}) {
  const t = useStoreText();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <div className="return-form">
      <button className="text-link" onClick={() => setOpen(!open)}>
        <RotateCcw size={17} />
        {t("Request an item return")}
      </button>
      {open && (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            const f = new FormData(e.currentTarget);
            const lines = order.lines
              .filter((l: Row) => Number(f.get(l.id)) > 0)
              .map((l: Row) => ({
                order_line_id: l.id,
                quantity: Number(f.get(l.id)),
              }));
            try {
              await api(
                `orders/${order.id}/returns/?token=${encodeURIComponent(token)}`,
                {
                  method: "POST",
                  body: JSON.stringify({ reason: f.get("reason"), lines }),
                },
              );
              await onSuccess();
              setOpen(false);
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <p className="muted">
            Choose the quantities you want reviewed. Items must be within the
            store’s return window.
          </p>
          {order.lines.map((l: Row) => (
            <Field key={l.id} label={l.product_name || l.sku_code}>
              <input
                name={l.id}
                type="number"
                min="0"
                max={Math.max(0, l.delivered_quantity - l.returned_quantity)}
                defaultValue="0"
              />
            </Field>
          ))}
          <Field label={t("Return reason")}>
            <select name="reason" required>
              <option value="wrong_item">{t("Wrong item received")}</option>
              <option value="damaged">{t("Damaged item")}</option>
              <option value="quality">{t("Quality concern")}</option>
              <option value="changed_mind">{t("Changed my mind")}</option>
            </select>
          </Field>
          <Notice message={error} />
          <button className="button primary" disabled={busy}>
            {t("Submit return request")}
            <ArrowRight size={16} />
          </button>
        </form>
      )}
    </div>
  );
}
