import { useState } from "react";
import { useTheme } from "./ThemeContext";
import { PlayCircle, CheckCircle2, XCircle, Loader2, ExternalLink, Wand2, FileText } from "lucide-react";

// ─── Types mirroring Rust IPC structs ────────────────────────────────────────

interface TbResult {
  name: string;
  verdict: "PASS" | "FAIL";
  cycles: number;
  pccx_path: string | null;
}

interface VerificationSummary {
  testbenches: TbResult[];
  synth_timing_met: boolean | null;
  synth_status: string;
  stdout: string;
}

interface MetricDiff {
  name: string;
  observed: number;
  expected: number;
  tolerance_pct: number;
  pass: boolean;
}

interface StepDiff {
  step: number;
  is_pass: boolean;
  summary: string;
  metrics: MetricDiff[];
}

interface GoldenDiffReport {
  step_count: number;
  pass_count: number;
  steps: StepDiff[];
  summary: string;
  total_metrics: number;
  exact_matches: number;
  tolerance_passes: number;
  metric_mismatches: number;
}

interface SanitizeResult {
  cleaned: string;
  fixups: string[];
}

// ─── IPC shim (matches VerificationRunner convention) ────────────────────────

function tauriInvoke<T>(cmd: string, args: Record<string, unknown>): Promise<T> {
  const w = window as unknown as {
    __TAURI__?: {
      core?: { invoke?: (cmd: string, args: Record<string, unknown>) => Promise<T> };
      invoke?: (cmd: string, args: Record<string, unknown>) => Promise<T>;
    };
  };
  const bridge = w.__TAURI__?.core?.invoke ?? w.__TAURI__?.invoke;
  if (!bridge) {
    return Promise.reject(new Error("Tauri IPC not available (browser-only build)"));
  }
  return bridge(cmd, args);
}

// ─── State types ─────────────────────────────────────────────────────────────

type RunState =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "ok"; summary: VerificationSummary }
  | { kind: "error"; message: string };

type DiffState =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "ok"; report: GoldenDiffReport }
  | { kind: "error"; message: string };

type SanitizeState =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "ok"; result: SanitizeResult }
  | { kind: "error"; message: string };

interface Props {
  repoPath: string;
}

// ─── VerificationRunner ───────────────────────────────────────────────────────

export function VerificationRunner({ repoPath }: Props) {
  const theme = useTheme();
  const [state, setState] = useState<RunState>({ kind: "idle" });
  const [lastOpened, setLastOpened] = useState<string | null>(null);

  const run = async () => {
    setState({ kind: "running" });
    try {
      const summary = await tauriInvoke<VerificationSummary>("run_verification", { repoPath });
      setState({ kind: "ok", summary });
    } catch (err) {
      setState({ kind: "error", message: String(err) });
    }
  };

  const openInTimeline = async (path: string) => {
    try {
      await tauriInvoke("load_pccx", { path });
      setLastOpened(path);
    } catch (err) {
      console.error("load_pccx failed", err);
    }
  };

  const isRunning = state.kind === "running";
  const passCount = state.kind === "ok"
    ? state.summary.testbenches.filter(t => t.verdict === "PASS").length
    : 0;
  const failCount = state.kind === "ok"
    ? state.summary.testbenches.filter(t => t.verdict === "FAIL").length
    : 0;
  const allPassed = state.kind === "ok" && failCount === 0 && passCount > 0;

  return (
    <div
      className="flex flex-col gap-3 p-4 rounded-md"
      style={{ background: theme.bgSurface, border: `0.5px solid ${theme.borderSubtle}`, minWidth: 320 }}
    >
      <div className="flex items-center gap-2">
        <PlayCircle size={16} style={{ color: theme.accent }} />
        <span style={{ fontWeight: 600, fontSize: 13 }}>Run Verification Suite</span>
        <div className="ml-auto">
          <button
            onClick={run}
            disabled={isRunning}
            className="flex items-center gap-2 px-3 py-1 text-[11px] rounded font-semibold"
            style={{
              background: isRunning ? theme.bgHover : theme.success,
              color: isRunning ? theme.textMuted : "#ffffff",
              cursor: isRunning ? "wait" : "pointer",
              border: "none",
            }}
          >
            {isRunning
              ? (<><Loader2 size={12} className="animate-spin" /> Running…</>)
              : (<><PlayCircle size={12} /> Run</>)}
          </button>
        </div>
      </div>

      <p style={{ fontSize: 11, color: theme.textMuted }}>
        Executes <code>hw/sim/run_verification.sh</code> in
        <code style={{ marginLeft: 4 }}>{repoPath}</code>
        and parses the emitted PASS / FAIL lines plus the synth verdict.
      </p>

      {state.kind === "error" && (
        <div
          className="px-3 py-2 rounded"
          style={{
            background: "rgba(241,76,76,0.12)",
            border: `0.5px solid ${theme.error}`,
            color: theme.text,
            fontSize: 12,
          }}
        >
          <strong>Error:</strong> {state.message}
        </div>
      )}

      {state.kind === "ok" && (
        <>
          <div
            className="flex items-center gap-2 px-3 py-2 rounded"
            style={{
              background: allPassed
                ? "rgba(78,200,107,0.10)"
                : "rgba(241,76,76,0.12)",
              border: `0.5px solid ${allPassed ? theme.success : theme.error}`,
            }}
          >
            {allPassed
              ? <CheckCircle2 size={14} style={{ color: theme.success }} />
              : <XCircle size={14} style={{ color: theme.error }} />}
            <span style={{ fontSize: 12, fontWeight: 600 }}>
              {passCount} pass / {failCount} fail ({state.summary.testbenches.length} testbenches)
            </span>
            <span className="ml-auto" style={{ fontSize: 11, color: theme.textMuted }}>
              Synth: {state.summary.synth_timing_met === true
                ? "met"
                : state.summary.synth_timing_met === false
                  ? "NOT met"
                  : "—"}
            </span>
          </div>

          <table style={{ fontSize: 11, width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{
                color: theme.textMuted,
                borderBottom: `0.5px solid ${theme.borderSubtle}`,
              }}>
                <th className="p-1 text-left">Testbench</th>
                <th className="p-1 text-right">Cycles</th>
                <th className="p-1 text-center">Status</th>
                <th className="p-1 text-center">Trace</th>
              </tr>
            </thead>
            <tbody>
              {state.summary.testbenches.map((tb) => (
                <tr key={tb.name} style={{ borderBottom: `0.5px solid ${theme.borderSubtle}` }}>
                  <td className="p-1 font-mono" style={{ color: theme.text }}>{tb.name}</td>
                  <td className="p-1 text-right">{tb.cycles.toLocaleString()}</td>
                  <td className="p-1 text-center">
                    <span
                      className="px-2 py-0.5 rounded text-[10px] font-bold"
                      style={{
                        color: tb.verdict === "PASS" ? theme.success : theme.error,
                        border: `0.5px solid ${tb.verdict === "PASS" ? theme.success : theme.error}`,
                      }}
                    >
                      {tb.verdict}
                    </span>
                  </td>
                  <td className="p-1 text-center">
                    {tb.pccx_path ? (
                      <button
                        onClick={() => openInTimeline(tb.pccx_path!)}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px]"
                        style={{
                          color: lastOpened === tb.pccx_path ? theme.success : theme.accent,
                          border: `0.5px solid ${lastOpened === tb.pccx_path ? theme.success : theme.accent}`,
                          background: "transparent",
                          cursor: "pointer",
                        }}
                        title={`Load ${tb.pccx_path} into Timeline`}
                      >
                        <ExternalLink size={10} />
                        {lastOpened === tb.pccx_path ? "Loaded" : "Open"}
                      </button>
                    ) : (
                      <span style={{ color: theme.textMuted }}>—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

// ─── GoldenDiffCard ───────────────────────────────────────────────────────────

export function GoldenDiffCard() {
  const theme = useTheme();
  const [expectedPath, setExpectedPath] = useState("");
  const [actualPath, setActualPath] = useState("");
  const [diffState, setDiffState] = useState<DiffState>({ kind: "idle" });
  const [markdownState, setMarkdownState] = useState<"idle" | "loading" | "ok" | "error">("idle");
  const [markdown, setMarkdown] = useState("");
  const [showMarkdown, setShowMarkdown] = useState(false);
  const [expandFailed, setExpandFailed] = useState(false);

  const runDiff = async () => {
    if (!expectedPath || !actualPath) return;
    setDiffState({ kind: "running" });
    setShowMarkdown(false);
    try {
      const report = await tauriInvoke<GoldenDiffReport>("verify_golden_diff", {
        expectedPath,
        actualPath,
      });
      setDiffState({ kind: "ok", report });
    } catch (err) {
      setDiffState({ kind: "error", message: String(err) });
    }
  };

  const fetchMarkdown = async () => {
    if (diffState.kind !== "ok") return;
    setMarkdownState("loading");
    try {
      const md = await tauriInvoke<string>("verify_report", {
        report: diffState.report,
      });
      setMarkdown(md);
      setMarkdownState("ok");
      setShowMarkdown(true);
    } catch (err) {
      setMarkdownState("error");
      console.error("verify_report failed", err);
    }
  };

  const isRunning = diffState.kind === "running";
  const report = diffState.kind === "ok" ? diffState.report : null;
  const allPass = report ? report.pass_count === report.step_count : false;
  const failedSteps = report ? report.steps.filter(s => !s.is_pass) : [];

  return (
    <div
      className="flex flex-col gap-3 p-4 rounded-md"
      style={{ background: theme.bgSurface, border: `0.5px solid ${theme.borderSubtle}` }}
    >
      <div className="flex items-center gap-2">
        <CheckCircle2 size={16} style={{ color: theme.accent }} />
        <span style={{ fontWeight: 600, fontSize: 13 }}>Golden Diff</span>
      </div>

      <p style={{ fontSize: 11, color: theme.textMuted }}>
        Compares a <code>.ref.jsonl</code> reference profile against a <code>.pccx</code> trace.
      </p>

      <div className="flex flex-col gap-2">
        <div className="flex flex-col gap-1">
          <label style={{ fontSize: 10, color: theme.textMuted, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Reference profile (.ref.jsonl)
          </label>
          <input
            type="text"
            value={expectedPath}
            onChange={e => setExpectedPath(e.target.value)}
            placeholder="path/to/golden.ref.jsonl"
            style={{
              background: theme.bg,
              color: theme.text,
              border: `0.5px solid ${theme.borderSubtle}`,
              borderRadius: 4,
              padding: "5px 8px",
              fontSize: 11,
              fontFamily: "ui-monospace, monospace",
            }}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label style={{ fontSize: 10, color: theme.textMuted, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Actual trace (.pccx)
          </label>
          <input
            type="text"
            value={actualPath}
            onChange={e => setActualPath(e.target.value)}
            placeholder="path/to/capture.pccx"
            style={{
              background: theme.bg,
              color: theme.text,
              border: `0.5px solid ${theme.borderSubtle}`,
              borderRadius: 4,
              padding: "5px 8px",
              fontSize: 11,
              fontFamily: "ui-monospace, monospace",
            }}
          />
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={runDiff}
          disabled={isRunning || !expectedPath || !actualPath}
          className="flex items-center gap-1.5 px-3 py-1 rounded text-[11px] font-semibold"
          style={{
            background: isRunning || !expectedPath || !actualPath ? theme.bgHover : theme.accent,
            color: isRunning || !expectedPath || !actualPath ? theme.textMuted : "#ffffff",
            cursor: isRunning || !expectedPath || !actualPath ? "default" : "pointer",
            border: "none",
          }}
        >
          {isRunning
            ? <><Loader2 size={11} className="animate-spin" /> Running…</>
            : <><PlayCircle size={11} /> Run Diff</>}
        </button>
        {diffState.kind === "ok" && (
          <button
            onClick={fetchMarkdown}
            disabled={markdownState === "loading"}
            className="flex items-center gap-1.5 px-3 py-1 rounded text-[11px] font-semibold"
            style={{
              background: "transparent",
              color: theme.accent,
              border: `0.5px solid ${theme.accent}`,
              cursor: markdownState === "loading" ? "wait" : "pointer",
            }}
          >
            <FileText size={11} />
            {markdownState === "loading" ? "Generating…" : "Markdown report"}
          </button>
        )}
      </div>

      {diffState.kind === "error" && (
        <div
          className="px-3 py-2 rounded text-xs"
          style={{ background: "rgba(241,76,76,0.12)", border: `0.5px solid ${theme.error}`, color: theme.text }}
        >
          <strong>Error:</strong> {diffState.message}
        </div>
      )}

      {report && (
        <>
          {/* Summary banner */}
          <div
            className="flex items-center gap-2 px-3 py-2 rounded"
            style={{
              background: allPass ? "rgba(78,200,107,0.10)" : "rgba(241,76,76,0.12)",
              border: `0.5px solid ${allPass ? theme.success : theme.error}`,
            }}
          >
            {allPass
              ? <CheckCircle2 size={14} style={{ color: theme.success }} />
              : <XCircle size={14} style={{ color: theme.error }} />}
            <span style={{ fontSize: 12, fontWeight: 600 }}>{report.summary}</span>
          </div>

          {/* Metric statistics */}
          <div className="grid grid-cols-4 gap-2">
            {[
              { label: "total",   value: String(report.total_metrics) },
              { label: "exact",   value: String(report.exact_matches) },
              { label: "tol",     value: String(report.tolerance_passes) },
              { label: "fail",    value: String(report.metric_mismatches) },
            ].map(s => (
              <div
                key={s.label}
                style={{ padding: "8px 10px", background: theme.bgPanel, borderRadius: 4, border: `0.5px solid ${theme.borderSubtle}` }}
              >
                <div style={{ fontSize: 9, color: theme.textMuted, textTransform: "uppercase", letterSpacing: "0.05em" }}>{s.label}</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: theme.text, marginTop: 2, fontFamily: "ui-monospace, monospace" }}>{s.value}</div>
              </div>
            ))}
          </div>

          {/* Failing steps */}
          {failedSteps.length > 0 && (
            <div>
              <button
                onClick={() => setExpandFailed(v => !v)}
                className="flex items-center gap-1 text-[11px]"
                style={{ color: theme.error, background: "transparent", border: "none", cursor: "pointer", padding: 0 }}
              >
                <XCircle size={11} />
                {expandFailed ? "Hide" : "Show"} {failedSteps.length} failing step{failedSteps.length !== 1 ? "s" : ""}
              </button>
              {expandFailed && (
                <table style={{ fontSize: 11, width: "100%", borderCollapse: "collapse", marginTop: 6 }}>
                  <thead>
                    <tr style={{ color: theme.textMuted, borderBottom: `0.5px solid ${theme.borderSubtle}` }}>
                      <th className="p-1 text-right">Step</th>
                      <th className="p-1 text-left">Metric</th>
                      <th className="p-1 text-right">Observed</th>
                      <th className="p-1 text-right">Expected</th>
                      <th className="p-1 text-right">Tol %</th>
                    </tr>
                  </thead>
                  <tbody>
                    {failedSteps.flatMap(step =>
                      step.metrics
                        .filter(m => !m.pass)
                        .map(m => (
                          <tr
                            key={`${step.step}-${m.name}`}
                            style={{ borderBottom: `0.5px solid ${theme.borderSubtle}` }}
                          >
                            <td className="p-1 text-right font-mono" style={{ color: theme.textMuted }}>{step.step}</td>
                            <td className="p-1 font-mono" style={{ color: theme.error }}>{m.name}</td>
                            <td className="p-1 text-right font-mono">{m.observed.toLocaleString()}</td>
                            <td className="p-1 text-right font-mono">{m.expected.toLocaleString()}</td>
                            <td className="p-1 text-right font-mono">{m.tolerance_pct.toFixed(1)}</td>
                          </tr>
                        ))
                    )}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {/* Markdown report panel */}
          {showMarkdown && markdown && (
            <div
              className="rounded p-3 overflow-auto"
              style={{
                background: theme.bg,
                border: `0.5px solid ${theme.borderSubtle}`,
                maxHeight: 240,
                fontSize: 11,
                fontFamily: "ui-monospace, monospace",
                color: theme.textDim,
                whiteSpace: "pre-wrap",
              }}
            >
              {markdown}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ─── SanitizeCard ─────────────────────────────────────────────────────────────

export function SanitizeCard() {
  const theme = useTheme();
  const [input, setInput] = useState("");
  const [sanState, setSanState] = useState<SanitizeState>({ kind: "idle" });

  const runSanitize = async () => {
    if (!input.trim()) return;
    setSanState({ kind: "running" });
    try {
      const result = await tauriInvoke<SanitizeResult>("verify_sanitize", { content: input });
      setSanState({ kind: "ok", result });
    } catch (err) {
      setSanState({ kind: "error", message: String(err) });
    }
  };

  const isRunning = sanState.kind === "running";

  return (
    <div
      className="flex flex-col gap-3 p-4 rounded-md"
      style={{ background: theme.bgSurface, border: `0.5px solid ${theme.borderSubtle}` }}
    >
      <div className="flex items-center gap-2">
        <Wand2 size={16} style={{ color: theme.accent }} />
        <span style={{ fontWeight: 600, fontSize: 13 }}>Robust Sanitizer</span>
      </div>

      <p style={{ fontSize: 11, color: theme.textMuted }}>
        Strips NUL bytes, normalises line endings, and forgives trailing commas.
        Paste TOML / JSON content to sanitize.
      </p>

      <textarea
        value={input}
        onChange={e => setInput(e.target.value)}
        rows={5}
        placeholder={'{"key": "value",}\n'}
        style={{
          background: theme.bg,
          color: theme.text,
          border: `0.5px solid ${theme.borderSubtle}`,
          borderRadius: 4,
          padding: "6px 8px",
          fontSize: 11,
          fontFamily: "ui-monospace, monospace",
          resize: "vertical",
        }}
      />

      <div>
        <button
          onClick={runSanitize}
          disabled={isRunning || !input.trim()}
          className="flex items-center gap-1.5 px-3 py-1 rounded text-[11px] font-semibold"
          style={{
            background: isRunning || !input.trim() ? theme.bgHover : theme.accent,
            color: isRunning || !input.trim() ? theme.textMuted : "#ffffff",
            cursor: isRunning || !input.trim() ? "default" : "pointer",
            border: "none",
          }}
        >
          {isRunning
            ? <><Loader2 size={11} className="animate-spin" /> Sanitizing…</>
            : <><Wand2 size={11} /> Sanitize</>}
        </button>
      </div>

      {sanState.kind === "error" && (
        <div className="px-3 py-2 rounded text-xs"
          style={{ background: "rgba(241,76,76,0.12)", border: `0.5px solid ${theme.error}`, color: theme.text }}>
          <strong>Error:</strong> {sanState.message}
        </div>
      )}

      {sanState.kind === "ok" && (
        <div className="flex flex-col gap-2">
          {sanState.result.fixups.length === 0 ? (
            <div className="flex items-center gap-1.5 text-xs" style={{ color: theme.success }}>
              <CheckCircle2 size={12} /> No fixups needed — input is clean.
            </div>
          ) : (
            <div className="flex flex-col gap-1">
              <span style={{ fontSize: 10, color: theme.textMuted, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Applied fixups
              </span>
              {sanState.result.fixups.map((f, i) => (
                <span key={i} className="text-[11px]" style={{ color: theme.warning }}>
                  — {f}
                </span>
              ))}
            </div>
          )}
          <div className="flex flex-col gap-1">
            <span style={{ fontSize: 10, color: theme.textMuted, textTransform: "uppercase", letterSpacing: "0.05em" }}>
              Cleaned output
            </span>
            <pre
              style={{
                background: theme.bg,
                border: `0.5px solid ${theme.borderSubtle}`,
                borderRadius: 4,
                padding: "6px 8px",
                fontSize: 11,
                color: theme.textDim,
                overflowX: "auto",
                maxHeight: 200,
                margin: 0,
              }}
            >
              {sanState.result.cleaned}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
