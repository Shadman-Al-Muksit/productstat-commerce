"use client";
import { useEffect, useRef, type RefObject } from "react";
import {
  LoaderCircle,
  CheckCircle2,
  AlertCircle,
  ArrowUpRight,
  Package,
  ArrowRight,
} from "lucide-react";
import Link from "next/link";
import { pretty } from "@/lib/api";
export function Loading({
  label = "Loading your workspace…",
}: {
  label?: string;
}) {
  return (
    <div className="loading">
      <LoaderCircle className="spin" size={22} />
      <span>{label}</span>
    </div>
  );
}
export function Notice({
  message,
  success = false,
}: {
  message: string;
  success?: boolean;
}) {
  if (!message) return null;
  return (
    <div
      role={success ? "status" : "alert"}
      className={`notice ${success ? "success" : "error"}`}
    >
      {success ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}
      <span>{message}</span>
    </div>
  );
}
export function Empty({
  title = "Nothing here yet",
  text = "Your records will appear here as your business grows.",
  href,
  label,
}: {
  title?: string;
  text?: string;
  href?: string;
  label?: string;
}) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <Package size={29} />
      </span>
      <h3>{title}</h3>
      <p>{text}</p>
      {href && (
        <Link href={href} className="button primary">
          {label || "Explore products"}
          <ArrowRight size={17} />
        </Link>
      )}
    </div>
  );
}
export function Badge({ value }: { value: unknown }) {
  return (
    <span
      className={`badge status-${String(value).toLowerCase().replaceAll(" ", "_")}`}
    >
      {pretty(value)}
    </span>
  );
}
export function SectionTitle({
  eyebrow,
  title,
  text,
  children,
}: {
  eyebrow?: string;
  title: string;
  text?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="section-title">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {text && <p className="muted">{text}</p>}
      </div>
      {children}
    </div>
  );
}
export function Stat({
  label,
  value,
  note,
  accent = false,
}: {
  label: string;
  value: React.ReactNode;
  note?: string;
  accent?: boolean;
}) {
  return (
    <div className={`stat ${accent ? "accent" : ""}`}>
      <div className="stat-top">
        <span>{label}</span>
        <ArrowUpRight size={17} />
      </div>
      <strong>{value}</strong>
      {note && <small>{note}</small>}
    </div>
  );
}
export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: React.ReactNode;
  hint?: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}
export function DateText({ value }: { value: unknown }) {
  if (!value) return <>—</>;
  const d = new Date(String(value));
  return (
    <>
      {isNaN(d.getTime())
        ? String(value)
        : d.toLocaleDateString("en-GB", {
            day: "numeric",
            month: "short",
            year: "numeric",
            timeZone: "Asia/Dhaka",
          })}
    </>
  );
}

export function Pagination({
  page,
  count,
  pageSize,
  onPage,
}: {
  page: number;
  count: number;
  pageSize: number;
  onPage: (page: number) => void;
}) {
  if (count <= pageSize) return null;
  const pages = Math.max(1, Math.ceil(count / pageSize));
  return (
    <div className="pagination">
      <span>
        {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, count)} of{" "}
        {count.toLocaleString("en-BD")} records
      </span>
      <div>
        <button
          className="button small secondary"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
        >
          Previous
        </button>
        <span className="page-number">
          {page} / {pages}
        </span>
        <button
          className="button small secondary"
          disabled={page >= pages}
          onClick={() => onPage(page + 1)}
        >
          Next
        </button>
      </div>
    </div>
  );
}

export function useDialogFocus(
  open: boolean,
  container: RefObject<HTMLElement | null>,
  onClose: () => void,
) {
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    if (!open || !container.current) return;
    const previous = document.activeElement as HTMLElement | null;
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const elements = () =>
      Array.from(
        container.current?.querySelectorAll<HTMLElement>(
          'button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex="0"]',
        ) || [],
      ).filter((e) => e.getClientRects().length > 0);
    const first = elements()[0];
    first?.focus();
    const listener = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close.current();
        return;
      }
      if (event.key !== "Tab") return;
      const items = elements();
      const first = items[0],
        last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", listener);
    return () => {
      document.removeEventListener("keydown", listener);
      document.body.style.overflow = oldOverflow;
      previous?.focus();
    };
  }, [open, container]);
}
