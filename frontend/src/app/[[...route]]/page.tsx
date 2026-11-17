import CommerceApp from "@/components/commerce-app";
import type { Metadata } from "next";
type RouteProps = { params: Promise<{ route?: string[] }> };
export async function generateMetadata({
  params,
}: RouteProps): Promise<Metadata> {
  const { route = [] } = await params;
  if (
    [
      "staff",
      "analytics",
      "imports",
      "account",
      "login",
      "cart",
      "checkout",
      "orders",
      "track",
    ].includes(route[0])
  )
    return {
      robots: { index: false, follow: false },
      title:
        route[0] === "analytics"
          ? "Product intelligence"
          : route[0] === "staff"
            ? "Company workspace"
            : "Your commerce workspace",
    };
  if (route[0] === "products" && route[1]) {
    try {
      const response = await fetch(
        `${process.env.API_INTERNAL_URL || "http://127.0.0.1:8001"}/api/v1/catalog/products/${encodeURIComponent(route[1])}/`,
        {
          headers: { "X-Forwarded-Proto": "https" },
          next: { revalidate: 60 },
        },
      );
      if (response.ok) {
        const product = await response.json();
        const description = String(product.description || "").slice(0, 160);
        return {
          title: product.name,
          description,
          openGraph: {
            title: `${product.name} · ProductStat`,
            description,
            type: "website",
          },
        };
      }
    } catch {
      /* The page shows an actionable connection error without blocking rendering. */
    }
    return {
      title: "Product unavailable",
      robots: { index: false, follow: false },
    };
  }
  return {};
}
export default function Page() {
  return <CommerceApp />;
}
