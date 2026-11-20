import Link from "next/link";
export default function NotFound() {
  return (
    <main id="main" className="mx-auto max-w-xl p-10 space">
      <h1>Page not found</h1>
      <p>This page may have moved or you may not have access.</p>
      <Link href="/dashboard" className="underline">
        Return to dashboard
      </Link>
    </main>
  );
}
