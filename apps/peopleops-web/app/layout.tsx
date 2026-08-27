import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PeopleOps AI | HR intelligence copilot",
  description: "Evidence-first HR analysis over structured data and policies.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
