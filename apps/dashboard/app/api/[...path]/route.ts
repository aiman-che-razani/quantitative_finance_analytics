import { NextRequest } from "next/server";
export const dynamic = "force-dynamic";
const MAX_BODY_BYTES = 65536;
// DNS-rebinding guard: only answer requests addressed to a loopback name.
const ALLOWED_HOSTS = new Set(
  (process.env.AXIOM_ALLOWED_HOSTS || "127.0.0.1,localhost,[::1]")
    .split(",")
    .map((h) => h.trim().toLowerCase()),
);
function hostnameOf(value: string | null): string | null {
  if (!value) return null;
  try {
    return new URL(`http://${value}`).hostname;
  } catch {
    return null;
  }
}
async function proxy(
  req: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  if (!ALLOWED_HOSTS.has(hostnameOf(req.headers.get("host")) ?? ""))
    return Response.json({ detail: "Host rejected" }, { status: 403 });
  const { path } = await context.params;
  const route = path.join("/");
  if (
    !/^(health|instruments|datasets|strategies|experiments|paper|market)(\/[a-zA-Z0-9-]+)?(\/advance)?$/.test(
      route,
    )
  )
    return Response.json({ detail: "Unknown route" }, { status: 404 });
  if (req.method === "POST") {
    const origin = req.headers.get("origin");
    if (origin) {
      let originHost: string | null = null;
      try {
        originHost = new URL(origin).host;
      } catch {}
      if (originHost !== req.headers.get("host"))
        return Response.json({ detail: "Origin rejected" }, { status: 403 });
    }
  }
  const token = process.env.API_TOKEN;
  if (!token)
    return Response.json(
      { detail: "API_TOKEN is not configured on the dashboard server" },
      { status: 503 },
    );
  // A POST must declare its size, so an unbounded chunked body is never buffered.
  if (req.method === "POST" && req.headers.get("content-length") === null)
    return Response.json({ detail: "Content-Length required" }, { status: 411 });
  if (Number(req.headers.get("content-length") ?? 0) > MAX_BODY_BYTES)
    return Response.json({ detail: "Request too large" }, { status: 413 });
  const body = req.method === "POST" ? await req.text() : undefined;
  if (body && Buffer.byteLength(body, "utf8") > MAX_BODY_BYTES)
    return Response.json({ detail: "Request too large" }, { status: 413 });
  try {
    const upstream = await fetch(
      `${process.env.AXIOM_API_URL || "http://127.0.0.1:8820"}/${route}${req.nextUrl.search}`,
      {
        method: req.method,
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body,
        cache: "no-store",
        signal: AbortSignal.timeout(300000),
      },
    );
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return Response.json(
      {
        detail:
          "Research API unavailable or request timed out. Check experiment history before retrying.",
      },
      { status: 502 },
    );
  }
}
export { proxy as GET, proxy as POST };
