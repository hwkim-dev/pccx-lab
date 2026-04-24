import { useState, useEffect, useRef } from "react";
import { useTheme } from "./ThemeContext";
import { Search, Play, FileText, Activity, Code2, Clock, Layers, Database, Box, Settings2, CheckCircle, PieChart, Zap, ActivitySquare, LayoutDashboard, Download } from "lucide-react";

interface CommandItem {
  id: string;
  label: string;
  shortcut?: string;
  icon?: React.ReactNode;
  action: () => void;
  category: "Files" | "View" | "Run" | "Analysis" | "Tools";
}

export function CommandPalette({ open, setOpen, onAction }: { open: boolean, setOpen: (v: boolean) => void, onAction: (a: string) => void }) {
  const theme = useTheme();
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const ITEMS: CommandItem[] = [
    // View
    { id: "view.scenario", label: "Scenario Flow", icon: <Zap size={14}/>, category: "View", action: () => onAction("view.scenario") },
    { id: "view.timeline", label: "Timeline Analysis", shortcut: "F1", icon: <Clock size={14}/>, category: "View", action: () => onAction("view.timeline") },
    { id: "view.flamegraph", label: "Flame Graph", icon: <Layers size={14}/>, category: "View", action: () => onAction("view.flamegraph") },
    { id: "view.waves", label: "Waveform Viewer", icon: <ActivitySquare size={14}/>, category: "View", action: () => onAction("view.waves") },
    { id: "view.hardware", label: "System Simulator", icon: <Activity size={14}/>, category: "View", action: () => onAction("view.hardware") },
    { id: "view.memory", label: "Memory Dump", icon: <Database size={14}/>, category: "View", action: () => onAction("view.memory") },
    { id: "view.nodes", label: "Data Flow Editor", shortcut: "F2", icon: <Activity size={14}/>, category: "View", action: () => onAction("view.nodes") },
    { id: "view.code", label: "SV Editor", shortcut: "F3", icon: <Code2 size={14}/>, category: "View", action: () => onAction("view.code") },
    { id: "view.tb_author", label: "Testbench Author", icon: <LayoutDashboard size={14}/>, category: "View", action: () => onAction("view.tb_author") },
    { id: "view.report", label: "Report Builder", shortcut: "F4", icon: <FileText size={14}/>, category: "View", action: () => onAction("view.report") },
    { id: "view.canvas", label: "3D View", icon: <Box size={14}/>, category: "View", action: () => onAction("view.canvas") },
    { id: "view.extensions", label: "Extensions", icon: <Settings2 size={14}/>, category: "View", action: () => onAction("view.extensions") },
    { id: "view.verify", label: "Verification Suite", icon: <CheckCircle size={14}/>, category: "View", action: () => onAction("verify.isa") },
    { id: "view.copilot", label: "Toggle AI Copilot", icon: <Activity size={14}/>, category: "View", action: () => onAction("view.copilot") },
    { id: "view.bottom", label: "Toggle Bottom Panel", icon: <Activity size={14}/>, category: "View", action: () => onAction("view.bottom") },
    // Analysis
    { id: "analysis.roofline", label: "Roofline Analysis", icon: <PieChart size={14}/>, category: "Analysis", action: () => onAction("analysis.roofline") },
    { id: "trace.benchmark", label: "IPC Benchmark", shortcut: "Ctrl+B", icon: <Zap size={14}/>, category: "Analysis", action: () => onAction("trace.benchmark") },
    { id: "analysis.pdf", label: "Generate PDF Report", icon: <FileText size={14}/>, category: "Analysis", action: () => onAction("analysis.pdf") },
    // Run
    { id: "run.start", label: "Start Simulation", shortcut: "F5", icon: <Play size={14}/>, category: "Run", action: () => onAction("run.start") },
    // Files
    { id: "file.openVcd", label: "Open VCD File", icon: <ActivitySquare size={14}/>, category: "Files", action: () => onAction("file.openVcd") },
    { id: "tools.vcd", label: "Export as VCD", icon: <Download size={14}/>, category: "Files", action: () => onAction("tools.vcd") },
    { id: "tools.chromeTrace", label: "Export as Chrome Trace", icon: <Download size={14}/>, category: "Files", action: () => onAction("tools.chromeTrace") },
  ];

  const filtered = ITEMS.filter(item => item.label.toLowerCase().includes(query.toLowerCase()) || item.category.toLowerCase().includes(query.toLowerCase()));

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "p") {
        e.preventDefault();
        setOpen(true);
      }
      if (e.key === "Escape" && open) {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, setOpen]);

  useEffect(() => {
    if (open) {
      inputRef.current?.focus();
      setQuery("");
      setSelectedIndex(0);
    }
  }, [open]);

  useEffect(() => { setSelectedIndex(0); }, [query]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex(prev => (prev + 1) % filtered.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex(prev => (prev - 1 + filtered.length) % filtered.length);
    } else if (e.key === "Enter" && filtered.length > 0) {
      e.preventDefault();
      filtered[selectedIndex].action();
      setOpen(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]" style={{ background: "rgba(0,0,0,0.4)", backdropFilter: "blur(2px)" }}>
      {/* Click outside to close */}
      <div className="absolute inset-0" onClick={() => setOpen(false)} />
      
      <div 
        className="relative w-[600px] shadow-2xl rounded-lg overflow-hidden flex flex-col pointer-events-auto"
        style={{ background: theme.bgPanel, border: `1px solid ${theme.border}` }}
      >
        <div className="flex items-center px-4" style={{ height: 46, borderBottom: `1px solid ${theme.borderDim}` }}>
          <Search size={18} style={{ color: theme.textMuted, marginRight: 12 }} />
          <input 
            ref={inputRef}
            type="text" 
            placeholder="Search commands, files, or settings..." 
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            style={{ 
              flex: 1, height: "100%", background: "transparent", border: "none", outline: "none", 
              color: theme.text, fontSize: 13, fontFamily: "Inter, sans-serif"
            }}
          />
        </div>

        <div className="flex-1 max-h-[400px] overflow-y-auto py-2">
          {filtered.length === 0 ? (
            <div className="px-4 py-8 text-center" style={{ color: theme.textMuted, fontSize: 12 }}>
              No matching commands.
            </div>
          ) : (
            filtered.map((item, i) => (
              <div 
                key={item.id}
                onClick={() => { item.action(); setOpen(false); }}
                className="flex items-center px-4 py-2 cursor-pointer transition-colors"
                style={{ 
                  background: i === selectedIndex ? theme.bgHover : "transparent",
                  color: i === selectedIndex ? theme.text : theme.textDim
                }}
                onMouseEnter={() => setSelectedIndex(i)}
              >
                <div style={{ color: i === selectedIndex ? theme.accent : theme.textMuted }} className="mr-3">
                  {item.icon}
                </div>
                <div style={{ flex: 1, fontSize: 12 }}>
                  <span style={{ fontWeight: 600 }}>{item.label}</span>
                  <span style={{ color: theme.textMuted, marginLeft: 8, fontSize: 11 }}>{item.category}</span>
                </div>
                {item.shortcut && (
                  <div style={{ fontSize: 10, background: theme.bgInput, padding: "2px 6px", borderRadius: 4, color: theme.textMuted, fontFamily: "monospace" }}>
                    {item.shortcut}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
        
        <div className="px-4 py-2 shrink-0 flex items-center justify-between" style={{ borderTop: `1px solid ${theme.borderDim}`, background: theme.bgSurface, fontSize: 9, color: theme.textMuted }}>
          <span><kbd style={{ background: theme.bgInput, padding: "1px 4px", borderRadius: 2 }}>↑↓</kbd> to navigate</span>
          <span><kbd style={{ background: theme.bgInput, padding: "1px 4px", borderRadius: 2 }}>Enter</kbd> to select</span>
          <span><kbd style={{ background: theme.bgInput, padding: "1px 4px", borderRadius: 2 }}>Esc</kbd> to dismiss</span>
        </div>
      </div>
    </div>
  );
}
