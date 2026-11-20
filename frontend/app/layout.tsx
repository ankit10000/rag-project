import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: { default: "RAG · Your knowledge workspace", template: "%s · RAG" },
  description:
    "Private document search, grounded answers and conversational memory.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{document.documentElement.classList.toggle('dark',localStorage.getItem('rag-theme')!=='light')}catch(e){}})()`,
          }}
        />
      </head>
      <body>
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
