import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: {
    default: "ProductStat — Electronics & gadgets in Bangladesh",
    template: "%s · ProductStat",
  },
  description:
    "Shop laptops, mobile devices, audio, tools and gadgets in Bangladesh. Compare finishes, track orders and explore transparent product performance with ProductStat.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
