import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "your-app",
  description: "Scaffolded from soup nextjs-app-router template.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

/**
 * Root layout is a Server Component. Keep it server-only.
 * Wrap client-only providers in a nested "use client" island.
 */
export default function RootLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
