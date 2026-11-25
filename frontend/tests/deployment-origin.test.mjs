import test from "node:test";
import assert from "node:assert/strict";
import { POST } from "../app/api/v2/[...path]/route.ts";

function request(host="demo.example",origin="https://demo.example") {
  const req=new Request("http://frontend:3000/api/v2/auth/register", {
    method:"POST",body:"{}",headers:{host,origin,
      "x-forwarded-proto":"https","x-forwarded-host":"attacker.example"},
  });
  Object.defineProperty(req,"nextUrl",{value:new URL(req.url)});
  return req;
}
const context={params:Promise.resolve({path:["auth","register"]})};

test("configured HTTPS origin survives an internal HTTP hop with exact public Host",async()=>{
  const oldOrigin=process.env.RAG_PUBLIC_ORIGIN,oldFetch=globalThis.fetch;
  try {
    process.env.RAG_PUBLIC_ORIGIN="https://demo.example";
    let calls=0;
    globalThis.fetch=async()=>{calls++;return Response.json({ok:true});};
    assert.equal((await POST(request(),context)).status,200);
    assert.equal(calls,1);
    for (const [host,origin] of [["attacker.example","https://demo.example"],
      ["demo.example","https://attacker.example"],
      ["demo.example","http://demo.example"]]) {
      assert.equal((await POST(request(host,origin),context)).status,403);
    }
    assert.equal(calls,1,"rejected requests must not reach the private API");
  } finally {
    if (oldOrigin===undefined) delete process.env.RAG_PUBLIC_ORIGIN;
    else process.env.RAG_PUBLIC_ORIGIN=oldOrigin;
    globalThis.fetch=oldFetch;
  }
});

test("forwarded headers alone cannot enable a different browser origin",async()=>{
  const oldOrigin=process.env.RAG_PUBLIC_ORIGIN,oldFetch=globalThis.fetch;
  try {
    delete process.env.RAG_PUBLIC_ORIGIN;
    globalThis.fetch=()=>{throw new Error("must not call backend");};
    assert.equal((await POST(request(),context)).status,403);
  } finally {
    if (oldOrigin!==undefined) process.env.RAG_PUBLIC_ORIGIN=oldOrigin;
    globalThis.fetch=oldFetch;
  }
});

test("malformed or insecure deployment origins fail closed before mutation",async()=>{
  const oldOrigin=process.env.RAG_PUBLIC_ORIGIN,oldFetch=globalThis.fetch;
  try {
    globalThis.fetch=()=>{throw new Error("must not call backend");};
    for (const origin of ["", "http://demo.example","https://user:password@demo.example",
      "https://demo.example/path","https://demo.example?query=1","https://demo.example#fragment"]) {
      process.env.RAG_PUBLIC_ORIGIN=origin;
      assert.equal((await POST(request(),context)).status,503,origin);
    }
  } finally {
    if (oldOrigin===undefined) delete process.env.RAG_PUBLIC_ORIGIN;
    else process.env.RAG_PUBLIC_ORIGIN=oldOrigin;
    globalThis.fetch=oldFetch;
  }
});
