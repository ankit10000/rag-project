"use client";
import { Button } from "@/components/ui/button";
export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <main id="main" className="mx-auto max-w-xl p-10 space">
      <h1>Something went wrong</h1>
      <p>
        We could not complete that action. Your private details have not been
        displayed.
      </p>
      <Button onClick={reset}>Try again</Button>
    </main>
  );
}
