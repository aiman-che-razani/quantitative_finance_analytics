"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  createChart,
  LineSeries,
  CandlestickSeries,
  ColorType,
  type Time,
} from "lightweight-charts";
type Equity = { timestamp: string; equity: number };
type Metrics = Record<
  string,
  number | null | number[] | Record<string, number>
>;
type Result = {
  id?: string;
  simulation?: {
    equity: Equity[];
    fills: Record<string, string | number>[];
    trades: Record<string, string | number>[];
    risk_decisions: Record<string, string | number>[];
  };
  benchmark?: { equity: Equity[] };
  metrics?: Metrics;
  provenance?: { provider: string; dataset_id: string };
  folds?: { test: string[]; models: Record<string, Record<string, number>> }[];
  pooled_test_auc?: Record<string, number | null>;
  out_of_sample_trading?: Record<
    string,
    { metrics: Metrics; equity: Equity[] }
  >;
};
type Dataset = {
  id: string;
  provider: string;
  symbols: string[];
  rows: number;
};
type Experiment = {
  id: string;
  kind: string;
  status: string;
  created_at: string;
  config: { strategy: string; symbols: string[] };
  error: string | null;
};
type Paper = {
  id: string;
  config: { dataset_id: string; symbols: string[]; strategy: string };
  state: {
    last_session: string | null;
    alerts: string[];
    last_error?: string;
    provider?: string;
    account?: { equity: number };
  };
};
async function api<T>(path: string, body?: unknown): Promise<T> {
  let r: Response;
  try {
    r = await fetch(
      `/api/${path}`,
      body
        ? {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          }
        : undefined,
    );
  } catch {
    throw new Error(
      "Dashboard server unreachable. Check experiment history before retrying.",
    );
  }
  // Upstream errors are not always JSON (e.g. a plain-text 500), so parse defensively.
  const text = await r.text();
  let data: { detail?: unknown } | null = null;
  try {
    data = JSON.parse(text);
  } catch {}
  if (!r.ok) {
    const detail = data?.detail;
    throw new Error(
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail
              .map(
                (e: { loc?: unknown[]; msg?: string }) =>
                  `${(e.loc ?? []).slice(1).join(".")}: ${e.msg}`,
              )
              .join(" · ")
          : `Research API error ${r.status}. Check experiment history before retrying.`,
    );
  }
  if (data === null)
    throw new Error(
      "Research API returned an unreadable response. Check experiment history before retrying.",
    );
  return data as T;
}
function Plot({
  rows,
  benchmark,
  title,
  caption,
}: {
  rows: Equity[];
  benchmark?: Equity[];
  title: string;
  caption?: string;
}) {
  const element = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!element.current || !rows.length) return;
    const chart = createChart(element.current, {
      autoSize: true,
      height: 300,
      layout: {
        background: { type: ColorType.Solid, color: "#111a21" },
        textColor: "#9eb0bd",
        attributionLogo: true,
      },
      grid: {
        vertLines: { color: "#1a2832" },
        horzLines: { color: "#1a2832" },
      },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false },
    });
    const series = chart.addSeries(LineSeries, {
      color: "#a8ecb4",
      lineWidth: 2,
    });
    series.setData(
      rows.map((r) => ({
        time: r.timestamp.slice(0, 10) as Time,
        value: r.equity,
      })),
    );
    if (benchmark?.length) {
      const b = chart.addSeries(LineSeries, { color: "#8199c5", lineWidth: 1 });
      b.setData(
        benchmark.map((r) => ({
          time: r.timestamp.slice(0, 10) as Time,
          value: r.equity,
        })),
      );
    }
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [rows, benchmark]);
  return (
    <section className="panel">
      <h2>{title}</h2>
      <div ref={element} role="img" aria-label={title} />
      <small>
        {caption ??
          (benchmark?.length
            ? "Drag to pan · Scroll to zoom · Green: strategy · Blue: buy and hold"
            : "Drag to pan · Scroll to zoom · Green: strategy")}
      </small>
    </section>
  );
}
type Bar = {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ema: number | null;
  rsi: number | null;
  bb_upper: number | null;
  bb_lower: number | null;
};
function MarketPlot({ bars }: { bars: Bar[] }) {
  const element = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!element.current || !bars.length) return;
    const chart = createChart(element.current, {
      autoSize: true,
      height: 420,
      layout: {
        background: { type: ColorType.Solid, color: "#111a21" },
        textColor: "#9eb0bd",
      },
      grid: {
        vertLines: { color: "#1a2832" },
        horzLines: { color: "#1a2832" },
      },
    });
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: "#a8ecb4",
      downColor: "#e39d9d",
      borderVisible: false,
      wickUpColor: "#a8ecb4",
      wickDownColor: "#e39d9d",
    });
    candles.setData(
      bars.map((b) => ({ ...b, time: b.timestamp.slice(0, 10) as Time })),
    );
    for (const [field, color] of [
      ["ema", "#e5ca8a"],
      ["bb_upper", "#8199c5"],
      ["bb_lower", "#8199c5"],
    ] as const) {
      const line = chart.addSeries(LineSeries, { color, lineWidth: 1 });
      line.setData(
        bars
          .filter((b) => b[field] !== null)
          .map((b) => ({
            time: b.timestamp.slice(0, 10) as Time,
            value: b[field] as number,
          })),
      );
    }
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [bars]);
  return (
    <section className="panel">
      <h2>Daily prices · EMA 200 · Bollinger 200 / 1.19</h2>
      <div
        ref={element}
        role="img"
        aria-label="Daily prices · EMA 200 · Bollinger 200 / 1.19"
      />
      <small>
        Last 3,000 sessions at most. Pan and zoom to inspect daily bars.
      </small>
    </section>
  );
}
function Table({ rows }: { rows: Record<string, unknown>[] }) {
  const columns = Object.keys(rows[0] || {});
  return (
    <div className="scroll">
      <table>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c}>{c.replaceAll("_", " ")}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 100).map((r, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={c}>
                  {typeof r[c] === "number"
                    ? (r[c] as number).toLocaleString("en-US", {
                        maximumFractionDigits: 4,
                      })
                    : String(r[c] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > 100 && (
        <small>
          First 100 of {rows.length.toLocaleString("en-US")} records. Export
          JSON for the complete ledger.
        </small>
      )}
    </div>
  );
}
const pct = (value: unknown) =>
  typeof value === "number" ? `${(value * 100).toFixed(2)}%` : "—";
// Metrics stored as fractions; shown as percentages everywhere so a table row
// never disagrees in unit with the tile above it.
const PCT_METRICS = new Set([
  "total_return",
  "cagr",
  "annualized_return",
  "annualized_volatility",
  "max_drawdown",
  "average_drawdown",
  "win_rate",
  "loss_rate",
  "exposure",
  "var_95",
  "cvar_95",
]);
const MONEY_METRICS = new Set([
  "average_winner",
  "average_loser",
  "expectancy",
]);
const money = (value: number) =>
  "$" +
  value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
function formatMetric(metric: string, value: unknown) {
  if (typeof value !== "number") return "—";
  if (PCT_METRICS.has(metric)) return pct(value);
  if (MONEY_METRICS.has(metric)) return money(value);
  if (metric === "turnover") return value.toFixed(2) + "×";
  return value.toLocaleString("en-US", { maximumFractionDigits: 4 });
}
export default function Workspace() {
  const [datasets, setDatasets] = useState<Dataset[]>([]),
    [dataset, setDataset] = useState("");
  const [symbols, setSymbols] = useState("SPY"),
    [strategy, setStrategy] = useState("ema_trend"),
    [strategies, setStrategies] = useState<string[]>([]);
  const [experiments, setExperiments] = useState<Experiment[]>([]),
    [papers, setPapers] = useState<Paper[]>([]),
    [result, setResult] = useState<Result | null>(null);
  const [bars, setBars] = useState<Bar[]>([]),
    [barsSource, setBarsSource] = useState<Dataset | undefined>();
  const [tab, setTab] = useState("Research"),
    [busy, setBusy] = useState(""), // status message while an action runs; "" = idle
    [error, setError] = useState(""),
    [cost, setCost] = useState(2.5),
    [short, setShort] = useState(false),
    [risk, setRisk] = useState(0.3),
    [ema, setEma] = useState(200),
    [order, setOrder] = useState("market");
  async function refresh() {
    const [ds, st, ex, pa] = await Promise.all([
      api<Dataset[]>("datasets"),
      api<{ strategies: string[] }>("strategies"),
      api<Experiment[]>("experiments"),
      api<Paper[]>("paper"),
    ]);
    setDatasets(ds);
    setDataset((old) => old || ds[0]?.id || "");
    setStrategies(st.strategies);
    setExperiments(ex);
    setPapers(pa);
  }
  useEffect(() => {
    refresh().catch((e) => setError(e.message));
  }, []);
  async function action(fn: () => Promise<void>, label = "Working…") {
    setBusy(label);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      // Refresh even after a failure: the error tells users to check history.
      await refresh().catch((e) =>
        setError((old) => old || (e instanceof Error ? e.message : String(e))),
      );
      setBusy("");
    }
  }
  const request = {
    dataset_id: dataset,
    symbols: [
      ...new Set(
        symbols
          .split(",")
          .map((s) => s.trim().toUpperCase())
          .filter(Boolean),
      ),
    ],
    strategy,
    execution: {
      commission_bps: cost,
      order_type: order,
      risk: { allow_short: short, max_drawdown: risk },
    },
    features: { ema_period: ema },
  };
  const metrics = result?.metrics;
  const drawdownRows = useMemo(
    () =>
      result?.simulation?.equity.flatMap((r, i) => {
        const value = (result.metrics?.drawdown as number[] | undefined)?.[i];
        return typeof value === "number" ? [{ ...r, equity: value * 100 }] : [];
      }) ?? [],
    [result],
  );
  const provenanceNote = (provider?: string) =>
    provider?.includes("synthetic")
      ? "SYNTHETIC DATA — engineering demonstration, not observed market performance."
      : "Provider: " + (provider || "unknown");
  const selected = datasets.find((d) => d.id === dataset);
  function exportResult() {
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(result, null, 2)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "axiom-experiment.json";
    link.click();
    URL.revokeObjectURL(url);
  }
  return (
    <main>
      <header>
        <a className="brand" href="/">
          AXIOM<span>RESEARCH / EXECUTION</span>
        </a>
        <span className="status">● PAPER EXECUTION ONLY</span>
      </header>
      <div className="intro">
        <div>
          <p className="eyebrow">QUANTITATIVE RESEARCH WORKSPACE</p>
          <h1>
            From hypothesis
            <br />
            to an auditable result.
          </h1>
          <p>Versioned data. Causal signals. Every fill accounted for.</p>
        </div>
        <div className="summary">
          <strong>{datasets.length}</strong>
          <span>dataset versions</span>
          <strong>
            {experiments.filter((e) => e.status === "SUCCEEDED").length}
          </strong>
          <span>completed experiments</span>
        </div>
      </div>
      <nav role="tablist">
        {[
          "Research",
          "Market data",
          "Experiments",
          "ML research",
          "Paper accounts",
        ].map((t) => (
          <button
            className={tab === t ? "active" : ""}
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            key={t}
          >
            {t}
          </button>
        ))}
      </nav>
      {error && (
        <div role="alert" className="error">
          {error}
        </div>
      )}
      <div role="status" aria-live="polite">
        {busy && <p>{busy}</p>}
      </div>
      {(tab === "Research" || tab === "ML research") && (
        <>
          <section className="panel controls">
            <label>
              Dataset version
              <select
                value={dataset}
                onChange={(e) => setDataset(e.target.value)}
              >
                {datasets.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.provider} · {d.symbols.length} instruments ·{" "}
                    {d.id.slice(0, 8)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Symbols, comma separated
              <input
                value={symbols}
                onChange={(e) => setSymbols(e.target.value)}
              />
            </label>
            <label>
              Strategy
              <select
                value={strategy}
                onChange={(e) => setStrategy(e.target.value)}
              >
                {strategies.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </label>
            <label>
              Commission / side, bps
              <input
                type="number"
                min="0"
                max="100"
                step="0.5"
                value={cost}
                onChange={(e) => setCost(+e.target.value)}
              />
            </label>
            <label>
              EMA window
              <input
                type="number"
                min="2"
                max="1000"
                value={ema}
                onChange={(e) => setEma(+e.target.value)}
              />
            </label>
            <label>
              Drawdown circuit breaker
              <select value={risk} onChange={(e) => setRisk(+e.target.value)}>
                {[0.1, 0.2, 0.3, 0.5].map((v) => (
                  <option value={v} key={v}>
                    {pct(v)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Entry order
              <select value={order} onChange={(e) => setOrder(e.target.value)}>
                {["market", "limit", "stop", "stop_limit"].map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={short}
                onChange={(e) => setShort(e.target.checked)}
              />{" "}
              Allow short signals
            </label>
            <button
              className="primary"
              disabled={Boolean(busy) || !dataset}
              onClick={() =>
                action(async () => {
                  setResult(
                    await api<Result>("experiments", {
                      ...request,
                      kind: tab === "ML research" ? "ml" : "backtest",
                    }),
                  );
                }, "Running research… You can find its durable status in experiment history.")
              }
            >
              {tab === "ML research"
                ? "Run walk-forward study"
                : "Run backtest"}{" "}
              ↗
            </button>
          </section>
          {!datasets.length && (
            <p>
              No dataset versions yet. Ingest one with scripts/ingest.py, then
              reload.
            </p>
          )}
          <p className="source">
            {provenanceNote(selected?.provider)} ·{" "}
            {selected ? selected.rows.toLocaleString("en-US") : "—"} bars ·
            Next-open fills · 1 bp slippage + 1 bp spread
          </p>
          {tab === "ML research" && (
            <p>
              Use one symbol. Expanding 504-session initial training,
              126-session validation and test windows, with a 5-session purge.
              Naive, logistic, random forest and XGBoost models share the same
              causal features.
            </p>
          )}
        </>
      )}
      {tab === "Market data" && (
        <section>
          <p>
            Uses the dataset selected in Research. Enter one symbol to inspect
            its prices and indicators.
          </p>
          <div className="controls">
            <label>
              Symbol
              <input
                value={symbols}
                onChange={(e) => setSymbols(e.target.value)}
              />
            </label>
            <button
              disabled={Boolean(busy) || !dataset}
              onClick={() =>
                action(async () => {
                  setBars(
                    await api<Bar[]>(
                      `market/${dataset}?symbol=${encodeURIComponent(symbols.split(",")[0].trim().toUpperCase())}`,
                    ),
                  );
                  setBarsSource(selected);
                }, "Loading market data…")
              }
            >
              Load market data
            </button>
          </div>
          <p className="source">
            {/* Describe the loaded bars, not whatever Research now selects. */}
            {provenanceNote((bars.length ? barsSource : selected)?.provider)} ·
            Dataset{" "}
            {(bars.length ? barsSource?.id : dataset)?.slice(0, 12) || "—"}
          </p>
          {bars.length ? (
            <>
              <MarketPlot bars={bars} />
              <details className="panel">
                <summary>OHLCV and indicators</summary>
                <Table rows={bars.slice(-100)} />
              </details>
            </>
          ) : (
            <p>
              No market data loaded. Enter a symbol and choose Load market data.
            </p>
          )}
        </section>
      )}
      {tab === "Experiments" && (
        <section className="panel">
          <div className="result-heading">
            <h2>Experiment history</h2>
            <button
              disabled={Boolean(busy)}
              onClick={() => action(async () => {}, "Refreshing…")}
            >
              Refresh
            </button>
          </div>
          <div className="scroll">
            <table>
              <thead>
                <tr>
                  <th>Created</th>
                  <th>Study</th>
                  <th>Status</th>
                  <th>Universe</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {experiments.map((e) => (
                  <tr key={e.id}>
                    <td>
                      {new Date(e.created_at)
                        .toISOString()
                        .slice(0, 16)
                        .replace("T", " ")}{" "}
                      UTC
                    </td>
                    <td>
                      {e.kind} / {e.config.strategy}
                    </td>
                    <td>
                      <span className={`run-${e.status.toLowerCase()}`}>
                        {e.status}
                      </span>
                      {e.error && (
                        <small className="run-error">
                          {e.error}
                        </small>
                      )}
                    </td>
                    <td>{e.config.symbols.join(", ")}</td>
                    <td>
                      <button
                        disabled={Boolean(busy) || e.status !== "SUCCEEDED"}
                        onClick={() =>
                          action(async () => {
                            const r = await api<{ result: Result }>(
                              `experiments/${e.id}`,
                            );
                            setResult({ ...r.result, id: e.id });
                            setTab(
                              e.kind === "ml" ? "ML research" : "Research",
                            );
                          }, "Opening experiment…")
                        }
                      >
                        Open
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      {tab === "Paper accounts" && (
        <section className="panel">
          <h2>Paper ledger</h2>
          <p>
            Historical daily replay with persistent account state. Repeated
            ticks do not duplicate fills. Uses the dataset and strategy selected
            in Research.
          </p>
          <button
            disabled={Boolean(busy) || !dataset}
            onClick={() =>
              action(async () => {
                await api<{ id: string }>("paper", request);
              }, "Creating paper account…")
            }
          >
            Create paper account
          </button>
          {papers.map((p) => (
            <article className="paper" key={p.id}>
              <code>{p.id}</code>
              <p className="source">
                {provenanceNote(
                  p.state.provider ??
                    datasets.find((d) => d.id === p.config.dataset_id)?.provider,
                )}{" "}
                · Dataset {p.config.dataset_id.slice(0, 12)} ·{" "}
                {p.config.strategy} on {p.config.symbols.join(", ")}
              </p>
              <p>
                Last session: {p.state.last_session || "Not started"} · Equity:{" "}
                {p.state.account ? money(p.state.account.equity) : "—"}
              </p>
              {p.state.alerts.length > 0 && (
                <p>
                  {p.state.alerts.map((a) => (
                    <span
                      key={a}
                      className={
                        a === "TICK_FAILED" ? "alert-danger" : "alert-warn"
                      }
                    >
                      {a.replaceAll("_", " ")}
                    </span>
                  ))}
                </p>
              )}
              {p.state.last_error && (
                <p>
                  <small>Last tick error: {p.state.last_error}</small>
                </p>
              )}
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const form = new FormData(e.currentTarget);
                  action(async () => {
                    await api<unknown>(`paper/${p.id}/advance`, {
                      as_of: form.get("date"),
                    });
                  }, "Updating paper ledger…");
                }}
              >
                <label>
                  Replay through
                  <input
                    type="date"
                    name="date"
                    required
                    defaultValue="2025-12-31"
                  />
                </label>
                <button disabled={Boolean(busy)}>Advance ledger</button>
              </form>
            </article>
          ))}
        </section>
      )}
      {result &&
        (tab === "ML research"
          ? Boolean(result.folds)
          : tab === "Research" && !result.folds) && (
          <>
            <div className="result-heading">
              <h2>Research result</h2>
              <button onClick={exportResult}>Export JSON ↓</button>
            </div>
            <p className="source">
              {result.provenance?.provider
                ? provenanceNote(result.provenance.provider)
                : "—"}{" "}
              · Dataset {result.provenance?.dataset_id?.slice(0, 12) ?? "—"} ·{" "}
              {result.id}
            </p>
            {metrics && (
              <div className="metrics">
                {[
                  ["Total return", pct(metrics.total_return)],
                  ["CAGR", pct(metrics.cagr)],
                  [
                    "Sharpe",
                    typeof metrics.sharpe === "number"
                      ? metrics.sharpe.toFixed(2)
                      : "—",
                  ],
                  ["Max drawdown", pct(metrics.max_drawdown)],
                  ["Win rate", pct(metrics.win_rate)],
                  [
                    "Trades",
                    typeof metrics.number_of_trades === "number"
                      ? metrics.number_of_trades.toLocaleString("en-US")
                      : "—",
                  ],
                ].map(([label, value]) => (
                  <div key={label}>
                    <span>{label}</span>
                    <strong>{value}</strong>
                  </div>
                ))}
              </div>
            )}
            {result.simulation && (
              <>
                <Plot
                  title="Portfolio equity"
                  rows={result.simulation.equity}
                  benchmark={result.benchmark?.equity}
                />
                <Plot
                  title="Drawdown (%)"
                  caption="Drag to pan · Scroll to zoom · Percent below running peak"
                  rows={drawdownRows}
                />
                <section className="panel">
                  <h2>Monthly returns</h2>
                  <div className="heatmap">
                    {Object.entries(
                      (metrics?.monthly_returns || {}) as Record<
                        string,
                        number
                      >,
                    ).map(([m, v]) => (
                      <div
                        key={m}
                        style={{
                          background:
                            v >= 0
                              ? `rgba(80,170,115,${Math.min(0.45, 0.12 + Math.abs(v) * 8)})`
                              : `rgba(210,90,90,${Math.min(0.45, 0.12 + Math.abs(v) * 8)})`,
                        }}
                      >
                        <small>{m}</small>
                        <strong>{pct(v)}</strong>
                      </div>
                    ))}
                  </div>
                </section>
                <details className="panel">
                  <summary>Full performance and risk metrics</summary>
                  <Table
                    rows={Object.entries(metrics || {})
                      .filter(([, v]) => typeof v === "number" || v === null)
                      .map(([metric, value]) => ({
                        metric,
                        value: formatMetric(metric, value),
                      }))}
                  />
                </details>
                <details className="panel">
                  <summary>Execution ledger</summary>
                  <Table rows={result.simulation.fills} />
                </details>
                <details className="panel">
                  <summary>Closed trades</summary>
                  <Table rows={result.simulation.trades} />
                </details>
                <details className="panel">
                  <summary>Risk decisions</summary>
                  <Table rows={result.simulation.risk_decisions} />
                </details>
              </>
            )}
            {result.out_of_sample_trading &&
              Object.entries(result.out_of_sample_trading).map(([name, r]) => (
                <section key={name}>
                  <h2>{name} · Out-of-sample trading</h2>
                  <p>
                    Total return {pct(r.metrics.total_return)} · Drawdown{" "}
                    {pct(r.metrics.max_drawdown)}
                  </p>
                  <Plot title={`${name} equity`} rows={r.equity} />
                </section>
              ))}
            {result.pooled_test_auc && (
              <section className="panel">
                <h2>Pooled test AUC</h2>
                <p className="source">
                  Per-fold AUC on short test windows reads above 0.5 even
                  with no signal, so compare pooled AUC with a random-walk
                  null (scripts/demo_ml.py), not with 0.5. The dashboard does
                  not compute that null, so these values are not evidence of
                  skill.
                </p>
                <Table
                  rows={Object.entries(result.pooled_test_auc).map(
                    ([model, auc]) => ({ model, pooled_test_auc: auc ?? "—" }),
                  )}
                />
              </section>
            )}
            {result.folds && (
              <section className="panel">
                <h2>Prediction evaluation by test fold</h2>
                <Table
                  rows={result.folds.flatMap((f) =>
                    Object.entries(f.models).map(([model, m]) => ({
                      test_start: f.test[0].slice(0, 10),
                      model,
                      ...m,
                    })),
                  )}
                />
              </section>
            )}
          </>
        )}
      <footer>
        <p>
          Daily bars · Shared portfolio accounting · Zero risk-free rate · Open
          positions marked at the last close
        </p>
        <p>
          Research results exclude financing, borrow fees and dividends. Daily
          OHLC cannot identify every intrabar path.{" "}
          <a
            href="https://www.tradingview.com/"
            target="_blank"
            rel="noreferrer"
          >
            Charts by TradingView
          </a>
        </p>
      </footer>
    </main>
  );
}
