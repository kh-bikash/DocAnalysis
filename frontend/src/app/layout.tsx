import type { Metadata } from "next";
import "./globals.css";
import Navigation from "@/components/Navigation";

export const metadata: Metadata = {
  title: "DocIntel RAG - Secure Document Intelligence",
  description: "Ingest, classify, and securely chat with complex invoices, NDAs, notes, and text files using agentic RAG and page citations.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      </head>
      <body>
        <div className="app-container">
          <Navigation />
          <main className="app-content">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
