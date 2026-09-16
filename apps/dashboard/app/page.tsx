"use client";
import { useEffect, useRef, useState } from "react";
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
  state: {
    last_session: string | null;
    alerts: string[];
    account?: { equity: number };
  };
};
async function api(path: string, body?: unknown) {
  const r = await fetch(
    `/api/${path}`,
    body
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      : undefined,
  );
  const data = await r.json();
  if (!r.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail),
    );
  return data;
}
function Plot({
  rows,
  benchmark,
  title,
}: {
  rows: Equity[];
  benchmark?: Equity[];
  title: string;
}) {
  const element = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!element.current || !rows.length) return;
    const chart = createChart(element.current, {
      autoSize: true,
      height: 300,
      layout: {
        background: { type: ColorType.Solid, color: "#111a21" },
        textColor: "#a5b7c4",
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
      <div ref={element} aria-label={title} />
      <small>
        Drag to pan · Scroll to zoom · Green: strategy · Blue: buy and hold
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
        textColor: "#a5b7c4",
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
      <div ref={element} />
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
                    ? (r[c] as number).toLocaleString(undefined, {
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
          First 100 of {rows.length.toLocaleString()} records. Export JSON for
          the complete ledger.
        </small>
      )}
    </div>
  );
}
const pct = (value: unknown) =>
  typeof value === "number" ? `${(value * 100).toFixed(2)}%` : "—";
export default function Workspace() {
  const [datasets, setDatasets] = useState<Dataset[]>([]),
    [dataset, setDataset] = useState("");
  const [symbols, setSymbols] = useState("SPY"),
    [strategy, setStrategy] = useState("ema_trend"),
    [strategies, setStrategies] = useState<string[]>([]);
  const [experiments, setExperiments] = useState<Experiment[]>([]),
    [papers, setPapers] = useState<Paper[]>([]),
    [result, setResult] = useState<Result | null>(null);
  const [bars, setBars] = useState<Bar[]>([]);
  const [tab, setTab] = useState("Research"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [cost, setCost] = useState(2.5),
    [short, setShort] = useState(false),
    [risk, setRisk] = useState(0.3),
    [ema, setEma] = useState(200),
    [order, setOrder] = useState("market");
  async function refresh() {
    const [ds, st, ex, pa] = await Promise.all([
      api("datasets"),
      api("strategies"),
      api("experiments"),
      api("paper"),
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
  async function action(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  const request = {
    dataset_id: dataset,
    symbols: symbols
      .split(",")
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean),
    strategy,
    execution: {
      commission_bps: cost,
      order_type: order,
      risk: { allow_short: short, max_drawdown: risk },
    },
    features: { ema_period: ema },
  };
  const metrics = result?.metrics;
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
      <nav>
        {[
          "Research",
          "Market data",
          "Experiments",
          "ML research",
          "Paper accounts",
        ].map((t) => (
          <button
            className={tab === t ? "active" : ""}
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
      {busy && (
        <p role="status">
          Running research… You can find its durable status in experiment
          history.
        </p>
      )}
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
              disabled={busy || !dataset}
              onClick={() =>
                action(async () => {
                  setResult(
                    await api("experiments", {
                      ...request,
                      kind: tab === "ML research" ? "ml" : "backtest",
                    }),
                  );
                })
              }
            >
              {tab === "ML research"
                ? "Run walk-forward study"
                : "Run backtest"}{" "}
              ↗
            </button>
          </section>
          <p className="source">
            {selected?.provider.includes("synthetic")
              ? "SYNTHETIC DATA — engineering demonstration, not observed market performance."
              : "Provider: " + (selected?.provider || "none")}{" "}
            · {selected?.rows.toLocaleString()} bars · Next-open fills · 1 bp
            slippage + 1 bp spread
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
              disabled={busy || !dataset}
              onClick={() =>
                action(async () =>
                  setBars(
                    await api(
                      `market/${dataset}?symbol=${encodeURIComponent(symbols.trim().toUpperCase())}`,
                    ),
                  ),
                )
              }
            >
              Load market data
            </button>
          </div>
          <MarketPlot bars={bars} />
          <details className="panel">
            <summary>OHLCV and indicators</summary>
            <Table rows={bars.slice(-100)} />
          </details>
        </section>
      )}
      {tab === "Experiments" && (
        <section className="panel">
          <h2>Experiment history</h2>
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
                    <td>{e.created_at.slice(0, 16)}</td>
                    <td>
                      {e.kind} / {e.config.strategy}
                    </td>
                    <td title={e.error || undefined}>{e.status}</td>
                    <td>{e.config.symbols.join(", ")}</td>
                    <td>
                      <button
                        disabled={busy || e.status !== "SUCCEEDED"}
                        onClick={() =>
                          action(async () => {
                            const r = await api(`experiments/${e.id}`);
                            setResult({ ...r.result, id: e.id });
                            setTab(
                              e.kind === "ml" ? "ML research" : "Research",
                            );
                          })
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
            disabled={busy || !dataset}
            onClick={() =>
              action(async () => {
                await api("paper", request);
              })
            }
          >
            Create paper account
          </button>
          {papers.map((p) => (
            <article className="paper" key={p.id}>
              <code>{p.id}</code>
              <p>
                Last session: {p.state.last_session || "Not started"} · Equity:{" "}
                {p.state.account?.equity.toLocaleString() || "—"}
              </p>
              <p>{p.state.alerts.join(" · ")}</p>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const form = new FormData(e.currentTarget);
                  action(async () => {
                    await api(`paper/${p.id}/advance`, {
                      as_of: form.get("date"),
                    });
                  });
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
                <button disabled={busy}>Advance ledger</button>
              </form>
            </article>
          ))}
        </section>
      )}
      {result && (tab === "Research" || tab === "ML research") && (
        <>
          <div className="result-heading">
            <h2>Research result</h2>
            <button onClick={exportResult}>Export JSON ↓</button>
          </div>
          <p className="source">
            {result.provenance?.provider} · Dataset{" "}
            {result.provenance?.dataset_id.slice(0, 12)} · {result.id}
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
                ["Trades", String(metrics.number_of_trades)],
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
                title="Drawdown"
                rows={result.simulation.equity.map((r, i) => ({
                  ...r,
                  equity: ((metrics?.drawdown as number[])?.[i] || 0) * 100,
                }))}
              />
              <section className="panel">
                <h2>Monthly returns</h2>
                <div className="heatmap">
                  {Object.entries(
                    (metrics?.monthly_returns || {}) as Record<string, number>,
                  ).map(([m, v]) => (
                    <div
                      key={m}
                      style={{
                        background:
                          v >= 0
                            ? `rgba(80,170,115,${Math.min(0.8, 0.12 + Math.abs(v) * 8)})`
                            : `rgba(210,90,90,${Math.min(0.8, 0.12 + Math.abs(v) * 8)})`,
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
                    .map(([metric, value]) => ({ metric, value }))}
                />
              </details>
              <details className="panel">
                <summary>Execution ledger</summary>
                <Table rows={result.simulation.fills} />
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
