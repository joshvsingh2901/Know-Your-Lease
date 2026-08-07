import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Know Your Lease",
  description: "Understand your lease with answers grounded in the document.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
