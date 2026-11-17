import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: {
    default: "ProductStat — Thoughtful goods. Clearer decisions.",
    template: "%s · ProductStat",
  },
  description:
    "A Bangladesh commerce platform with transparent product performance, domestic delivery and carefully chosen everyday goods.",
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
