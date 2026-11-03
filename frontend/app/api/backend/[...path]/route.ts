import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const maxDuration = 300;
const cookieName = "staytus_session";
const backend = process.env.BACKEND_URL || (process.env.NODE_ENV === "production" ? null : "http://127.0.0.1:8000");
type Context = { params: Promise<{ path: string[] }> };

async function proxy(request: NextRequest, context: Context) {
  if (!backend) {
    return NextResponse.json({ detail: "The server API address is not configured." }, { status: 503 });
  }
  const { path } = await context.params;
  if (!path.length || path.some(segment => !/^[A-Za-z0-9_.-]+$/.test(segment) || segment === "..")) {
    return NextResponse.json({ detail: "Invalid API path" }, { status: 400 });
  }
  const appOrigin = process.env.APP_ORIGIN || `${request.nextUrl.protocol}//${request.headers.get("host")}`;
  // Prevent another website from using the browser's session cookie to mutate state.
  if (!["GET", "HEAD"].includes(request.method)) {
    const origin = request.headers.get("origin");
    // Next dev may normalize nextUrl.hostname to localhost although the browser
    // used 127.0.0.1. Compare the browser origin to the actual request Host.
    if (origin && origin !== appOrigin) {
      return NextResponse.json({ detail: "Cross-origin request rejected" }, { status: 403 });
    }
  }
  const jar = await cookies();
  if (path.join("/") === "auth/logout") {
    const session = jar.get(cookieName)?.value;
    if (session) {
      try {
        await fetch(`${backend.replace(/\/$/, "")}/api/v1/auth/logout`, {
          method: "POST", headers: { Authorization: `Bearer ${session}` },
          cache: "no-store", signal: AbortSignal.timeout(5000),
        });
      } catch { /* Always clear the browser cookie even when the backend is unavailable. */ }
    }
    jar.delete(cookieName);
    return NextResponse.json({ ok: true });
  }
  const headers = new Headers({ Accept: "application/json" });
  const token = jar.get(cookieName)?.value;
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  const requestPath = path.join("/");
  // Chat can include retrieval/model work before the Orchestrate request.
  // Keep refresh and ordinary API budgets separate from that longer path.
  const timeoutSignal = AbortSignal.timeout(requestPath === "chat" ? 180000 : requestPath === "policies/refresh" ? 120000 : 45000);
  try {
    const upstream = await fetch(`${backend.replace(/\/$/, "")}/api/v1/${path.join("/")}${request.nextUrl.search}`, {
      method: request.method,
      headers,
      body: ["GET", "HEAD"].includes(request.method) ? undefined : await request.text(),
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.any([request.signal, timeoutSignal]),
    });
    if (upstream.status >= 300 && upstream.status < 400) {
      // OAuth returns through this same-origin proxy so the backend can bind
      // the callback to the initiating HttpOnly session. Forward only its
      // expected completion redirect, never an arbitrary upstream location.
      const callback = path.length === 3 && path[0] === "connections" && ["google", "microsoft"].includes(path[1]) && path[2] === "callback";
      const location = upstream.headers.get("location");
      if (!callback || upstream.status !== 303 || !location) return NextResponse.json({ detail: "Unexpected API redirect" }, { status: 502 });
      const target = new URL(location, appOrigin);
      const connection = target.searchParams.get("connection");
      if (target.origin !== new URL(appOrigin).origin || target.pathname !== "/" || target.hash || [...target.searchParams.keys()].some(key => key !== "connection") || ![path[1], "cancelled"].includes(connection || "")) {
        return NextResponse.json({ detail: "Unexpected authorization return destination" }, { status: 502 });
      }
      const redirected = NextResponse.redirect(target, 303);
      redirected.headers.set("Cache-Control", "no-store");
      return redirected;
    }
    if (["auth/register", "auth/login"].includes(path.join("/")) && upstream.ok) {
      const result = await upstream.json();
      if (typeof result.access_token !== "string") return NextResponse.json({ detail: "Backend did not create a session" }, { status: 502 });
      jar.set(cookieName, result.access_token, { httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax", path: "/", maxAge: 8 * 60 * 60 });
      const { access_token: unused, ...safe } = result;
      void unused;
      return NextResponse.json(safe);
    }
    const outputHeaders = new Headers({ "Content-Type": upstream.headers.get("content-type") || "application/json", "Cache-Control": "no-store" });
    const disposition = upstream.headers.get("content-disposition");
    if (disposition) outputHeaders.set("Content-Disposition", disposition);
    // A late response from an expired session must not clear a newer login's
    // cookie. The client handles 401; only explicit logout clears the cookie.
    return new Response(await upstream.arrayBuffer(), { status: upstream.status, headers: outputHeaders });
  } catch {
    if (request.signal.aborted) return NextResponse.json({ detail: "The request was cancelled." }, { status: 499 });
    if (timeoutSignal.aborted) {
      return NextResponse.json({ detail: requestPath === "chat"
        ? "The assistant request timed out after waiting for retrieval and IBM. Check the Action inbox and Activity log before retrying; a cloud request may still be running."
        : "This request took too long. Check the current state before trying again." }, { status: 504 });
    }
    return NextResponse.json({ detail: "Staytus API is temporarily unavailable. Please try again later." }, { status: 502 });
  }
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
