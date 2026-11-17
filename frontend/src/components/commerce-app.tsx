"use client";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
} from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import {
  ShoppingBag,
  Search,
  ArrowUpRight,
  LayoutDashboard,
  Package,
  Truck,
  BarChart3,
  Upload,
  Users,
  Settings,
  LogOut,
  Menu,
  X,
  Store,
  RotateCcw,
} from "lucide-react";
import { api, setCsrf, Bootstrap, Cart } from "@/lib/api";
import { Loading, Notice } from "./ui";
import {
  Storefront,
  ProductDetail,
  CartPage,
  CheckoutPage,
  AccountPage,
  OrderPage,
  TrackingPage,
} from "./storefront";
import { StaffPage } from "./staff";
import { AnalyticsPage, ImportsPage } from "./analytics";
type Context = {
  bootstrap: Bootstrap;
  refresh: () => Promise<void>;
  cart: Cart;
  refreshCart: () => Promise<void>;
  language: "en" | "bn";
  setLanguage: (value: "en" | "bn") => void;
};
const AppContext = createContext<Context | null>(null);
export function useApp() {
  const value = useContext(AppContext);
  if (!value) throw new Error("Application context unavailable");
  return value;
}
const navigation = [
  { href: "/staff", label: "Overview", icon: LayoutDashboard },
  { href: "/staff/orders", label: "Orders", icon: ShoppingBag },
  { href: "/staff/products", label: "Products & stock", icon: Package },
  { href: "/staff/returns", label: "Returns & refunds", icon: RotateCcw },
  { href: "/analytics", label: "Product intelligence", icon: BarChart3 },
  { href: "/imports", label: "Data imports", icon: Upload },
  { href: "/staff/users", label: "Team & access", icon: Users },
  { href: "/staff/settings", label: "Company settings", icon: Settings },
];
export default function CommerceApp() {
  const pathname = usePathname();
  const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null);
  const [cart, setCart] = useState<Cart>({ items: [], subtotal: "0.00" });
  const [error, setError] = useState("");
  const [language, setLanguage] = useState<"en" | "bn">("en");
  const [menu, setMenu] = useState(false);
  const refresh = useCallback(async () => {
    const data = await api<Bootstrap>("bootstrap/");
    setCsrf(data.csrfToken);
    setBootstrap(data);
  }, []);
  const refreshCart = useCallback(
    async () => setCart(await api<Cart>("cart/")),
    [],
  );
  useEffect(() => {
    Promise.all([refresh(), refreshCart()]).catch((e) => setError(e.message));
    const l = localStorage.getItem("productstat-language");
    if (l === "bn") setLanguage("bn");
  }, [refresh, refreshCart]);
  useEffect(() => {
    localStorage.setItem("productstat-language", language);
    document.documentElement.lang = language;
  }, [language]);
  useEffect(() => setMenu(false), [pathname]);
  const workspace =
    pathname.startsWith("/staff") ||
    pathname.startsWith("/analytics") ||
    pathname.startsWith("/imports");
  if (!bootstrap)
    return (
      <div className="startup">
        <Link href="/" className="wordmark">
          <span className="brand-mark">p</span>productstat
          <span className="brand-dot">.</span>
        </Link>
        {error ? (
          <>
            <Notice message={`Could not connect to ProductStat. ${error}`} />
            <button
              className="button primary"
              onClick={() => {
                setError("");
                refresh().catch((e) => setError(e.message));
              }}
            >
              Try again
            </button>
          </>
        ) : (
          <Loading label="Opening ProductStat…" />
        )}
      </div>
    );
  const count = cart.items.reduce((a, item) => a + item.quantity, 0);
  const staff =
    !!bootstrap.user &&
    ["admin", "administrator", "operator", "analyst"].includes(
      bootstrap.user.role || "",
    );
  const allowedNavigation = navigation.filter((n) =>
    bootstrap.user?.role === "analyst"
      ? n.href === "/analytics"
      : !["/staff/users", "/staff/settings"].includes(n.href) ||
        ["admin", "administrator"].includes(bootstrap.user?.role || ""),
  );
  const routeAllowed =
    bootstrap.user?.role === "analyst"
      ? pathname.startsWith("/analytics")
      : !["/staff/users", "/staff/settings"].some((path) =>
          pathname.startsWith(path),
        ) || bootstrap.user?.role === "administrator";
  const body =
    pathname === "/cart" ? (
      <CartPage />
    ) : pathname === "/checkout" ? (
      <CheckoutPage />
    ) : pathname.startsWith("/products/") ? (
      <ProductDetail slug={decodeURIComponent(pathname.split("/")[2] || "")} />
    ) : pathname.startsWith("/orders/") ? (
      <OrderPage id={pathname.split("/")[2]} />
    ) : pathname === "/track" ? (
      <TrackingPage />
    ) : pathname === "/account" || pathname === "/login" ? (
      <AccountPage />
    ) : workspace ? (
      !staff ? (
        <AccountPage staffOnly />
      ) : !routeAllowed ? (
        <div className="panel">
          <h1>This workspace needs a different role.</h1>
          <p className="muted">
            Your account does not have access to these company operations.
          </p>
          <Link
            className="button primary"
            href={bootstrap.user?.role === "analyst" ? "/analytics" : "/staff"}
          >
            Return to your workspace
            <ArrowUpRight size={16} />
          </Link>
        </div>
      ) : pathname.startsWith("/analytics") ? (
        <AnalyticsPage />
      ) : pathname.startsWith("/imports") ? (
        <ImportsPage />
      ) : (
        <StaffPage section={pathname.split("/")[2] || "overview"} />
      )
    ) : (
      <Storefront />
    );
  return (
    <AppContext.Provider
      value={{ bootstrap, refresh, cart, refreshCart, language, setLanguage }}
    >
      {workspace ? (
        <div className="workspace">
          <aside className={`sidebar ${menu ? "open" : ""}`}>
            <Link href="/" className="wordmark">
              <span className="brand-mark">p</span>productstat
              <span className="brand-dot">.</span>
            </Link>
            <div className="workspace-label">COMMERCE WORKSPACE</div>
            <nav>
              {allowedNavigation.map((n) => (
                <Link
                  href={n.href}
                  key={n.href}
                  className={
                    pathname === n.href ||
                    (n.href !== "/staff" && pathname.startsWith(n.href))
                      ? "active"
                      : ""
                  }
                >
                  <n.icon size={19} />
                  <span>{n.label}</span>
                </Link>
              ))}
            </nav>
            <div className="sidebar-bottom">
              <div className="demo-mini">
                <span className="live-dot" />
                <span>
                  {bootstrap.demo
                    ? "Demonstration store"
                    : bootstrap.company.name}
                  <small>
                    {bootstrap.demo
                      ? "Synthetic records · BDT"
                      : "Company workspace · BDT"}
                  </small>
                </span>
              </div>
              <Link href="/" className="back-store">
                <Store size={18} />
                Visit storefront
                <ArrowUpRight size={16} />
              </Link>
              {bootstrap.user && (
                <button
                  className="profile"
                  onClick={async () => {
                    await api("auth/logout/", { method: "POST", body: "{}" });
                    await refresh();
                  }}
                >
                  <span className="avatar">
                    {bootstrap.user.username.slice(0, 2).toUpperCase()}
                  </span>
                  <span>
                    {bootstrap.user.username}
                    <small>{bootstrap.user.role}</small>
                  </span>
                  <LogOut size={16} />
                </button>
              )}
            </div>
          </aside>
          {menu && <div className="overlay" onClick={() => setMenu(false)} />}
          <div className="workspace-main">
            <header className="workspace-header">
              <div>
                <button
                  aria-label="Toggle navigation"
                  className="icon-button mobile-only"
                  onClick={() => setMenu(!menu)}
                >
                  {menu ? <X /> : <Menu />}
                </button>
                <span className="breadcrumb">
                  Workspace <span>/</span>{" "}
                  {pathname.startsWith("/analytics")
                    ? "Intelligence"
                    : pathname.startsWith("/imports")
                      ? "Data imports"
                      : pathname.split("/")[2] || "Overview"}
                </span>
              </div>
              <div className="header-right">
                <span className="badge demo">
                  {bootstrap.demo ? "DEMO ENVIRONMENT" : "COMPANY WORKSPACE"}
                </span>
                <span className="timezone">Asia / Dhaka</span>
              </div>
            </header>
            <main className="workspace-content">{body}</main>
          </div>
        </div>
      ) : (
        <>
          <div className="announcement">
            <span>
              {language === "en"
                ? "Thoughtfully chosen. Delivered across Bangladesh."
                : "বাছাই করা পণ্য। সারা বাংলাদেশে ডেলিভারি।"}
            </span>
            <span className="announcement-demo">
              {bootstrap.demo
                ? "Portfolio demonstration · Synthetic data"
                : "Bangladesh · BDT · Domestic delivery"}
            </span>
          </div>
          <header className="store-header">
            <div className="store-header-inner">
              <Link href="/" className="wordmark">
                <span className="brand-mark">p</span>productstat
                <span className="brand-dot">.</span>
              </Link>
              <nav className="store-nav">
                <Link href="/">
                  {language === "en" ? "Shop collection" : "পণ্যসমূহ"}
                </Link>
                <Link href="/track">
                  {language === "en" ? "Track an order" : "অর্ডার ট্র্যাক"}
                </Link>
                <Link href="/analytics" className="workspace-link">
                  Workspace
                  <ArrowUpRight size={14} />
                </Link>
              </nav>
              <div className="store-actions">
                <button
                  className="language-switch"
                  onClick={() => setLanguage(language === "en" ? "bn" : "en")}
                  aria-label="Switch language"
                >
                  {language === "en" ? "বাংলা" : "EN"}
                </button>
                <Link href="/account" className="account-link">
                  {bootstrap.user
                    ? bootstrap.user.username
                    : language === "en"
                      ? "Account"
                      : "অ্যাকাউন্ট"}
                </Link>
                <Link
                  href="/cart"
                  className="cart-link"
                  aria-label={`Shopping bag, ${count} items`}
                >
                  <ShoppingBag size={21} />
                  <span className="cart-count">{count}</span>
                </Link>
              </div>
            </div>
          </header>
          <main>{body}</main>
          <footer className="store-footer">
            <div>
              <Link href="/" className="wordmark">
                productstat<span className="brand-dot">.</span>
              </Link>
              <p>Thoughtful goods. Clearer decisions.</p>
              <small>
                A complete commerce & product intelligence demonstration.
              </small>
            </div>
            <div>
              <strong>Explore</strong>
              <Link href="/">The collection</Link>
              <Link href="/track">Order tracking</Link>
              <Link href="/account">Your account</Link>
            </div>
            <div>
              <strong>Behind the store</strong>
              <Link href="/analytics">Product intelligence</Link>
              <Link href="/staff">Company workspace</Link>
              <span>Bangladesh · BDT · Asia/Dhaka</span>
            </div>
            <div className="footer-note">
              <span className="live-dot" />
              Built for everyday commerce.
              <small>
                {bootstrap.demo
                  ? "Demonstration only. No real purchases or fulfilment."
                  : "Considered goods, delivered across Bangladesh."}
              </small>
            </div>
          </footer>
        </>
      )}
    </AppContext.Provider>
  );
}
