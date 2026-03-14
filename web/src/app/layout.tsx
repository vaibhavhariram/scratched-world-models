import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Logistics World Graph",
  description: "Building entrance locations and delivery difficulty scores for Manhattan",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
