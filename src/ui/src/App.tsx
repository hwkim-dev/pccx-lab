import { useState, useEffect, useRef } from "react";
import { invoke } from "@tauri-apps/api/core";
import { emit } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { resolveResource } from "@tauri-apps/api/path";
import { Group, Panel, Separator } from "react-resizable-panels";

import { ThemeProvider, useTheme } from "./ThemeContext";
import { I18nProvider, useI18n } from "./i18n";
import { TitleBar }          from "./TitleBar";
import { MenuBar }           from "./MenuBar";
import { MainToolbar }       from "./MainToolbar";
import { StatusBar }         from "./StatusBar";
import { CanvasView }        from "./CanvasView";
import { NodeEditor }        from "./NodeEditor";
import { Timeline }          from "./Timeline";
import { CommandPalette }    from "./CommandPalette";
import { FlameGraph }        from "./FlameGraph";
import { ExtensionManager }  from "./ExtensionManager";
import { CodeEditor }        from "./CodeEditor";
import { ReportBuilder }     from "./ReportBuilder";
import { HardwareVisualizer }from "./HardwareVisualizer";
import { MemoryDump }        from "./MemoryDump";
import { WaveformViewer }    from "./WaveformViewer";
import { VerificationSuite } from "./VerificationSuite";
import { Roofline }          from "./Roofline";
import { BottomPanel }       from "./BottomPanel";
import { ScenarioFlow }      from "./ScenarioFlow";
import { TestbenchAuthor }   from "./TestbenchAuthor";
import { ShortcutHelp, useShortcutHelp } from "./useShortcuts";

import { Badge, Button, Flex, TextField } from "@radix-ui/themes";
import {
  LayoutDashboard, BrainCircuit, Activity,
  Settings2, Zap, MessageSquare, Clock, FileText,
  Code2, Sun, Moon, Box, Layers, Database, Cpu, ActivitySquare,
  PanelLeftClose, PanelRightClose, PanelBottomClose, CheckCircle, PieChart
} from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────

type ActiveTab = "timeline" | "flamegraph" | "hardware" | "memory" | "waves" | "nodes" | "canvas" | "code" | "report" | "extensions" | "verify" | "roofline" | "scenario" | "tb_author";

interface ChatMessage { role: "system" | "user" | "ai"; content: string; }

const TABS: { id: ActiveTab; label: string; icon: React.ReactNode }[] = [
  { id: "scenario",   label: "Scenario Flow",    icon: <Zap size={12} />             },
  { id: "timeline",   label: "Timeline",         icon: <Clock size={12} />           },
  { id: "flamegraph", label: "Flame Graph",      icon: <Layers size={12} />          },
  { id: "waves",      label: "Waveform",         icon: <ActivitySquare size={12} />  },
  { id: "hardware",   label: "System Simulator", icon: <Cpu size={12} />             },
  { id: "memory",     label: "Memory Dump",      icon: <Database size={12} />        },
  { id: "nodes",      label: "Data Flow",        icon: <Activity size={12} />        },
  { id: "code",       label: "SV Editor",        icon: <Code2 size={12} />           },
  { id: "tb_author",  label: "TB Author",        icon: <LayoutDashboard size={12} /> },
  { id: "report",     label: "Report",           icon: <FileText size={12} />        },
  { id: "canvas",     label: "3D View",          icon: <Box size={12} />             },
  { id: "extensions", label: "Extensions",       icon: <Settings2 size={12} />       },
  { id: "verify",     label: "Verification",     icon: <CheckCircle size={12} />     },
  { id: "roofline",   label: "Roofline",         icon: <PieChart size={12} />        },
];

// ─── Resize Handle ────────────────────────────────────────────────────────────

function ResizeHandle({ direction = "horizontal" }: { direction?: "horizontal" | "vertical" }) {
  const theme = useTheme();
  return (
    <Separator
      className={`group relative ${direction === "vertical" ? "h-[6px]" : "w-[6px]"} flex items-center justify-center hover:bg-[var(--accent)]`}
      style={{ background: theme.borderDim, ["--accent" as any]: theme.accent, cursor: direction === "vertical" ? "row-resize" : "col-resize" }}
    >
      <div
        className="transition-all group-hover:bg-white"
        style={{
          ...(direction === "vertical"
            ? { width: 40, height: 3, borderRadius: 2 }
            : { height: 40, width: 3, borderRadius: 2 }),
          background: theme.textFaint,
        }}
      />
    </Separator>
  );
}

// ─── Inner App (needs ThemeContext) ────────────────────────────────────────────

function AppInner() {
  const theme = useTheme();
  const { t } = useI18n();
  const isDark = theme.mode === "dark";
  const [header, setHeader]       = useState<any>(null);
  const [license, setLicense]     = useState("");
  const [activeTab, setActiveTab] = useState<ActiveTab>("timeline");
  const [traceLoaded, setTraceLoaded] = useState(false);
  const [copilotVisible, setCopilotVisible] = useState(true);
  const [copilotDock, setCopilotDock]       = useState<"left" | "right" | "bottom">(() => (localStorage.getItem("pccx-copilot-dock") as any) || "right");
  const [bottomVisible, setBottomVisible]   = useState(true);
  const [bottomDock, setBottomDock]         = useState<"left" | "right" | "bottom">(() => (localStorage.getItem("pccx-bottom-dock") as any) || "bottom");
  const [cmdPaletteOpen, setCmdPaletteOpen] = useState(false);
  const shortcutHelp = useShortcutHelp();

  // Persist dock choices
  useEffect(() => { localStorage.setItem("pccx-copilot-dock", copilotDock); }, [copilotDock]);
  useEffect(() => { localStorage.setItem("pccx-bottom-dock",  bottomDock);  }, [bottomDock]);

  const dockBtn = (active: boolean) => ({
    padding: 3, borderRadius: 3, cursor: "pointer",
    background: active ? theme.accentBg : "transparent",
    color: active ? theme.accent : theme.textMuted,
    border: "none", display: "inline-flex" as const, alignItems: "center" as const,
  });

  // Copilot Panel Component
  const renderCopilot = () => (
      <div className="w-full h-full flex flex-col min-w-0 min-h-0" style={{ background: theme.bgPanel }}>
        <div className="flex items-center px-3 gap-2 shrink-0" style={{ height: 32, borderBottom: `1px solid ${border}` }}>
          <BrainCircuit size={13} style={{ color: theme.accent }} />
          <span style={{ fontSize: 11, fontWeight: 600, color: theme.textDim }}>AI Copilot</span>
          {copilotBusy && <span style={{ fontSize: 9, color: theme.accent }} className="animate-pulse">thinking…</span>}
          <div className="flex-1" />
          <div className="flex gap-0.5 mr-2" style={{ opacity: 0.7 }}>
             <button aria-label="Dock Copilot left"   onClick={() => setCopilotDock("left")}   title="Dock Left"   style={dockBtn(copilotDock === "left")}  ><PanelLeftClose size={12}/></button>
             <button aria-label="Dock Copilot bottom" onClick={() => setCopilotDock("bottom")} title="Dock Bottom" style={dockBtn(copilotDock === "bottom")}><PanelBottomClose size={12}/></button>
             <button aria-label="Dock Copilot right"  onClick={() => setCopilotDock("right")}  title="Dock Right"  style={dockBtn(copilotDock === "right")} ><PanelRightClose size={12}/></button>
          </div>
          <button aria-label="Close Copilot panel" onClick={() => setCopilotVisible(false)} style={{ fontSize: 11, color: theme.textMuted, cursor: "pointer", padding: "2px 4px" }} title="Close">X</button>
        </div>

        <div className="flex px-3 pb-2 pt-2 gap-2 shrink-0" style={{ borderBottom: `1px solid ${border}`, background: theme.bgHover }}>
          <span style={{ fontSize: 10, color: theme.textDim, whiteSpace: "nowrap", paddingTop: 4 }}>OpenAI Token:</span>
          <input 
             type="password" 
             className="flex-1 bg-black/20 border rounded px-2 outline-none text-xs"
             style={{ borderColor: theme.borderDim, color: theme.text }}
             value={apiKey} 
             onChange={e => { setApiKey(e.target.value); localStorage.setItem("pccx_openai_key", e.target.value); }} 
             placeholder="sk-proj-..." 
          />
        </div>

        <div className="flex-1 overflow-y-auto p-2 flex flex-col gap-2 min-h-0">
          {messages.map((m, i) => (
            <div key={i} style={{
              borderRadius: 8, padding: "8px", fontSize: 11, lineHeight: 1.5,
              wordBreak: "break-word", overflowWrap: "break-word", 
              ...(m.role === "user"
                ? { background: theme.accentBg, border: `1px solid ${theme.accentDim}44`, marginLeft: 16, color: theme.accent }
                : m.role === "ai"
                ? { background: theme.bgSurface, border: `1px solid ${theme.border}`, color: theme.text }
                : { background: "transparent", color: theme.textMuted }),
            }}>
              {m.role === "ai" && <span style={{ color: theme.accent, fontWeight: 600, display: "block", marginBottom: 2 }}>AI:</span>}
              {m.role === "system" && <span style={{ color: theme.textMuted, fontWeight: 600, display: "block", marginBottom: 2 }}>System:</span>}
              {m.content}
            </div>
          ))}
          <div ref={chatEndRef} />
        </div>

        <div className="p-2 shrink-0" style={{ borderTop: `1px solid ${border}` }}>
          <Flex gap="1">
            <TextField.Root placeholder={t("placeholder.ask")} className="flex-1" size="1"
              value={inputText} onChange={e => setInputText(e.target.value)}
              onKeyDown={handleKeyDown} />
            <Button size="1" color="purple" variant="solid"
              disabled={copilotBusy || !inputText.trim()} onClick={handleSend}>→</Button>
          </Flex>
          <div style={{ fontSize: 9, color: theme.textMuted, marginTop: 3 }}>
            {t("copilot.kbdHint")}
          </div>
        </div>
      </div>
  );

  // AI Chat.  Seed with an i18n key instead of a literal so the idle line
  // renders in whatever language is active when the component mounts.
  const [messages, setMessages]   = useState<ChatMessage[]>([
    { role: "system", content: t("copilot.idle") },
  ]);
  const [inputText, setInputText] = useState("");
  const [apiKey, setApiKey] = useState(() => localStorage.getItem("pccx_openai_key") || "");
  const [copilotBusy, setCopilotBusy] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const addMsg = (role: ChatMessage["role"], content: string) =>
    setMessages(p => [...p, { role, content }]);

  useEffect(() => {
    (async () => {
      try {
        // Resolve the bundled dummy trace via Tauri 2.0's path API so
        // it works regardless of the binary's CWD (fixes Round-3 Gap 5:
        // the prior relative path resolved three levels up from the
        // dev binary and never hit the real file, so the UI silently
        // fell back to the Gemma literal flame graph).
        const bundled = await resolveResource("dummy_trace.pccx");
        const res = await invoke("load_pccx", { path: bundled });
        setHeader(res); setTraceLoaded(true);
        const lic: string = await invoke("get_license_info");
        setLicense(lic);
        const ctx: string = await invoke("compress_trace_context");
        addMsg("system", `✓ ${t("copilot.traceLoaded")} ${ctx}`);
      } catch (e) {
        addMsg("system", `⚠ ${t("copilot.traceFailed")}: ${e}`);
      }
    })();
  }, []);

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  // Menu actions
  const handleMenuAction = async (action: string) => {
    const win = getCurrentWindow();
    const tabMap: Record<string, ActiveTab> = {
      "view.canvas": "canvas", "view.nodes": "nodes", "view.timeline": "timeline",
      "view.extensions": "extensions", "view.code": "code", "view.report": "report",
      "view.flamegraph": "flamegraph", "view.hardware": "hardware", "view.memory": "memory",
      "view.waves": "waves", "verify.isa": "verify", "verify.api": "verify", "verify.uvm": "verify", "verify.regression": "verify",
      "analysis.roofline": "roofline",
    };
    if (tabMap[action]) { setActiveTab(tabMap[action]); return; }
    switch (action) {
      case "view.copilot": setCopilotVisible(v => !v); break;
      case "view.bottom":  setBottomVisible(v => !v); break;
      case "view.fullscreen": win.setFullscreen(true); break;
      case "win.minimize": win.minimize(); break;
      case "win.maximize": win.toggleMaximize(); break;
      case "win.close":    win.close(); break;
      case "trace.benchmark": await handleTestIPC(); break;
      case "analysis.pdf": setActiveTab("report"); break;
      case "tools.extensions": setActiveTab("extensions"); break;
      case "tools.uvm": setActiveTab("code"); break;
      case "tools.vcd":
        addMsg("system", "[Export VCD] Attempting .pccx → IEEE 1364 VCD conversion via pccx_core::vcd_writer...");
        try {
          const path: string = await invoke("export_vcd", { outputPath: "pccx_trace.vcd" });
          addMsg("system", `Wrote ${path}. Ready for GTKWave / Surfer / Verdi.`);
        } catch (e) {
          addMsg("system", `Export failed: ${e}. (Load a .pccx file first; vcd_writer needs a cached trace.)`);
        }
        break;
      case "tools.chromeTrace":
        addMsg("system", "[Export Chrome Trace] Serializing to JSON via pccx_core::chrome_trace...");
        try {
          const path: string = await invoke("export_chrome_trace", { outputPath: "trace.json" });
          addMsg("system", `Wrote ${path}. Open chrome://tracing to view.`);
        } catch (e) {
          addMsg("system", `Export failed: ${e}. (chrome_trace writer may not be wired yet.)`);
        }
        break;
      case "file.openVcd": {
        // Switch to Waveform tab first so the panel mounts and listens
        // for the open event; then trigger the native file picker.
        setActiveTab("waves");
        // `undefined` payload tells WaveformViewer to open its own dialog.
        await emit("pccx://open-vcd", undefined);
        break;
      }
      case "file.exit": win.close(); break;
      case "help.about":
        addMsg("system", "pccx-lab v0.4.0 — NPU Architecture Profiler\nLicense: Apache 2.0\nModules: core · ui · ai_copilot · uvm_bridge");
        break;
      case "help.shortcuts": shortcutHelp.setOpen(true); break;
      default: addMsg("system", `[${action}] — Coming soon`);
    }
  };

  const handleTestIPC = async () => {
    const t0 = performance.now();
    try {
      const payload: Uint8Array = await invoke("fetch_trace_payload");
      const dt = performance.now() - t0;
      const count = payload.byteLength / 24;
      addMsg("system", `⚡ IPC: ${(payload.byteLength / 1024 / 1024).toFixed(2)} MB (${count.toLocaleString()} events) — ${dt.toFixed(1)} ms`);
    } catch (e) { addMsg("system", `${t("copilot.ipcError")}: ${e}`); }
  };

  const handleSend = async () => {
    const text = inputText.trim();
    if (!text || copilotBusy) return;
    setInputText(""); addMsg("user", text);
    setCopilotBusy(true);
    try {
      let ctx = "";
      if (traceLoaded) { try { ctx = await invoke("compress_trace_context"); } catch {} }

      if (!apiKey) {
          const low = text.toLowerCase();
          let reply = "";
          if (low.includes("병목") || low.includes("bottleneck")) {
            reply = `${t("copilot.context")}: ${ctx}\n\n${t("copilot.bottleneck")}`;
          } else if (low.includes("uvm") || low.includes("testbench") || low.includes("코드")) {
            try {
              const s = low.includes("barrier") ? "barrier_reduction" : "l2_prefetch";
              const sv: string = await invoke("generate_uvm_sequence_cmd", { strategy: s });
              reply = `${t("copilot.uvmIntro")} (${s}):\n\n\`\`\`\n${sv}\n\`\`\`\n\n${t("copilot.uvmHint")}`;
            } catch { reply = t("copilot.uvmFailed"); }
          } else if (low.includes("report") || low.includes("보고서")) {
            reply = t("copilot.reportHint");
            setActiveTab("report");
          } else {
            reply = `${t("copilot.context")}: ${ctx || t("copilot.none")}\n\n${t("copilot.hintExamples")}`;
          }
          addMsg("ai", `${reply}\n${t("copilot.hintApiKey")}`);
      } else {
         try {
            const res = await fetch("https://api.openai.com/v1/chat/completions", {
              method: "POST",
              headers: { "Content-Type": "application/json", "Authorization": `Bearer ${apiKey}` },
              body: JSON.stringify({
                model: "gpt-4o-mini",
                messages: [
                  { role: "system", content: "You are the AI Copilot for pccx-lab EDA profiler. You assist with SystemVerilog, UVM, and NPU bottleneck analysis. Output context: " + ctx },
                  ...messages.filter(m => m.role !== "system").map(m => ({ role: m.role === "ai" ? "assistant" : "user", content: m.content })),
                  { role: "user", content: text }
                ]
              })
            });
            const data = await res.json();
            if (data.choices && data.choices[0]) {
               addMsg("ai", data.choices[0].message.content);
            } else {
               addMsg("system", `${t("copilot.apiError")}: ${data.error?.message || "Unknown error"}`);
            }
         } catch (err: any) {
            addMsg("system", `${t("copilot.httpError")}: ${err.message}`);
         }
      }
    } catch (e) { addMsg("ai", `${t("copilot.error")}: ${e}`); }
    finally { setCopilotBusy(false); }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const bg      = theme.bg;
  const panelBg = theme.bgPanel;
  const border  = theme.border;

  return (
    <div className="h-screen w-screen flex flex-col overflow-hidden select-none" style={{ background: bg, color: theme.text }}>
      <CommandPalette open={cmdPaletteOpen} setOpen={setCmdPaletteOpen} onAction={handleMenuAction} />
      <ShortcutHelp open={shortcutHelp.open} onClose={() => shortcutHelp.setOpen(false)} />
      
      {/* Title + Menu */}
      <TitleBar subtitle={header?.trace?.cycles ? `${header.trace.cycles.toLocaleString()} cycles` : undefined}>
        <MenuBar onAction={handleMenuAction} />
        <div className="flex-1" />
        <button aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"} onClick={theme.toggle} className="mr-2 p-1 rounded hover:bg-white/10 transition-colors" title={isDark ? "Light mode" : "Dark mode"}>
          {isDark ? <Sun size={13} className="text-yellow-400" /> : <Moon size={13} className="text-gray-600" />}
        </button>
      </TitleBar>
      <MainToolbar onAction={handleMenuAction} />

      {/* Main */}
      <div className="flex-1 flex overflow-hidden">
        {/* Resizable layout.
            Left / Right columns collect any panel with matching dock state.
            Center column hosts main tabs + any "bottom"-docked panels
            stacked vertically. Resize handles between every pair. */}
        {(() => {
          const copilotLeft    = copilotVisible && copilotDock === "left";
          const copilotRight   = copilotVisible && copilotDock === "right";
          const copilotBottom  = copilotVisible && copilotDock === "bottom";
          const bottomLeft     = bottomVisible && bottomDock === "left";
          const bottomRight    = bottomVisible && bottomDock === "right";
          const bottomBottom   = bottomVisible && bottomDock === "bottom";
          const hasLeft        = copilotLeft || bottomLeft;
          const hasRight       = copilotRight || bottomRight;
          const hasBottomStack = copilotBottom || bottomBottom;
          return (
          <Group orientation="horizontal" className="flex-1">
            {hasLeft && (
              <>
                <Panel defaultSize="24%" minSize="240px" maxSize="70%">
                   <Group orientation="vertical">
                     {copilotLeft && (
                       <Panel defaultSize={bottomLeft ? "60%" : "100%"} minSize="20%">
                         {renderCopilot()}
                       </Panel>
                     )}
                     {copilotLeft && bottomLeft && <ResizeHandle direction="vertical" />}
                     {bottomLeft && (
                       <Panel defaultSize={copilotLeft ? "40%" : "100%"} minSize="20%">
                         <BottomPanel dock={bottomDock} onDockChange={setBottomDock} onClose={() => setBottomVisible(false)} />
                       </Panel>
                     )}
                   </Group>
                </Panel>
                <ResizeHandle />
              </>
            )}
            <Panel defaultSize={hasLeft && hasRight ? "52%" : (hasLeft || hasRight ? "76%" : "100%")} minSize="25%">
              <Group orientation="vertical">
                <Panel defaultSize={hasBottomStack ? "68%" : "100%"} minSize="20%">
                  <div className="w-full h-full flex flex-col min-w-0 min-h-0" style={{ background: bg }}>
                    <div className="flex items-center shrink-0 overflow-x-auto" style={{ height: 32, borderBottom: `1px solid ${border}`, background: panelBg }}>
                      {TABS.map(t => (
                        <button key={t.id} onClick={() => setActiveTab(t.id)}
                          className="flex items-center gap-1.5 px-3 h-full transition-colors shrink-0"
                          style={{
                            fontSize: 11, fontWeight: activeTab === t.id ? 600 : 400,
                            color: activeTab === t.id ? theme.accent : theme.textMuted,
                            borderBottom: activeTab === t.id ? `2px solid ${theme.accent}` : "2px solid transparent",
                            borderRight: `1px solid ${border}`,
                          }}>
                          {t.icon} {t.label}
                        </button>
                      ))}
                      <div className="flex-1" />
                      <button aria-label="Run IPC benchmark" title="IPC Benchmark" onClick={handleTestIPC}
                        className="px-2 h-full flex items-center justify-center transition-colors"
                        style={{ color: theme.warning }}>
                        <Zap size={13} />
                      </button>
                      <button aria-label="Toggle AI Copilot panel" title="AI Copilot" onClick={() => setCopilotVisible(v => !v)}
                        className="px-2 h-full flex items-center justify-center transition-colors"
                        style={{ color: copilotVisible ? theme.accent : theme.textMuted }}>
                        <MessageSquare size={13} />
                      </button>
                      <div className="px-2">
                        {traceLoaded
                          ? <Badge color="green" variant="soft" size="1">trace loaded</Badge>
                          : <Badge color="gray"  variant="soft" size="1">no trace</Badge>}
                      </div>
                    </div>
                    <div className="flex-1 overflow-hidden">
                      {activeTab === "timeline"   && <Timeline />}
                      {activeTab === "flamegraph" && <FlameGraph />}
                      {activeTab === "hardware"   && <HardwareVisualizer />}
                      {activeTab === "memory"     && <MemoryDump />}
                      {activeTab === "waves"      && <WaveformViewer />}
                      {activeTab === "nodes"      && <NodeEditor />}
                      {activeTab === "canvas"     && <CanvasView />}
                      {activeTab === "code"       && <CodeEditor />}
                      {activeTab === "report"     && <ReportBuilder />}
                      {activeTab === "extensions" && <ExtensionManager />}
                      {activeTab === "verify"     && <VerificationSuite />}
                      {activeTab === "roofline"   && <Roofline />}
                      {activeTab === "scenario"   && <ScenarioFlow />}
                      {activeTab === "tb_author"  && <TestbenchAuthor />}
                    </div>
                  </div>
                </Panel>

                {hasBottomStack && (
                  <>
                    <ResizeHandle direction="vertical" />
                    <Panel defaultSize="32%" minSize="10%" maxSize="70%">
                       <Group orientation="horizontal">
                          {bottomBottom && (
                            <Panel defaultSize={copilotBottom ? "60%" : "100%"} minSize="20%">
                              <BottomPanel dock={bottomDock} onDockChange={setBottomDock} onClose={() => setBottomVisible(false)} />
                            </Panel>
                          )}
                          {bottomBottom && copilotBottom && <ResizeHandle />}
                          {copilotBottom && (
                            <Panel defaultSize={bottomBottom ? "40%" : "100%"} minSize="20%">
                              {renderCopilot()}
                            </Panel>
                          )}
                       </Group>
                    </Panel>
                  </>
                )}
              </Group>
            </Panel>
            {hasRight && (
              <>
                <ResizeHandle />
                <Panel defaultSize="24%" minSize="240px" maxSize="70%">
                  <Group orientation="vertical">
                    {copilotRight && (
                      <Panel defaultSize={bottomRight ? "60%" : "100%"} minSize="20%">
                        {renderCopilot()}
                      </Panel>
                    )}
                    {copilotRight && bottomRight && <ResizeHandle direction="vertical" />}
                    {bottomRight && (
                      <Panel defaultSize={copilotRight ? "40%" : "100%"} minSize="20%">
                        <BottomPanel dock={bottomDock} onDockChange={setBottomDock} onClose={() => setBottomVisible(false)} />
                      </Panel>
                    )}
                  </Group>
                </Panel>
              </>
            )}
          </Group>
          );
        })()}

        {/* Right Activity Bar (VS Code Secondary Side Bar style) */}
        <aside role="toolbar" aria-label="Activity bar" aria-orientation="vertical" style={{ width: 42, background: theme.bgPanel, borderLeft: `1px solid ${theme.border}`, display: "flex", flexDirection: "column", alignItems: "center", paddingTop: 8, gap: 6, zIndex: 10 }}>
          <button aria-label="Toggle AI Copilot panel" onClick={() => setCopilotVisible(v => !v)} title="AI Copilot" style={{ padding: 6, borderRadius: 4, cursor: "pointer", background: copilotVisible ? theme.bgHover : "transparent", transition: "all 0.15s" }}>
            <BrainCircuit size={18} color={copilotVisible ? theme.accent : theme.textMuted} />
          </button>
          <button aria-label="Toggle live telemetry panel" onClick={() => setBottomVisible(v => !v)} title="Live Telemetry" style={{ padding: 6, borderRadius: 4, cursor: "pointer", background: bottomVisible ? theme.bgHover : "transparent", transition: "all 0.15s" }}>
            <Activity size={18} color={bottomVisible ? theme.success : theme.textMuted} />
          </button>
        </aside>
      </div>

      {/* Status Bar */}
      <StatusBar traceLoaded={traceLoaded} totalCycles={header?.trace?.cycles} numCores={header?.trace?.cores} license={license} activeTab={activeTab} />
    </div>
  );
}

// ─── Root ─────────────────────────────────────────────────────────────────────

function App() {
  return (
    <ThemeProvider>
      <I18nProvider>
        <AppInner />
      </I18nProvider>
    </ThemeProvider>
  );
}

export default App;
