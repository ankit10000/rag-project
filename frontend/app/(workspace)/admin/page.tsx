"use client";
import { useState } from "react";
import {
  Search,
  Shield,
  MoreHorizontal,
  KeyRound,
  UserRoundCog,
  Power,
} from "lucide-react";
import { api } from "@/lib/api";
import type { User } from "@/lib/api-types";
import {
  useResource,
  useUser,
  ErrorNotice,
  Empty,
} from "@/components/workspace";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableHeader,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
} from "@/components/ui/table";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
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
type Change = { user: User; kind: "role" | "status"; value: string };
function UserTable() {
  const { data, error, loading, refresh } = useResource(api.users);
  const [query, setQuery] = useState(""),
    [status, setStatus] = useState("all");
  const [change, setChange] = useState<Change | null>(null),
    [resetUser, setResetUser] = useState<User | null>(null);
  const [password, setPassword] = useState(""),
    [busy, setBusy] = useState(false),
    [actionError, setActionError] = useState<Error | null>(null);
  function choose(user: User, kind: "role" | "status") {
    setActionError(null);
    setChange({
      user,
      kind,
      value:
        kind === "role"
          ? user.role === "admin"
            ? "user"
            : "admin"
          : user.status === "active"
            ? "disabled"
            : "active",
    });
  }
  async function apply() {
    if (!change) return;
    setBusy(true);
    setActionError(null);
    try {
      await api.updateUser(change.user.id, { [change.kind]: change.value });
      await refresh();
      setChange(null);
    } catch (e) {
      setActionError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  async function reset(event: React.FormEvent) {
    event.preventDefault();
    if (!resetUser) return;
    setBusy(true);
    setActionError(null);
    try {
      await api.resetPassword(resetUser.id, password);
      setResetUser(null);
      setPassword("");
      await refresh();
    } catch (e) {
      setActionError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  const shown = data?.filter(
    (user) =>
      (status === "all" || user.status === status) &&
      `${user.display_name} ${user.email}`
        .toLocaleLowerCase()
        .includes(query.toLocaleLowerCase()),
  );
  return (
    <>
      <ErrorNotice error={error} />
      <div className="flex flex-col gap-3 sm:flex-row">
        <div className="relative flex-1">
          <label htmlFor="user-search" className="sr-only">
            Search users
          </label>
          <Search className="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground" />
          <Input
            id="user-search"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="pl-10"
            placeholder="Search users by name or email"
          />
        </div>
        <label className="sr-only" htmlFor="user-status">
          Account status
        </label>
        <select
          id="user-status"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="sm:w-44"
        >
          <option value="all">All statuses</option>
          <option value="active">Active</option>
          <option value="disabled">Disabled</option>
        </select>
      </div>
      {loading ? (
        <div role="status" aria-label="Loading users" className="space-y-3">
          {[0, 1, 2].map((n) => (
            <Skeleton key={n} className="h-20" />
          ))}
        </div>
      ) : !shown?.length ? (
        <Empty>No users match your search.</Empty>
      ) : (
        <div className="overflow-hidden rounded-xl border border-border/60">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>User</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-12">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {shown.map((user) => (
                <TableRow key={user.id}>
                  <TableCell>
                    <p className="max-w-48 break-words font-medium">
                      {user.display_name || "Unnamed user"}
                    </p>
                    <p className="mt-1 max-w-64 break-all text-xs muted">
                      {user.email}
                    </p>
                  </TableCell>
                  <TableCell>
                    <Badge className="capitalize">{user.role}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge
                      className={
                        user.status === "active"
                          ? "text-success"
                          : "text-muted-foreground"
                      }
                    >
                      {user.status}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          disabled={busy}
                          aria-label={`Manage ${user.email}`}
                        >
                          <MoreHorizontal />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem
                          onSelect={() => choose(user, "status")}
                        >
                          <Power />
                          {user.status === "active" ? "Disable" : "Enable"}{" "}
                          account
                        </DropdownMenuItem>
                        <DropdownMenuItem onSelect={() => choose(user, "role")}>
                          <UserRoundCog />
                          Change role
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          onSelect={() => {
                            setActionError(null);
                            setResetUser(user);
                            setPassword("");
                          }}
                        >
                          <KeyRound />
                          Reset password
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <AlertDialog
        open={!!change}
        onOpenChange={(open) => {
          if (!open && !busy) {
            setChange(null);
            setActionError(null);
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {change?.kind === "role"
                ? "Change account role?"
                : change?.value === "disabled"
                  ? "Disable account?"
                  : "Enable account?"}
            </AlertDialogTitle>
            <AlertDialogDescription>
              Set {change?.user.email} {change?.kind} to {change?.value}.
              Existing sessions may be revoked. This account change is recorded
              by the server.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <ErrorNotice error={actionError} />
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={busy}
              onClick={(event) => {
                event.preventDefault();
                void apply();
              }}
            >
              {busy ? "Applying…" : "Confirm change"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <Dialog
        open={!!resetUser}
        onOpenChange={(open) => {
          if (!open && !busy) {
            setResetUser(null);
            setPassword("");
            setActionError(null);
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reset password</DialogTitle>
            <DialogDescription>
              Reset the password for {resetUser?.email}. Existing sessions will
              be revoked. Deliver the new password securely outside this
              application.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={reset} className="space">
            <div className="field">
              <label htmlFor="admin-new-password">New password</label>
              <Input
                id="admin-new-password"
                type="password"
                minLength={12}
                maxLength={1024}
                autoComplete="new-password"
                value={password}
                required
                onChange={(e) => setPassword(e.target.value)}
              />
              <p className="text-xs muted">Use at least 12 characters.</p>
            </div>
            <ErrorNotice error={actionError} />
            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                disabled={busy}
                onClick={() => {
                  setResetUser(null);
                  setPassword("");
                }}
              >
                Cancel
              </Button>
              <Button
                variant="destructive"
                type="submit"
                disabled={busy || password.length < 12}
              >
                {busy ? "Resetting…" : "Reset password"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
export default function Admin() {
  const user = useUser();
  return (
    <>
      <div>
        <div className="flex items-center gap-3">
          <Shield className="size-5 text-muted-foreground" />
          <h1>Users & access</h1>
        </div>
        <p className="mt-2 text-sm muted">Manage who can use this workspace.</p>
      </div>
      {user?.role === "admin" ? (
        <>
          <UserTable />
          <p className="text-xs muted">
            Account changes and password resets are recorded by the server.
          </p>
        </>
      ) : (
        <div role="alert" className="rounded-xl border border-border/60 p-6">
          <h2 className="font-medium">Access denied</h2>
          <p className="mt-2 text-sm muted">
            This page is available to administrators.
          </p>
        </div>
      )}
    </>
  );
}
