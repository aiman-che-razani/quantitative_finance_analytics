import { NextRequest } from "next/server";
export const dynamic = "force-dynamic";
async function proxy(
  req: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
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
    if (origin && new URL(origin).host !== req.headers.get("host"))
      return Response.json({ detail: "Origin rejected" }, { status: 403 });
  }
  const token = process.env.API_TOKEN;
  if (!token)
    return Response.json(
      { detail: "API_TOKEN is not configured on the dashboard server" },
      { status: 503 },
    );
  const body = req.method === "POST" ? await req.text() : undefined;
  if (body && body.length > 65536)
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
