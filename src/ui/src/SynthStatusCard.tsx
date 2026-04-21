import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { useTheme } from "./ThemeContext";
import { Cpu, Timer, CheckCircle2, AlertTriangle } from "lucide-react";

export interface SynthReport {
  utilisation: {
    top_module: string;
    total_luts: number;
    logic_luts: number;
    ffs: number;
    rams_36: number;
    rams_18: number;
    urams: number;
    dsps: number;
  };
  timing: {
    wns_ns: number;
    tns_ns: number;
    failing_endpoints: number;
    total_endpoints: number;
    is_timing_met: boolean;
    worst_clock: string;
  };
  device: string;
}

/** Mirrors `pccx_core::vivado_timing::TimingReport` across the Tauri bridge.
 *  UG906 design-timing-summary + UG949 per-clock breakdown. */
export interface TimingReport {
  wns_ns:             number;
  tns_ns:             number;
  failing_endpoints:  number;
  clock_domains:      ClockDomain[];
}

export interface ClockDomain {
  name:       string;
  wns_ns:     number;
  tns_ns:     number;
  period_ns:  number;
}

interface Props {
  utilizationPath: string;
  timingPath: string;
  autoLoad?: boolean;
}

type Status =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; report: SynthReport }
  | { kind: "error"; message: string };

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

function Stat({ label, value, theme }: { label: string; value: number | string; theme: ReturnType<typeof useTheme> }) {
  return (
    <div
      className="flex flex-col items-center justify-center px-3 py-2 rounded"
      style={{ background: theme.bg, border: `1px solid ${theme.border}` }}
    >
      <span style={{ fontSize: 10, color: theme.textMuted, letterSpacing: 0.5 }}>{label}</span>
      <span style={{ fontSize: 15, fontWeight: 700, color: theme.text, marginTop: 2 }}>{value}</span>
    </div>
  );
}

export function SynthStatusCard({ utilizationPath, timingPath, autoLoad = true }: Props) {
  const theme = useTheme();
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  // Dim-6 signoff panel: `load_timing_report` yields `TimingReport`
  // in the same card.  Shared `err` collapses both IPC error branches.
  const [timing, setTiming] = useState<TimingReport | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = async () => {
    setStatus({ kind: "loading" });
    setErr(null);
    try {
      const report = await tauriInvoke<SynthReport>("load_synth_report", {
        utilizationPath,
        timingPath,
      });
      setStatus({ kind: "ok", report });
    } catch (e) {
      setStatus({ kind: "error", message: String(e) });
      setErr(String(e));
    }
  };

  useEffect(() => {
    if (autoLoad) {
      void load();
    }
  }, [utilizationPath, timingPath, autoLoad]);

  // UG906 structured timing: parses `report_timing_summary` text via
  // `pccx_core::vivado_timing::parse_timing_report` on the Rust side.
  useEffect(() => {
    if (!autoLoad || !timingPath) return;
    let cancelled = false;
    (async () => {
      try {
        const t = await invoke<TimingReport>("load_timing_report", {
          path: timingPath,
        });
        if (!cancelled) setTiming(t);
      } catch (e) {
        if (!cancelled) {
          setTiming(null);
          setErr(String(e));
        }
      }
    })();
    return () => { cancelled = true; };
  }, [timingPath, autoLoad]);

  return (
    <div
      className="flex flex-col gap-3 p-4 rounded-md"
      style={{ background: theme.bgSurface, border: `1px solid ${theme.border}`, minWidth: 320 }}
    >
      <div className="flex items-center gap-2">
        <Cpu size={16} style={{ color: theme.accent }} />
        <span style={{ fontWeight: 600, fontSize: 13 }}>Synthesis Status</span>
        <div className="ml-auto">
          <button
            onClick={load}
            disabled={status.kind === "loading"}
            className="px-2 py-0.5 text-[11px] rounded"
            style={{
              background: theme.accentBg,
              color: theme.accent,
              border: `1px solid ${theme.border}`,
              cursor: status.kind === "loading" ? "wait" : "pointer",
            }}
          >
            {status.kind === "loading" ? "Loading…" : "Reload"}
          </button>
        </div>
      </div>

      {status.kind === "idle" && (
        <div style={{ fontSize: 12, color: theme.textMuted }}>Not loaded.</div>
      )}

      {status.kind === "loading" && (
        <div style={{ fontSize: 12, color: theme.textMuted }}>Loading synth reports…</div>
      )}

      {status.kind === "error" && (
        <div className="flex items-start gap-2" style={{ fontSize: 12 }}>
          <AlertTriangle size={14} style={{ color: theme.error, marginTop: 2 }} />
          <span style={{ color: theme.error }}>{err ?? status.message}</span>
        </div>
      )}

      {status.kind === "ok" && (
        <>
          <div className="flex items-center gap-2" style={{ fontSize: 11, color: theme.textMuted }}>
            <span>Top: <strong style={{ color: theme.text }}>{status.report.utilisation.top_module}</strong></span>
            <span>·</span>
            <span>Device: <strong style={{ color: theme.text }}>{status.report.device || "—"}</strong></span>
          </div>

          <div className="grid grid-cols-4 gap-2">
            <Stat label="LUT"     value={status.report.utilisation.total_luts} theme={theme} />
            <Stat label="FF"      value={status.report.utilisation.ffs}        theme={theme} />
            <Stat label="RAMB36"  value={status.report.utilisation.rams_36}    theme={theme} />
            <Stat label="RAMB18"  value={status.report.utilisation.rams_18}    theme={theme} />
            <Stat label="URAM"    value={status.report.utilisation.urams}      theme={theme} />
            <Stat label="DSP"     value={status.report.utilisation.dsps}       theme={theme} />
            <Stat label="Logic"   value={status.report.utilisation.logic_luts} theme={theme} />
            <Stat label="Endpoints" value={status.report.timing.total_endpoints} theme={theme} />
          </div>

          <div
            className="flex items-center gap-2 px-3 py-2 rounded"
            style={{
              background: status.report.timing.is_timing_met
                ? "rgba(78,200,107,0.10)"
                : "rgba(241,76,76,0.12)",
              border: `1px solid ${status.report.timing.is_timing_met ? theme.success : theme.error}`,
            }}
          >
            {status.report.timing.is_timing_met ? (
              <CheckCircle2 size={16} style={{ color: theme.success }} />
            ) : (
              <AlertTriangle size={16} style={{ color: theme.error }} />
            )}
            <span style={{ fontSize: 12, fontWeight: 600, color: theme.text }}>
              {status.report.timing.is_timing_met ? "Timing met" : "Timing NOT met"}
            </span>
            <span className="ml-auto" style={{ fontSize: 11, color: theme.textMuted }}>
              <Timer size={10} className="inline mr-1" />
              WNS {status.report.timing.wns_ns.toFixed(3)} ns
              {status.report.timing.worst_clock && ` on ${status.report.timing.worst_clock}`}
              {!status.report.timing.is_timing_met &&
                ` · ${status.report.timing.failing_endpoints} failing`}
            </span>
          </div>
        </>
      )}

      {/* UG949 §4 timing-summary grouping — structured TimingReport from
          `load_timing_report` (Dim-6 signoff).  Negative WNS/TNS renders
          in theme.error per PrimeTime convention. */}
      {timing && (
        <div
          className="flex flex-col gap-2 pt-2"
          style={{ borderTop: `1px solid ${theme.border}` }}
        >
          <div className="flex items-center gap-2" style={{ fontSize: 11, color: theme.textMuted }}>
            <Timer size={12} style={{ color: theme.accent }} />
            <strong style={{ color: theme.text, fontSize: 12 }}>Timing Report</strong>
            <span className="ml-auto">
              <span style={{ color: timing.wns_ns < 0 ? theme.error : theme.success, fontWeight: 600 }}>
                WNS {timing.wns_ns.toFixed(3)} ns
              </span>
              <span style={{ margin: "0 6px", color: theme.textFaint }}>·</span>
              <span style={{ color: timing.tns_ns < 0 ? theme.error : theme.success, fontWeight: 600 }}>
                TNS {timing.tns_ns.toFixed(3)} ns
              </span>
              <span style={{ margin: "0 6px", color: theme.textFaint }}>·</span>
              <span style={{ color: timing.failing_endpoints > 0 ? theme.error : theme.textMuted }}>
                {timing.failing_endpoints} failing
              </span>
            </span>
          </div>
          {timing.clock_domains.length > 0 && (
            <table style={{ fontSize: 11, width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ color: theme.textMuted, textAlign: "left" }}>
                  <th style={{ padding: "2px 6px", fontWeight: 500 }}>Clock</th>
                  <th style={{ padding: "2px 6px", fontWeight: 500, textAlign: "right" }}>Period</th>
                  <th style={{ padding: "2px 6px", fontWeight: 500, textAlign: "right" }}>WNS</th>
                  <th style={{ padding: "2px 6px", fontWeight: 500, textAlign: "right" }}>TNS</th>
                </tr>
              </thead>
              <tbody>
                {timing.clock_domains.map(c => (
                  <tr key={c.name} style={{ borderTop: `1px solid ${theme.borderDim}` }}>
                    <td style={{ padding: "2px 6px", color: theme.text }}>{c.name}</td>
                    <td style={{ padding: "2px 6px", textAlign: "right", color: theme.textDim }}>
                      {c.period_ns.toFixed(3)} ns
                    </td>
                    <td style={{ padding: "2px 6px", textAlign: "right",
                                  color: c.wns_ns < 0 ? theme.error : theme.textDim }}>
                      {c.wns_ns.toFixed(3)}
                    </td>
                    <td style={{ padding: "2px 6px", textAlign: "right",
                                  color: c.tns_ns < 0 ? theme.error : theme.textDim }}>
                      {c.tns_ns.toFixed(3)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
