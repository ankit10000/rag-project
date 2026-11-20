"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import {
  BookOpen,
  Files,
  MessagesSquare,
  Brain,
  Settings,
  Shield,
  Activity,
  LogOut,
  Menu,
  Sun,
  Moon,
  LayoutDashboard,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  SquarePen,
  MoreHorizontal,
  Pencil,
  Trash2,
  ArrowUpRight,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Conversation, User } from "@/lib/api-types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetTrigger,
} from "@/components/ui/sheet";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogCancel,
  AlertDialogAction,
} from "@/components/ui/alert-dialog";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";

const UserContext = createContext<User | null>(null);
const AppearanceContext = createContext<{
  dark: boolean;
  setTheme: (theme: "dark" | "light") => void;
}>({ dark: true, setTheme: () => {} });
export function useUser() {
  return useContext(UserContext);
}
export function useAppearance() {
  return useContext(AppearanceContext);
}

export function useResource<T>(load: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await load());
    } catch (e) {
      setError(e instanceof Error ? e : new Error("Request failed"));
    } finally {
      setLoading(false);
    }
  }, [load]);
  useEffect(() => {
    let active = true;
    load()
      .then((value) => {
        if (active) {
          setData(value);
          setError(null);
        }
      })
      .catch((e) => {
        if (active) setError(e);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [load]);
  return { data, error, loading, refresh };
}

export function ErrorNotice({ error }: { error: Error | null }) {
  const router = useRouter();
  useEffect(() => {
    if (error instanceof ApiError && error.status === 401)
      router.replace("/login");
  }, [error, router]);
  return error ? (
    <div
      role="alert"
      className="rounded-xl border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive"
    >
      {error.message}
    </div>
  ) : null;
}
export function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-border/60 px-6 py-10 text-center text-sm text-muted-foreground">
      {children}
    </div>
  );
}

const navigation = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/documents", label: "Document library", icon: Files },
  { href: "/conversations", label: "Conversations", icon: MessagesSquare },
  { href: "/memories", label: "Memories", icon: Brain },
  { href: "/jobs", label: "Processing activity", icon: Activity },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Workspace({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const auth = useResource(api.me);
  const recent = useResource(api.conversations);
  const refreshConversations = recent.refresh;
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [dark, setDark] = useState(true);
  const [selected, setSelected] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [renaming, setRenaming] = useState<Conversation | null>(null);
  const [title, setTitle] = useState("");
  const [deleting, setDeleting] = useState<Conversation | null>(null);
  const [mutating, setMutating] = useState(false);
  const [actionError, setActionError] = useState<Error | null>(null);

  useEffect(() => {
    try {
      const theme = localStorage.getItem("rag-theme") !== "light";
      document.documentElement.classList.toggle("dark", theme);
      queueMicrotask(() => {
        setDark(theme);
        setCollapsed(localStorage.getItem("rag-sidebar-collapsed") === "1");
      });
    } catch {
      /* The dark default also works without browser storage. */
    }
  }, []);
  useEffect(() => {
    const sync = () =>
      setSelected(
        new URLSearchParams(window.location.search).get("conversation") ?? "",
      );
    queueMicrotask(sync);
    const changed = () => {
      sync();
      void refreshConversations();
    };
    window.addEventListener("popstate", sync);
    window.addEventListener("rag:conversations-changed", changed);
    return () => {
      window.removeEventListener("popstate", sync);
      window.removeEventListener("rag:conversations-changed", changed);
    };
  }, [pathname, refreshConversations]);
  function setTheme(theme: "dark" | "light") {
    const next = theme === "dark";
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("rag-theme", theme);
    } catch {
      /* Storage is optional. */
    }
  }
  function toggleSidebar() {
    const next = !collapsed;
    setCollapsed(next);
    try {
      localStorage.setItem("rag-sidebar-collapsed", next ? "1" : "0");
    } catch {
      /* Storage is optional. */
    }
  }
  function beginRename(conversation: Conversation) {
    setActionError(null);
    setTitle(conversation.title);
    setRenaming(conversation);
  }
  async function rename(event: React.FormEvent) {
    event.preventDefault();
    if (!renaming || !title.trim() || mutating) return;
    setMutating(true);
    setActionError(null);
    try {
      await api.renameConversation(renaming.conversation_id, title.trim());
      setRenaming(null);
      window.dispatchEvent(new Event("rag:conversations-changed"));
    } catch (e) {
      setActionError(e as Error);
    } finally {
      setMutating(false);
    }
  }
  async function remove() {
    if (!deleting || mutating) return;
    setMutating(true);
    setActionError(null);
    try {
      await api.deleteConversation(deleting.conversation_id);
      if (selected === deleting.conversation_id) router.replace("/chat");
      setDeleting(null);
      window.dispatchEvent(new Event("rag:conversations-changed"));
    } catch (e) {
      setActionError(e as Error);
    } finally {
      setMutating(false);
    }
  }
  async function logout() {
    try {
      await api.logout();
      router.replace("/login");
      router.refresh();
    } catch (e) {
      setActionError(e as Error);
    }
  }

  if (auth.loading)
    return (
      <main
        id="main"
        role="status"
        className="mx-auto w-full max-w-4xl space-y-5 p-8"
      >
        <span className="sr-only">Opening your workspace…</span>
        <Skeleton className="h-9 w-48" />
        <Skeleton className="h-32 w-full" />
      </main>
    );
  if (auth.error || !auth.data)
    return (
      <main id="main" className="mx-auto max-w-md space p-8">
        <ErrorNotice error={auth.error} />
        <Link href="/login" className="underline">
          Sign in
        </Link>
      </main>
    );
  const user = auth.data;
  const isChat = pathname === "/chat";
  const filtered = (recent.data ?? []).filter((item) =>
    item.title.toLocaleLowerCase().includes(search.toLocaleLowerCase()),
  );
  const initials = (user.display_name || user.email)
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
  const closeMobile = () => setMobileOpen(false);

  function sidebar(compact: boolean) {
    return (
      <div className="flex h-full min-h-0 flex-col gap-3 p-3">
        <div
          className={`flex h-12 shrink-0 items-center ${compact ? "justify-center" : "justify-between px-1"}`}
        >
          <Link
            href="/chat"
            onClick={() => {
              closeMobile();
              setSelected("");
            }}
            className="inline-flex items-center gap-2.5 rounded-lg font-semibold tracking-tight"
            aria-label="RAG home"
          >
            <span className="grid size-9 place-items-center rounded-xl border border-border/60 bg-surface">
              <BookOpen className="size-4" />
            </span>
            {!compact && (
              <>
                <span>RAG</span>
                <span className="rounded border border-border/50 px-1.5 py-0.5 text-[10px] text-muted-foreground">
                  2.0
                </span>
              </>
            )}
          </Link>
          {!compact && (
            <Button
              variant="ghost"
              size="icon"
              className="hidden md:inline-flex"
              onClick={toggleSidebar}
              aria-label="Collapse sidebar"
            >
              <PanelLeftClose />
            </Button>
          )}
        </div>
        <div className="space-y-1">
          <Button
            variant="ghost"
            asChild
            className={`w-full ${compact ? "px-0" : "justify-start"}`}
          >
            <Link
              href="/chat"
              onClick={() => {
                closeMobile();
                setSelected("");
              }}
              title="New chat"
            >
              <SquarePen />
              {!compact && "New chat"}
              <span className="sr-only">{compact ? "New chat" : ""}</span>
            </Link>
          </Button>
          <Button
            variant="ghost"
            className={`w-full ${compact ? "px-0" : "justify-start text-muted-foreground"}`}
            onClick={() => {
              setSearch("");
              setSearchOpen(true);
            }}
            aria-label="Search conversations"
            title="Search conversations"
          >
            <Search />
            {!compact && "Search conversations"}
          </Button>
        </div>
        <nav
          aria-label="Workspace"
          className="space-y-1 border-t border-border/40 pt-3"
        >
          {navigation.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || pathname.startsWith(href + "/");
            return (
              <Link
                key={href}
                href={href}
                title={compact ? label : undefined}
                onClick={closeMobile}
                aria-label={compact ? label : undefined}
                aria-current={active ? "page" : undefined}
                className={`flex h-10 items-center gap-3 rounded-lg text-sm transition-colors ${compact ? "justify-center" : "px-3"} ${active ? "bg-accent font-medium text-foreground" : "text-muted-foreground hover:bg-accent/70 hover:text-foreground"}`}
              >
                <Icon className="size-4 shrink-0" />
                {!compact && <span className="truncate">{label}</span>}
              </Link>
            );
          })}
          {user.role === "admin" && (
            <Link
              href="/admin"
              onClick={closeMobile}
              title={compact ? "Users & access" : undefined}
              aria-label={compact ? "Users & access" : undefined}
              aria-current={pathname === "/admin" ? "page" : undefined}
              className={`flex h-10 items-center gap-3 rounded-lg text-sm hover:bg-accent ${compact ? "justify-center" : "px-3"} ${pathname === "/admin" ? "bg-accent text-foreground" : "text-muted-foreground"}`}
            >
              <Shield className="size-4 shrink-0" />
              {!compact && "Users & access"}
            </Link>
          )}
        </nav>
        {!compact && (
          <section
            aria-label="Recent chats"
            className="min-h-0 flex-1 overflow-y-auto pt-3"
          >
            <h2 className="px-3 pb-2 text-xs font-medium text-muted-foreground">
              Recent chats
            </h2>
            {recent.loading && !recent.data ? (
              <div className="space-y-2 p-2">
                <Skeleton className="h-9 w-full" />
                <Skeleton className="h-9 w-4/5" />
                <Skeleton className="h-9 w-full" />
              </div>
            ) : recent.error ? (
              <p className="px-3 text-xs text-muted-foreground">
                Could not load recent chats.{" "}
                <button
                  type="button"
                  className="underline"
                  onClick={() => void recent.refresh()}
                >
                  Retry
                </button>
              </p>
            ) : !recent.data?.length ? (
              <p className="px-3 py-2 text-xs leading-relaxed text-muted-foreground">
                Your conversations will appear here.
              </p>
            ) : (
              recent.data.slice(0, 20).map((item) => (
                <div
                  key={item.conversation_id}
                  className={`group flex min-w-0 items-center rounded-lg hover:bg-accent/60 ${selected === item.conversation_id && isChat ? "bg-accent" : ""}`}
                >
                  <Link
                    href={`/chat?conversation=${encodeURIComponent(item.conversation_id)}`}
                    onClick={() => {
                      closeMobile();
                      setSelected(item.conversation_id);
                    }}
                    aria-current={
                      selected === item.conversation_id && isChat
                        ? "page"
                        : undefined
                    }
                    className="min-w-0 flex-1 truncate rounded-lg px-3 py-2.5 text-sm"
                    title={item.title}
                  >
                    {item.title}
                  </Link>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="mr-1 size-8 shrink-0 opacity-100 md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100 data-[state=open]:opacity-100"
                        aria-label={`Actions for ${item.title}`}
                      >
                        <MoreHorizontal />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="start">
                      <DropdownMenuItem onSelect={() => beginRename(item)}>
                        <Pencil />
                        Rename
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        className="text-destructive focus:text-destructive"
                        onSelect={() => {
                          setActionError(null);
                          setDeleting(item);
                        }}
                      >
                        <Trash2 />
                        Delete
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              ))
            )}
          </section>
        )}
        <div
          className={`${compact ? "mt-auto" : ""} shrink-0 space-y-2 border-t border-border/40 pt-3`}
        >
          {!compact && (
            <div className="flex items-center gap-3 px-2 py-1">
              <span className="grid size-8 shrink-0 place-items-center rounded-full bg-accent text-xs font-medium">
                {initials}
              </span>
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">
                  {user.display_name || user.email}
                </p>
                <p className="truncate text-xs text-muted-foreground">
                  {user.role === "admin"
                    ? "Administrator"
                    : "Personal workspace"}
                </p>
              </div>
            </div>
          )}
          <div
            className={`flex gap-1 ${compact ? "flex-col" : "items-center justify-between"}`}
          >
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setTheme(dark ? "light" : "dark")}
              aria-label={dark ? "Use light mode" : "Use dark mode"}
              title={dark ? "Use light mode" : "Use dark mode"}
            >
              {dark ? <Sun /> : <Moon />}
            </Button>
            <Button
              variant="ghost"
              size={compact ? "icon" : "default"}
              onClick={logout}
              aria-label="Sign out"
              title="Sign out"
            >
              <LogOut />
              {!compact && "Sign out"}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <UserContext.Provider value={user}>
      <AppearanceContext.Provider value={{ dark, setTheme }}>
        <div className="flex h-dvh w-full min-w-0 overflow-hidden bg-background">
          <aside
            aria-label="Sidebar"
            className={`hidden h-dvh shrink-0 flex-col border-r border-border/30 bg-sidebar md:flex ${collapsed ? "w-[68px]" : "w-[260px]"}`}
          >
            {sidebar(collapsed)}
          </aside>
          <div className="flex min-h-0 min-w-0 flex-1 flex-col">
            <header className="flex h-[60px] shrink-0 items-center justify-between gap-3 px-4 sm:px-6">
              <div className="flex min-w-0 items-center gap-2">
                <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
                  <SheetTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="md:hidden"
                      aria-label="Toggle navigation"
                      aria-expanded={mobileOpen}
                    >
                      <Menu />
                    </Button>
                  </SheetTrigger>
                  <SheetContent
                    side="left"
                    className="w-[min(300px,90vw)] border-border/40 bg-sidebar p-0"
                  >
                    <SheetHeader className="sr-only">
                      <SheetTitle>Workspace navigation</SheetTitle>
                      <SheetDescription>
                        Navigate your private documents and conversations.
                      </SheetDescription>
                    </SheetHeader>
                    {sidebar(false)}
                  </SheetContent>
                </Sheet>
                {collapsed && (
                  <Button
                    variant="ghost"
                    size="icon"
                    className="hidden md:inline-flex"
                    onClick={toggleSidebar}
                    aria-label="Expand sidebar"
                  >
                    <PanelLeftOpen />
                  </Button>
                )}
                <Link
                  href="/chat"
                  className="truncate text-sm font-medium text-foreground"
                >
                  RAG workspace
                </Link>
              </div>
              <p className="hidden text-xs text-muted-foreground sm:block">
                Your sources. Grounded answers.
              </p>
              <Link
                href="/documents"
                className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground sm:hidden"
              >
                Sources
                <ArrowUpRight className="size-3" />
              </Link>
            </header>
            <main
              id="main"
              className={
                isChat
                  ? "flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden px-4 sm:px-6"
                  : "min-h-0 min-w-0 flex-1 overflow-y-auto"
              }
            >
              <div
                className={
                  isChat
                    ? "contents"
                    : "mx-auto flex w-full max-w-6xl flex-col gap-7 px-5 py-6 sm:px-8 sm:py-9"
                }
              >
                {actionError && !renaming && !deleting && (
                  <ErrorNotice error={actionError} />
                )}
                {children}
              </div>
            </main>
          </div>
        </div>
        <Dialog open={searchOpen} onOpenChange={setSearchOpen}>
          <DialogContent className="max-w-lg">
            <DialogHeader>
              <DialogTitle>Search conversations</DialogTitle>
              <DialogDescription>
                Find a conversation in your private workspace.
              </DialogDescription>
            </DialogHeader>
            <label htmlFor="conversation-search" className="sr-only">
              Search conversations
            </label>
            <Input
              id="conversation-search"
              autoFocus
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search your chats…"
            />
            <ul
              className="max-h-[50dvh] overflow-y-auto"
              aria-label="Conversation search results"
            >
              {filtered.length ? (
                filtered.map((item) => (
                  <li key={item.conversation_id}>
                    <Link
                      href={`/chat?conversation=${encodeURIComponent(item.conversation_id)}`}
                      onClick={() => {
                        setSearchOpen(false);
                        setSelected(item.conversation_id);
                        closeMobile();
                      }}
                      className="flex items-center gap-3 rounded-lg px-3 py-3 text-sm hover:bg-accent"
                    >
                      <MessagesSquare className="size-4 shrink-0 text-muted-foreground" />
                      <span className="truncate">{item.title}</span>
                    </Link>
                  </li>
                ))
              ) : (
                <li>
                  <p className="py-8 text-center text-sm text-muted-foreground">
                    {search
                      ? "No conversations match your search."
                      : "No conversations yet."}
                  </p>
                </li>
              )}
            </ul>
          </DialogContent>
        </Dialog>
        <Dialog
          open={!!renaming}
          onOpenChange={(open) => {
            if (!open) {
              setRenaming(null);
              setActionError(null);
            }
          }}
        >
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Rename conversation</DialogTitle>
              <DialogDescription>
                Choose a title that makes this conversation easy to find.
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={rename} className="space">
              <label htmlFor="conversation-title">Conversation title</label>
              <Input
                id="conversation-title"
                value={title}
                maxLength={200}
                onChange={(event) => setTitle(event.target.value)}
                autoFocus
                required
              />
              <ErrorNotice error={actionError} />
              <DialogFooter>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setRenaming(null)}
                >
                  Cancel
                </Button>
                <Button type="submit" disabled={mutating || !title.trim()}>
                  {mutating ? "Saving…" : "Save title"}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
        <AlertDialog
          open={!!deleting}
          onOpenChange={(open) => {
            if (!open) {
              setDeleting(null);
              setActionError(null);
            }
          }}
        >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete conversation?</AlertDialogTitle>
              <AlertDialogDescription>
                This permanently deletes “{deleting?.title}” and its messages
                and saved memories. This cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <ErrorNotice error={actionError} />
            <AlertDialogFooter>
              <AlertDialogCancel disabled={mutating}>Cancel</AlertDialogCancel>
              <AlertDialogAction
                className="bg-destructive text-background hover:bg-destructive/90"
                disabled={mutating}
                onClick={(event) => {
                  event.preventDefault();
                  void remove();
                }}
              >
                {mutating ? "Deleting…" : "Delete conversation"}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </AppearanceContext.Provider>
    </UserContext.Provider>
  );
}
