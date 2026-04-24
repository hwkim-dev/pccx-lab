import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { ChevronRight, ChevronDown, Code2, FileText, Folder } from "lucide-react";
import { useTheme } from "./ThemeContext";

// ─── Types ───────────────────────────────────────────────────────────────────

interface FileNode {
  name: string;
  path: string;
  is_dir: boolean;
  children?: FileNode[] | null;
}

interface FileTreeProps {
  root: string;
  onFileOpen: (path: string, name: string) => void;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const HDL_EXTENSIONS = new Set(["sv", "svh", "v", "vh"]);

function extOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot + 1).toLowerCase() : "";
}

function isHdlFile(name: string): boolean {
  return HDL_EXTENSIONS.has(extOf(name));
}

// ─── Row ─────────────────────────────────────────────────────────────────────

interface RowProps {
  node: FileNode;
  depth: number;
  expanded: Set<string>;
  onToggle: (path: string, isDir: boolean) => void;
  onFileOpen: (path: string, name: string) => void;
  accent: string;
  text: string;
  textMuted: string;
  bgHover: string;
}

function Row({
  node,
  depth,
  expanded,
  onToggle,
  onFileOpen,
  accent,
  text,
  textMuted,
  bgHover,
}: RowProps) {
  const isOpen = expanded.has(node.path);
  const hdl = !node.is_dir && isHdlFile(node.name);

  const handleClick = useCallback(() => {
    if (node.is_dir) {
      onToggle(node.path, true);
    }
  }, [node.path, node.is_dir, onToggle]);

  const handleDoubleClick = useCallback(() => {
    if (!node.is_dir) {
      onFileOpen(node.path, node.name);
    }
  }, [node.path, node.name, node.is_dir, onFileOpen]);

  return (
    <>
      <div
        role="treeitem"
        style={{
          display: "flex",
          alignItems: "center",
          height: 20,
          paddingLeft: depth * 16,
          cursor: node.is_dir ? "pointer" : "default",
          userSelect: "none",
          color: hdl ? accent : text,
          fontSize: 12,
          fontFamily: "'JetBrains Mono', monospace",
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
        onClick={handleClick}
        onDoubleClick={handleDoubleClick}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLElement).style.backgroundColor = bgHover;
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLElement).style.backgroundColor = "transparent";
        }}
      >
        {/* Chevron / spacer */}
        <span style={{ width: 16, flexShrink: 0, display: "inline-flex" }}>
          {node.is_dir ? (
            isOpen ? (
              <ChevronDown size={14} color={textMuted} />
            ) : (
              <ChevronRight size={14} color={textMuted} />
            )
          ) : null}
        </span>

        {/* Icon */}
        <span
          style={{
            width: 16,
            flexShrink: 0,
            display: "inline-flex",
            marginRight: 4,
          }}
        >
          {node.is_dir ? (
            <Folder size={14} color={textMuted} />
          ) : hdl ? (
            <Code2 size={14} color={accent} />
          ) : (
            <FileText size={14} color={textMuted} />
          )}
        </span>

        {/* Name */}
        <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>
          {node.name}
        </span>
      </div>

      {/* Children (only rendered when expanded) */}
      {node.is_dir && isOpen && node.children && node.children.length > 0 && (
        <div role="group">
          {node.children.map((child) => (
            <Row
              key={child.path}
              node={child}
              depth={depth + 1}
              expanded={expanded}
              onToggle={onToggle}
              onFileOpen={onFileOpen}
              accent={accent}
              text={text}
              textMuted={textMuted}
              bgHover={bgHover}
            />
          ))}
        </div>
      )}
    </>
  );
}

// ─── FileTree ────────────────────────────────────────────────────────────────

export default function FileTree({ root, onFileOpen }: FileTreeProps) {
  const theme = useTheme();
  const [nodes, setNodes] = useState<FileNode[]>([]);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  // Initial load of the root directory (depth 1 for immediate children).
  useEffect(() => {
    let cancelled = false;
    invoke<FileNode[]>("read_file_tree", { root, depth: 1 })
      .then((tree) => {
        if (!cancelled) {
          setNodes(tree);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [root]);

  // Expand / collapse handler with lazy-load for directories.
  const handleToggle = useCallback(
    (path: string, isDir: boolean) => {
      if (!isDir) return;

      setExpanded((prev) => {
        const next = new Set(prev);
        if (next.has(path)) {
          next.delete(path);
        } else {
          next.add(path);
          // Lazy-load children if they haven't been fetched yet.
          // Walk the tree to find the node and populate its children.
          const populate = (list: FileNode[]): boolean => {
            for (const n of list) {
              if (n.path === path) {
                // Children are the empty-placeholder array -> need fetch
                if (n.children && n.children.length === 0) {
                  invoke<FileNode[]>("read_file_tree", {
                    root: path,
                    depth: 1,
                  }).then((children) => {
                    n.children = children;
                    // Force re-render by creating a new top-level array ref
                    setNodes((prev) => [...prev]);
                  });
                }
                return true;
              }
              if (n.children && populate(n.children)) return true;
            }
            return false;
          };
          populate(nodes);
        }
        return next;
      });
    },
    [nodes],
  );

  if (error) {
    return (
      <div
        style={{
          padding: 8,
          fontSize: 11,
          color: theme.error,
          fontFamily: "'JetBrains Mono', monospace",
        }}
      >
        {error}
      </div>
    );
  }

  if (nodes.length === 0) {
    return (
      <div
        style={{
          padding: 8,
          fontSize: 11,
          color: theme.textFaint,
          fontFamily: "'JetBrains Mono', monospace",
        }}
      >
        Empty directory
      </div>
    );
  }

  return (
    <div
      role="tree"
      style={{
        overflowY: "auto",
        overflowX: "hidden",
        fontSize: 12,
        fontFamily: "'JetBrains Mono', monospace",
      }}
    >
      {nodes.map((node) => (
        <Row
          key={node.path}
          node={node}
          depth={0}
          expanded={expanded}
          onToggle={handleToggle}
          onFileOpen={onFileOpen}
          accent={theme.accent}
          text={theme.text}
          textMuted={theme.textMuted}
          bgHover={theme.bgHover}
        />
      ))}
    </div>
  );
}
