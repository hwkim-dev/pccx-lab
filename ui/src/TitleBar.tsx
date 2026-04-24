import { getCurrentWindow } from "@tauri-apps/api/window";
import { useTheme } from "./ThemeContext";
import { Play, Pause, Square, StepForward, Sun, Moon } from "lucide-react";

interface TitleBarProps {
  title?: string;
  subtitle?: string;
  children?: React.ReactNode;
  onAction?: (action: string) => void;
}

export function TitleBar({ title = "pccx-lab", subtitle, children, onAction }: TitleBarProps) {
  const theme = useTheme();
  const isDark = theme.mode === "dark";

  const handleMinimize = () => getCurrentWindow().minimize();
  const handleMaximize = () => getCurrentWindow().toggleMaximize();
  const handleClose = () => getCurrentWindow().close();

  const runBtnStyle = (color: string) => ({
    width: 28, height: 28,
    display: "flex" as const, alignItems: "center" as const, justifyContent: "center" as const,
    background: "transparent", border: "none", cursor: "pointer" as const,
    color, borderRadius: 6,
    transition: "all 0.15s cubic-bezier(0.25, 0.1, 0.25, 1)",
  });

  return (
    <div
      data-tauri-drag-region
      className="flex items-center shrink-0 select-none"
      style={{
        height: 38,
        background: theme.bgPanel,
        borderBottom: `0.5px solid ${isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.08)"}`,
      }}
    >
      {/* Left: Traffic lights + Brand */}
      <div data-tauri-drag-region className="flex items-center gap-2.5 pl-3 pr-4" style={{ minWidth: 140 }}>
        <div className="flex items-center gap-1.5">
          <button onClick={handleClose} title="Close"
            className="w-3 h-3 rounded-full transition-opacity hover:opacity-80"
            style={{ background: "#ff5f57", border: "0.5px solid rgba(0,0,0,0.12)" }} />
          <button onClick={handleMinimize} title="Minimize"
            className="w-3 h-3 rounded-full transition-opacity hover:opacity-80"
            style={{ background: "#febc2e", border: "0.5px solid rgba(0,0,0,0.12)" }} />
          <button onClick={handleMaximize} title="Maximize"
            className="w-3 h-3 rounded-full transition-opacity hover:opacity-80"
            style={{ background: "#28c840", border: "0.5px solid rgba(0,0,0,0.12)" }} />
        </div>
        <div className="flex items-center gap-1.5 pointer-events-none" data-tauri-drag-region>
          <div className="w-4 h-4 rounded flex items-center justify-center shrink-0"
            style={{
              background: `linear-gradient(135deg, ${theme.accent}, ${theme.accentDim})`,
              borderRadius: 5,
            }}>
            <span style={{ fontSize: 8, fontWeight: 800, color: "#fff" }}>P</span>
          </div>
          <span style={{ fontSize: 12, fontWeight: 600, color: theme.text, letterSpacing: -0.3 }}>{title}</span>
        </div>
      </div>

      {/* Center-left: Menu bar (passed as children) */}
      <div className="flex items-center h-full" data-tauri-drag-region>
        {children}
      </div>

      <div className="flex-1" data-tauri-drag-region />

      {/* Center: Run controls (Xcode pill group) */}
      <div className="flex items-center gap-0.5 px-1 py-1 rounded-lg" style={{
        background: isDark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.03)",
        border: `0.5px solid ${isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)"}`,
      }}>
        <button style={runBtnStyle(theme.success)} onClick={() => onAction?.("run.start")} title="Start (F5)"
          onMouseEnter={e => e.currentTarget.style.background = isDark ? "rgba(78,200,107,0.15)" : "rgba(56,138,52,0.1)"}
          onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
          <Play size={13} fill="currentColor" />
        </button>
        <button style={runBtnStyle(theme.warning)} onClick={() => onAction?.("run.pause")} title="Pause (F7)"
          onMouseEnter={e => e.currentTarget.style.background = isDark ? "rgba(229,164,0,0.15)" : "rgba(191,136,3,0.1)"}
          onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
          <Pause size={13} />
        </button>
        <button style={runBtnStyle(theme.error)} onClick={() => onAction?.("run.stop")} title="Stop (Shift+F5)"
          onMouseEnter={e => e.currentTarget.style.background = isDark ? "rgba(241,76,76,0.15)" : "rgba(205,49,49,0.1)"}
          onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
          <Square size={11} fill="currentColor" />
        </button>
        <div style={{ width: 1, height: 16, background: isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)", margin: "0 2px" }} />
        <button style={runBtnStyle(theme.info)} onClick={() => onAction?.("run.step")} title="Step (F10)"
          onMouseEnter={e => e.currentTarget.style.background = isDark ? "rgba(55,148,255,0.15)" : "rgba(26,133,255,0.1)"}
          onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
          <StepForward size={13} />
        </button>
      </div>

      {/* Center: Status */}
      <div data-tauri-drag-region className="flex-1 flex items-center justify-center pointer-events-none">
        {subtitle && (
          <span style={{
            fontSize: 11, color: theme.textMuted, fontWeight: 500,
            background: isDark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.03)",
            padding: "2px 10px", borderRadius: 10,
          }}>
            {subtitle}
          </span>
        )}
      </div>

      {/* Right: Theme + Target */}
      <div className="flex items-center gap-2 pr-3">
        <span style={{ fontSize: 10, color: theme.textFaint, fontFamily: theme.fontMono }}>NPU SIM</span>
        <button onClick={theme.toggle} title={isDark ? "Light mode" : "Dark mode"}
          className="w-7 h-7 rounded-lg flex items-center justify-center transition-colors"
          style={{ background: isDark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.04)" }}
          onMouseEnter={e => e.currentTarget.style.background = isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.08)"}
          onMouseLeave={e => e.currentTarget.style.background = isDark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.04)"}>
          {isDark ? <Sun size={13} color="#e5a400" /> : <Moon size={13} color="#717171" />}
        </button>
      </div>
    </div>
  );
}
