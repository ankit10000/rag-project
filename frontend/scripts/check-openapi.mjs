/** Route contract verification against actual FastAPI OpenAPI, no provider calls. */
const response = await fetch(
  process.argv[2] ?? "http://127.0.0.1:8000/api/v2/openapi.json",
);
if (!response.ok) throw new Error("OpenAPI unavailable");
const spec = await response.json();
const paths = spec.paths ?? {};
const contracts = {
  "/api/v2/auth/register": ["post"],
  "/api/v2/auth/login": ["post"],
  "/api/v2/auth/logout": ["post"],
  "/api/v2/auth/me": ["get"],
  "/api/v2/documents": ["get", "post"],
  "/api/v2/documents/{did}": ["get", "put", "delete"],
  "/api/v2/documents/{did}/file": ["get"],
  "/api/v2/conversations": ["get", "post"],
  "/api/v2/conversations/{cid}": ["get", "patch", "delete"],
  "/api/v2/chat": ["post"],
  "/api/v2/memories": ["get"],
  "/api/v2/conversations/{cid}/memories/{mid}": ["delete"],
  "/api/v2/jobs": ["get"],
  "/api/v2/jobs/{jid}/cancel": ["post"],
  "/api/v2/jobs/{jid}/retry": ["post"],
  "/api/v2/admin/users": ["get"],
  "/api/v2/admin/users/{uid}": ["patch"],
  "/api/v2/admin/users/{uid}/reset-password": ["post"],
};
let count = 0;
for (const [path, methods] of Object.entries(contracts)) {
  for (const method of methods) {
    if (!paths[path]?.[method])
      throw new Error(`Missing API contract: ${method} ${path}`);
    count++;
  }
}
console.log(`${count} frontend route/method contracts matched FastAPI OpenAPI`);
