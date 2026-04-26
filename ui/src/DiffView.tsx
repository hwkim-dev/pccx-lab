import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useTheme } from "./ThemeContext";
import { ChevronRight, Copy, WrapText } from "lucide-react";

// ─── Public interface ─────────────────────────────────────────────────────────

export interface DiffViewProps {
  leftTitle?: string;
  rightTitle?: string;
  leftContent: string;
  rightContent: string;
  /** Used for optional syntax class hints (informational only — no full syntax highlighting) */
  language?: string;
}

// ─── Diff types ───────────────────────────────────────────────────────────────

type LineKind = "equal" | "added" | "removed" | "modified";

/** One rendered row in the side-by-side view. */
interface DiffRow {
  kind: LineKind;
  /** Left (expected) line, null for pure-added rows */
  left: string | null;
  /** Right (actual) line, null for pure-removed rows */
  right: string | null;
  /** 1-based line number on the left side */
  leftLine: number | null;
  /** 1-based line number on the right side */
  rightLine: number | null;
}

/** A collapsed run of equal lines. */
interface CollapseRow {
  kind: "collapsed";
  count: number;
  startIndex: number; // index into the full DiffRow[] before collapsing
}

type VirtualRow = DiffRow | CollapseRow;

// ─── LCS-based line diff ──────────────────────────────────────────────────────

/** Returns the LCS length table for Myers-style backtracking. */
function buildLcsTable(a: string[], b: string[]): number[][] {
  const m = a.length;
  const n = b.length;
  // Allocate (m+1)×(n+1)
  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i][j] = a[i - 1] === b[j - 1] ? dp[i - 1][j - 1] + 1 : Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }
  return dp;
}

type EditOp = { op: "eq"; a: string; b: string } | { op: "del"; a: string } | { op: "ins"; b: string };

/** Backtracks the LCS table to produce a flat edit script. */
function backtrack(dp: number[][], a: string[], b: string[], i: number, j: number, out: EditOp[]): void {
  if (i === 0 && j === 0) return;
  if (i > 0 && j > 0 && a[i - 1] === b[j - 1]) {
    backtrack(dp, a, b, i - 1, j - 1, out);
    out.push({ op: "eq", a: a[i - 1], b: b[i - 1] });
  } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
    backtrack(dp, a, b, i, j - 1, out);
    out.push({ op: "ins", b: b[j - 1] });
  } else {
    backtrack(dp, a, b, i - 1, j, out);
    out.push({ op: "del", a: a[i - 1] });
  }
}

/**
 * Produces DiffRows from two arrays of lines. Post-processes adjacent
 * delete/insert blocks into "modified" row pairs.
 */
function computeDiff(leftLines: string[], rightLines: string[]): DiffRow[] {
  // LCS is O(m*n). For very large files guard against OOM by trimming.
  const MAX_LINES = 4000;
  const a = leftLines.slice(0, MAX_LINES);
  const b = rightLines.slice(0, MAX_LINES);

  const dp = buildLcsTable(a, b);
  const ops: EditOp[] = [];
  backtrack(dp, a, b, a.length, b.length, ops);

  // Convert ops to raw diff rows with line number tracking
  const rawRows: DiffRow[] = [];
  let lNum = 1;
  let rNum = 1;
  for (const op of ops) {
    if (op.op === "eq") {
      rawRows.push({ kind: "equal", left: op.a, right: op.b, leftLine: lNum++, rightLine: rNum++ });
    } else if (op.op === "del") {
      rawRows.push({ kind: "removed", left: op.a, right: null, leftLine: lNum++, rightLine: null });
    } else {
      rawRows.push({ kind: "added", left: null, right: op.b, leftLine: null, rightLine: rNum++ });
    }
  }

  // Append any truncated lines as a simplified "equal" block
  if (leftLines.length > MAX_LINES || rightLines.length > MAX_LINES) {
    rawRows.push({
      kind: "equal",
      left: `… (${leftLines.length - MAX_LINES} more lines not shown)`,
      right: `… (${rightLines.length - MAX_LINES} more lines not shown)`,
      leftLine: null,
      rightLine: null,
    });
  }

  // Post-process: pair adjacent del/ins blocks as "modified"
  return pairModified(rawRows);
}

function pairModified(rows: DiffRow[]): DiffRow[] {
  const out: DiffRow[] = [];
  let i = 0;
  while (i < rows.length) {
    const row = rows[i];
    if (row.kind === "removed") {
      // Collect the del run
      const delRun: DiffRow[] = [];
      while (i < rows.length && rows[i].kind === "removed") delRun.push(rows[i++]);
      // Collect the immediately following ins run
      const insRun: DiffRow[] = [];
      while (i < rows.length && rows[i].kind === "added") insRun.push(rows[i++]);

      const paired = Math.min(delRun.length, insRun.length);
      for (let k = 0; k < paired; k++) {
        out.push({
          kind: "modified",
          left: delRun[k].left,
          right: insRun[k].right,
          leftLine: delRun[k].leftLine,
          rightLine: insRun[k].rightLine,
        });
      }
      // Leftovers remain as pure del/ins
      for (let k = paired; k < delRun.length; k++) out.push(delRun[k]);
      for (let k = paired; k < insRun.length; k++) out.push(insRun[k]);
    } else {
      out.push(row);
      i++;
    }
  }
  return out;
}

// ─── Collapsing equal regions ─────────────────────────────────────────────────

const COLLAPSE_THRESHOLD = 6;
const CONTEXT_LINES = 3;

function collapseEqualRuns(rows: DiffRow[], expandedRanges: Set<number>): VirtualRow[] {
  if (rows.length === 0) return [];

  // Find spans of equal rows
  const equalSpans: Array<{ start: number; end: number }> = [];
  let spanStart = -1;
  for (let i = 0; i < rows.length; i++) {
    if (rows[i].kind === "equal") {
      if (spanStart === -1) spanStart = i;
    } else {
      if (spanStart !== -1) { equalSpans.push({ start: spanStart, end: i - 1 }); spanStart = -1; }
    }
  }
  if (spanStart !== -1) equalSpans.push({ start: spanStart, end: rows.length - 1 });

  // Build a set of rows that should be collapsed
  const collapsedRows = new Set<number>();
  for (const span of equalSpans) {
    const len = span.end - span.start + 1;
    if (len <= COLLAPSE_THRESHOLD) continue;
    if (expandedRanges.has(span.start)) continue;
    // Keep CONTEXT_LINES at each end
    const keepStart = span.start + CONTEXT_LINES;
    const keepEnd   = span.end - CONTEXT_LINES;
    if (keepEnd < keepStart) continue;
    for (let i = keepStart; i <= keepEnd; i++) collapsedRows.add(i);
  }

  // Emit virtual rows, replacing each collapsed run with a single CollapseRow
  const out: VirtualRow[] = [];
  let i = 0;
  while (i < rows.length) {
    if (!collapsedRows.has(i)) {
      out.push(rows[i++]);
    } else {
      let count = 0;
      const startIndex = i;
      while (i < rows.length && collapsedRows.has(i)) { count++; i++; }
      out.push({ kind: "collapsed", count, startIndex });
    }
  }
  return out;
}

// ─── Diff summary ─────────────────────────────────────────────────────────────

interface DiffSummary { added: number; removed: number; modified: number; }

function summarize(rows: DiffRow[]): DiffSummary {
  let added = 0, removed = 0, modified = 0;
  for (const r of rows) {
    if (r.kind === "added")    added++;
    else if (r.kind === "removed") removed++;
    else if (r.kind === "modified") modified++;
  }
  return { added, removed, modified };
}

// ─── Row height constant ──────────────────────────────────────────────────────

const ROW_H = 20; // px — monospace line height

// ─── Component ───────────────────────────────────────────────────────────────

export const DiffView = memo(function DiffView({
  leftTitle = "Expected",
  rightTitle = "Actual",
  leftContent,
  rightContent,
}: DiffViewProps) {
  const theme = useTheme();
  const scrollRef = useRef<HTMLDivElement>(null);

  const [expandedRanges, setExpandedRanges] = useState<Set<number>>(new Set());
  const [wrapLines, setWrapLines] = useState(false);
  const [copiedSide, setCopiedSide] = useState<"left" | "right" | null>(null);
  const [focusedChangeIdx, setFocusedChangeIdx] = useState<number>(-1);

  // Recompute diff when content changes
  const diffRows = useMemo<DiffRow[]>(() => {
    const a = leftContent.split("\n");
    const b = rightContent.split("\n");
    return computeDiff(a, b);
  }, [leftContent, rightContent]);

  // Collapsed virtual row list
  const virtualRows = useMemo<VirtualRow[]>(
    () => collapseEqualRuns(diffRows, expandedRanges),
    [diffRows, expandedRanges],
  );

  const summary = useMemo(() => summarize(diffRows), [diffRows]);

  // Indices of change rows in virtualRows (for keyboard nav)
  const changeIndices = useMemo(
    () => virtualRows.reduce<number[]>((acc, r, i) => {
      if (r.kind !== "equal" && r.kind !== "collapsed") acc.push(i);
      return acc;
    }, []),
    [virtualRows],
  );

  // Reset expansion when content changes
  useEffect(() => { setExpandedRanges(new Set()); }, [leftContent, rightContent]);

  // Virtualizer
  const virtualizer = useVirtualizer({
    count: virtualRows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_H,
    overscan: 12,
  });

  // Keyboard navigation between changes
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable) return;
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      if (changeIndices.length === 0) return;
      e.preventDefault();
      setFocusedChangeIdx(prev => {
        let next: number;
        if (e.key === "ArrowDown") {
          next = prev < changeIndices.length - 1 ? prev + 1 : 0;
        } else {
          next = prev > 0 ? prev - 1 : changeIndices.length - 1;
        }
        const vIdx = changeIndices[next];
        virtualizer.scrollToIndex(vIdx, { align: "center" });
        return next;
      });
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [changeIndices, virtualizer]);

  const expandCollapsed = useCallback((startIndex: number) => {
    setExpandedRanges(prev => new Set(prev).add(startIndex));
  }, []);

  const handleCopy = useCallback((side: "left" | "right") => {
    const text = side === "left" ? leftContent : rightContent;
    navigator.clipboard.writeText(text).then(() => {
      setCopiedSide(side);
      setTimeout(() => setCopiedSide(null), 1500);
    }).catch(() => {});
  }, [leftContent, rightContent]);

  // ── Row style helpers ────────────────────────────────────────────────────

  const kindBg = (kind: LineKind, side: "left" | "right"): string => {
    if (kind === "added" && side === "right")    return theme.successBg;
    if (kind === "removed" && side === "left")   return theme.errorBg;
    if (kind === "modified")                     return theme.warningBg;
    return "transparent";
  };

  const kindText = (kind: LineKind): string => {
    if (kind === "added")    return theme.success;
    if (kind === "removed")  return theme.error;
    if (kind === "modified") return theme.warning;
    return theme.textMuted;
  };

  const gutterChar = (kind: LineKind, side: "left" | "right"): string => {
    if (kind === "added" && side === "right")    return "+";
    if (kind === "removed" && side === "left")   return "-";
    if (kind === "modified")                     return "~";
    return " ";
  };

  // ── Render ───────────────────────────────────────────────────────────────

  const lineNumStyle: React.CSSProperties = {
    minWidth: 40,
    paddingRight: 8,
    textAlign: "right",
    color: theme.textFaint,
    fontSize: 11,
    userSelect: "none",
    flexShrink: 0,
  };

  const gutterStyle = (kind: LineKind, _side: "left" | "right"): React.CSSProperties => ({
    width: 14,
    textAlign: "center",
    fontSize: 11,
    color: kindText(kind),
    fontWeight: 700,
    userSelect: "none",
    flexShrink: 0,
  });

  const codeStyle: React.CSSProperties = {
    flex: 1,
    fontFamily: theme.fontMono,
    fontSize: 12,
    lineHeight: `${ROW_H}px`,
    whiteSpace: wrapLines ? "pre-wrap" : "pre",
    overflowX: wrapLines ? "visible" : "hidden",
    overflow: "hidden",
    textOverflow: "ellipsis",
  };

  const renderCell = (
    text: string | null,
    lineNum: number | null,
    kind: LineKind,
    side: "left" | "right",
  ) => (
    <div style={{
      display: "flex",
      alignItems: "flex-start",
      background: kindBg(kind, side),
      paddingLeft: 4,
      minHeight: ROW_H,
      overflow: "hidden",
    }}>
      <span style={lineNumStyle}>{lineNum ?? ""}</span>
      <span style={gutterStyle(kind, side)}>{text !== null ? gutterChar(kind, side) : ""}</span>
      <span style={{ ...codeStyle, color: text === null ? theme.textFaint : theme.text }}>
        {text ?? ""}
      </span>
    </div>
  );

  const renderVirtualRow = (vRow: VirtualRow) => {
    if (vRow.kind === "collapsed") {
      return (
        <div style={{
          display: "flex",
          alignItems: "center",
          height: ROW_H,
          background: theme.bgPanel,
          borderTop: `0.5px solid ${theme.borderSubtle}`,
          borderBottom: `0.5px solid ${theme.borderSubtle}`,
        }}>
          <button
            onClick={() => expandCollapsed(vRow.startIndex)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 4,
              flex: 1,
              padding: "0 8px",
              background: "transparent",
              border: "none",
              cursor: "pointer",
              color: theme.accent,
              fontSize: 11,
              fontFamily: theme.fontMono,
              height: "100%",
            }}
          >
            <ChevronRight size={12} />
            {vRow.count} lines unchanged
          </button>
        </div>
      );
    }

    const row = vRow as DiffRow;
    return (
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", height: ROW_H }}>
        {renderCell(row.left, row.leftLine, row.kind, "left")}
        <div style={{ width: 1, background: theme.borderSubtle, flexShrink: 0 }} />
        {renderCell(row.right, row.rightLine, row.kind, "right")}
      </div>
    );
  };

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      width: "100%",
      height: "100%",
      background: theme.bgEditor,
      fontFamily: theme.fontMono,
      fontSize: 12,
    }}>
      {/* ── Toolbar ─────────────────────────────────────────────────────── */}
      <div style={{
        display: "flex",
        alignItems: "center",
        height: 32,
        padding: "0 8px",
        background: theme.bgPanel,
        borderBottom: `0.5px solid ${theme.borderSubtle}`,
        gap: 8,
        flexShrink: 0,
      }}>
        {/* Summary */}
        <span style={{ fontSize: 11, color: theme.textMuted }}>
          {summary.added > 0 && (
            <span style={{ color: theme.success, marginRight: 8 }}>+{summary.added}</span>
          )}
          {summary.removed > 0 && (
            <span style={{ color: theme.error, marginRight: 8 }}>-{summary.removed}</span>
          )}
          {summary.modified > 0 && (
            <span style={{ color: theme.warning, marginRight: 8 }}>~{summary.modified}</span>
          )}
          {summary.added === 0 && summary.removed === 0 && summary.modified === 0 && (
            <span>No differences</span>
          )}
        </span>

        <div style={{ flex: 1 }} />

        {/* Nav hint */}
        {changeIndices.length > 0 && (
          <span style={{ fontSize: 10, color: theme.textFaint }}>
            {focusedChangeIdx >= 0 ? `${focusedChangeIdx + 1}/` : ""}{changeIndices.length} changes
          </span>
        )}

        {/* Wrap toggle */}
        <button
          title="Toggle line wrap"
          onClick={() => setWrapLines(w => !w)}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 4,
            padding: "3px 7px",
            borderRadius: 5,
            border: "none",
            cursor: "pointer",
            background: wrapLines ? theme.accentBg : "transparent",
            color: wrapLines ? theme.accent : theme.textMuted,
            fontSize: 11,
            transition: `all 0.12s ${theme.ease}`,
          }}
        >
          <WrapText size={12} />
        </button>
      </div>

      {/* ── Column headers ───────────────────────────────────────────────── */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        height: 28,
        borderBottom: `0.5px solid ${theme.borderSubtle}`,
        background: theme.bgPanel,
        flexShrink: 0,
      }}>
        <div style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 8px",
          borderRight: `0.5px solid ${theme.borderSubtle}`,
        }}>
          <span style={{ fontSize: 11, color: theme.textMuted, fontFamily: theme.fontSans }}>{leftTitle}</span>
          <button
            title="Copy left content"
            onClick={() => handleCopy("left")}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 4,
              padding: "2px 6px",
              borderRadius: 4,
              border: "none",
              cursor: "pointer",
              background: "transparent",
              color: copiedSide === "left" ? theme.success : theme.textFaint,
              fontSize: 10,
              fontFamily: theme.fontSans,
              transition: `color 0.15s ${theme.ease}`,
            }}
          >
            <Copy size={11} />
            {copiedSide === "left" ? "Copied" : "Copy"}
          </button>
        </div>
        <div style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 8px",
        }}>
          <span style={{ fontSize: 11, color: theme.accent, fontFamily: theme.fontSans }}>{rightTitle}</span>
          <button
            title="Copy right content"
            onClick={() => handleCopy("right")}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 4,
              padding: "2px 6px",
              borderRadius: 4,
              border: "none",
              cursor: "pointer",
              background: "transparent",
              color: copiedSide === "right" ? theme.success : theme.textFaint,
              fontSize: 10,
              fontFamily: theme.fontSans,
              transition: `color 0.15s ${theme.ease}`,
            }}
          >
            <Copy size={11} />
            {copiedSide === "right" ? "Copied" : "Copy"}
          </button>
        </div>
      </div>

      {/* ── Virtual diff body ─────────────────────────────────────────────── */}
      <div
        ref={scrollRef}
        style={{ flex: 1, overflowY: "auto", overflowX: wrapLines ? "hidden" : "auto" }}
      >
        {virtualRows.length === 0 ? (
          <div style={{ padding: 24, color: theme.textMuted, fontSize: 12, fontFamily: theme.fontSans }}>
            No content to diff.
          </div>
        ) : (
          <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
            {virtualizer.getVirtualItems().map(vi => (
              <div
                key={vi.index}
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "100%",
                  height: vi.size,
                  transform: `translateY(${vi.start}px)`,
                }}
              >
                {renderVirtualRow(virtualRows[vi.index])}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
});
