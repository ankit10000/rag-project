"use client";
import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  UserRound,
  Sun,
  Moon,
  LogOut,
  ArrowUpRight,
  LockKeyhole,
  Settings2,
} from "lucide-react";
import { api } from "@/lib/api";
import { useUser, useAppearance, ErrorNotice } from "@/components/workspace";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
export default function Settings() {
  const user = useUser(),
    { dark, setTheme } = useAppearance(),
    router = useRouter();
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<Error | null>(null);
  async function logout() {
    setBusy(true);
    setError(null);
    try {
      await api.logout();
      router.replace("/login");
      router.refresh();
    } catch (e) {
      setError(e as Error);
      setBusy(false);
    }
  }
  return (
    <>
      <div>
        <h1>Settings</h1>
        <p className="mt-2 text-sm muted">Make this workspace yours.</p>
      </div>
      <ErrorNotice error={error} />
      <Tabs defaultValue="profile" className="min-w-0">
        <TabsList aria-label="Settings sections">
          <TabsTrigger value="profile">Profile</TabsTrigger>
          <TabsTrigger value="appearance">Appearance</TabsTrigger>
          <TabsTrigger value="privacy">Privacy</TabsTrigger>
        </TabsList>
        <TabsContent value="profile" className="space-y-8">
          <section className="space-y-5">
            <div className="flex items-center gap-3">
              <UserRound className="size-4 text-muted-foreground" />
              <h2 className="font-medium">Your profile</h2>
            </div>
            <dl className="grid gap-5 rounded-xl border border-border/60 p-5 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-xs muted">Name</dt>
                <dd className="mt-1 break-words">
                  {user?.display_name || "—"}
                </dd>
              </div>
              <div>
                <dt className="text-xs muted">Email</dt>
                <dd className="mt-1 break-all">{user?.email}</dd>
              </div>
              <div>
                <dt className="text-xs muted">Role</dt>
                <dd className="mt-2">
                  <Badge className="capitalize">{user?.role}</Badge>
                </dd>
              </div>
              <div>
                <dt className="text-xs muted">Account status</dt>
                <dd className="mt-2">
                  <Badge className="capitalize">{user?.status}</Badge>
                </dd>
              </div>
            </dl>
          </section>
          <section className="space-y-3">
            <div className="flex items-center gap-3">
              <LockKeyhole className="size-4 text-muted-foreground" />
              <h2 className="font-medium">Account & session</h2>
            </div>
            <p className="max-w-2xl text-sm leading-7 muted">
              Signing out ends this session. To change a forgotten or
              compromised password, contact your administrator. A password reset
              ends existing sessions.
            </p>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => void logout()}
            >
              <LogOut />
              {busy ? "Signing out…" : "Sign out of this session"}
            </Button>
          </section>
          <section className="space-y-3 border-t border-border/50 pt-6">
            <div className="flex items-center gap-3">
              <Settings2 className="size-4 text-muted-foreground" />
              <h2 className="font-medium">Model & provider</h2>
            </div>
            <p className="max-w-2xl text-sm leading-7 muted">
              Model and provider configuration is managed by your workspace
              administrator. This workspace does not offer account-level model
              settings.
            </p>
          </section>
        </TabsContent>
        <TabsContent value="appearance" className="space-y-5">
          <div>
            <h2 className="font-medium">Appearance</h2>
            <p className="mt-2 text-sm muted">
              Choose the look of your workspace. Your choice is saved on this
              browser.
            </p>
          </div>
          <div
            className="grid max-w-xl gap-3 sm:grid-cols-2"
            role="group"
            aria-label="Color theme"
          >
            <Button
              variant="outline"
              className={`h-auto justify-start gap-3 rounded-xl p-5 ${dark ? "border-foreground bg-secondary" : ""}`}
              aria-pressed={dark}
              onClick={() => setTheme("dark")}
            >
              <Moon className="size-5" />
              <span className="text-left">
                <span className="block font-medium">Dark</span>
                <span className="mt-1 block text-xs muted">
                  Charcoal and neutral grey
                </span>
              </span>
            </Button>
            <Button
              variant="outline"
              className={`h-auto justify-start gap-3 rounded-xl p-5 ${!dark ? "border-foreground bg-secondary" : ""}`}
              aria-pressed={!dark}
              onClick={() => setTheme("light")}
            >
              <Sun className="size-5" />
              <span className="text-left">
                <span className="block font-medium">Light</span>
                <span className="mt-1 block text-xs muted">
                  Soft, clear neutrals
                </span>
              </span>
            </Button>
          </div>
        </TabsContent>
        <TabsContent value="privacy" className="space-y-6">
          <div>
            <h2 className="font-medium">Your data stays in your workspace</h2>
            <p className="mt-2 max-w-2xl text-sm leading-7 muted">
              Your documents, conversations and saved memories are private to
              your account. You control what you keep.
            </p>
          </div>
          <div className="divide-y divide-border/50 rounded-xl border border-border/60">
            {[
              {
                title: "Document library",
                text: "Review source PDFs, replace files or remove documents.",
                href: "/documents",
              },
              {
                title: "Conversations",
                text: "Delete a conversation, its messages and associated memories.",
                href: "/conversations",
              },
              {
                title: "Saved memories",
                text: "See supporting source links and forget individual memories.",
                href: "/memories",
              },
            ].map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="flex items-center justify-between gap-4 p-5 hover:bg-accent/40"
              >
                <div>
                  <h3 className="text-sm font-medium">{item.title}</h3>
                  <p className="mt-1 text-xs muted">{item.text}</p>
                </div>
                <ArrowUpRight className="size-4 shrink-0 text-muted-foreground" />
              </Link>
            ))}
          </div>
          <p className="text-xs muted">
            Account deletion is not available here. Contact your administrator
            for account access requests.
          </p>
        </TabsContent>
      </Tabs>
    </>
  );
}
