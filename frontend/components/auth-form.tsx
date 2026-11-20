"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { BookOpen, ArrowRight } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
export function AuthForm({ register = false }: { register?: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const values = new FormData(event.currentTarget);
    try {
      if (register) {
        await api.register(
          String(values.get("email")),
          String(values.get("password")),
          String(values.get("display_name")),
        );
        setMessage(
          "If this address is eligible, your account is ready. Sign in to continue.",
        );
      } else {
        await api.login(
          String(values.get("email")),
          String(values.get("password")),
        );
        router.replace("/dashboard");
        router.refresh();
      }
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 401
          ? "Email or password was not accepted."
          : e instanceof Error
            ? e.message
            : "Could not sign in.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <main id="main" className="min-h-dvh grid items-center bg-background px-5 py-12">
      <div className="mx-auto w-full max-w-sm space-y-8">
        <div className="row justify-center text-xl font-semibold tracking-tight">
          <span className="grid size-10 place-items-center rounded-xl border bg-card"><BookOpen className="size-5" /></span>
          RAG
        </div>
        <div className="text-center">
          <h1>{register ? "Create your workspace" : "Welcome back"}</h1>
          <p className="muted mt-2">
            {register
              ? "A private home for your documents and grounded answers."
              : "Sign in to pick up where you left off."}
          </p>
        </div>
        <Card className="border-0 bg-transparent shadow-none">
          <CardHeader className="sr-only">
            <CardTitle>{register ? "Account setup" : "Sign in"}</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <form onSubmit={submit} className="space">
              {register && (
                <div className="field">
                  <label htmlFor="display_name">Name</label>
                  <Input
                    id="display_name"
                    name="display_name"
                    autoComplete="name"
                    maxLength={100}
                    required
                  />
                </div>
              )}
              <div className="field">
                <label htmlFor="email">Email</label>
                <Input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  maxLength={254}
                  required
                />
              </div>
              <div className="field">
                <label htmlFor="password">Password</label>
                <Input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete={register ? "new-password" : "current-password"}
                  minLength={register ? 12 : 1}
                  maxLength={1024}
                  required
                />
                {register && (
                  <p className="text-xs muted">
                    Use at least 12 characters. Never reuse a password.
                  </p>
                )}
              </div>
              {error && (
                <p role="alert" className="text-destructive text-sm">
                  {error}
                </p>
              )}
              {message && (
                <p role="status" className="text-sm">
                  {message}{" "}
                  <Link href="/login" className="underline">
                    Sign in
                  </Link>
                </p>
              )}
              <Button disabled={busy} className="w-full">
                {busy
                  ? "Please wait…"
                  : register
                    ? "Create account"
                    : "Sign in"}
                <ArrowRight />
              </Button>
              <p className="text-xs muted">
                Forgot your password? Contact your administrator for a secure
                reset.
              </p>
            </form>
          </CardContent>
        </Card>
        <p className="text-center text-sm muted">
          {register ? "Already have an account?" : "New here?"}{" "}
          <Link
            className="text-foreground underline underline-offset-4"
            href={register ? "/login" : "/register"}
          >
            {register ? "Sign in" : "Create an account"}
          </Link>
        </p>
      </div>
    </main>
  );
}
