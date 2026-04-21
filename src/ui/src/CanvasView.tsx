import { useRef, useEffect, useCallback } from "react";
import * as THREE from "three";
import { invoke } from "@tauri-apps/api/core";
import { useVisibilityGate } from "./hooks/useVisibilityGate";

// MAC array dimensions — must match HardwareModel::pccx_reference()
const ROWS = 32;
const COLS = 32;
const COUNT = ROWS * COLS;

/** Maps [0,1] utilisation to an HSL colour (blue=idle → green=active → red=hot). */
function utilToColor(util: number): THREE.Color {
  // cold: hue=220 (blue) → warm: hue=120 (green) → hot: hue=0 (red)
  const hue = (1.0 - util) * 220;
  return new THREE.Color().setHSL(hue / 360, 0.9, 0.55);
}

// Round-5 T-3: `animated` gates the ornamental colour pulse wave.
// When false (e.g. paused playback) the array renders static per-core
// utilisation only — no decorative heartbeat.  Default true preserves
// the existing <CanvasView /> call sites.
interface CanvasViewProps { animated?: boolean; isPlaying?: boolean }

export function CanvasView({ animated = true, isPlaying }: CanvasViewProps = {}) {
  // `isPlaying` is the canonical name; `animated` is the prop alias
  // the ticket calls out.  Treat either as the animation gate.
  const animationEnabled = isPlaying ?? animated;
  const animRef = useRef<boolean>(animationEnabled);
  animRef.current = animationEnabled;
  const mountRef  = useRef<HTMLDivElement>(null);
  const animIdRef = useRef<number>(0);
  // Round-6 T-3: pause the RAF loop when the 3D-View tab is hidden or
  // the panel is docked off-screen.  MDN Page Visibility API + DOM
  // IntersectionObserver — an Apple-grade app never renders an
  // off-screen tab (spec: https://w3c.github.io/page-visibility/).
  const visible = useVisibilityGate(mountRef);
  const visibleRef = useRef(visible);
  visibleRef.current = visible;

  // Mouse state for orbit-like rotation
  const mouse = useRef({ dragging: false, lastX: 0, lastY: 0, rotX: 0.3, rotY: 0.4 });

  const setupMouseHandlers = useCallback((
    canvas: HTMLCanvasElement,
    mesh: THREE.InstancedMesh,
    camera: THREE.PerspectiveCamera,
  ) => {
    const m = mouse.current;

    const onDown = (e: MouseEvent) => {
      m.dragging = true; m.lastX = e.clientX; m.lastY = e.clientY;
    };
    const onUp   = () => { m.dragging = false; };
    const onMove = (e: MouseEvent) => {
      if (!m.dragging) return;
      const dx = e.clientX - m.lastX;
      const dy = e.clientY - m.lastY;
      m.lastX = e.clientX; m.lastY = e.clientY;
      m.rotY += dx * 0.005;
      m.rotX += dy * 0.005;
      m.rotX = Math.max(-Math.PI / 2, Math.min(Math.PI / 2, m.rotX));
      mesh.rotation.y = m.rotY;
      mesh.rotation.x = m.rotX;
    };
    const onWheel = (e: WheelEvent) => {
      camera.position.z = Math.max(10, Math.min(60, camera.position.z + e.deltaY * 0.03));
    };

    canvas.addEventListener("mousedown", onDown);
    window.addEventListener("mouseup", onUp);
    window.addEventListener("mousemove", onMove);
    canvas.addEventListener("wheel", onWheel, { passive: true });

    return () => {
      canvas.removeEventListener("mousedown", onDown);
      window.removeEventListener("mouseup", onUp);
      window.removeEventListener("mousemove", onMove);
      canvas.removeEventListener("wheel", onWheel);
    };
  }, []);

  useEffect(() => {
    if (!mountRef.current) return;
    const container = mountRef.current;
    const w = container.clientWidth;
    const h = container.clientHeight;

    // ─── Scene Setup ────────────────────────────────────────────────
    const scene    = new THREE.Scene();
    const camera   = new THREE.PerspectiveCamera(60, w / h, 0.1, 1000);
    camera.position.set(0, 0, 28);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(w, h);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0);
    container.appendChild(renderer.domElement);

    // ─── Instanced MAC Array ────────────────────────────────────────
    const geo  = new THREE.BoxGeometry(0.78, 0.78, 0.78);
    const mat  = new THREE.MeshStandardMaterial({
      roughness: 0.25,
      metalness: 0.85,
      vertexColors: false,
    });
    const mesh = new THREE.InstancedMesh(geo, mat, COUNT);
    mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);

    const dummy = new THREE.Object3D();
    let   idx   = 0;
    for (let x = 0; x < COLS; x++) {
      for (let y = 0; y < ROWS; y++) {
        dummy.position.set(x - COLS / 2 + 0.5, y - ROWS / 2 + 0.5, 0);
        dummy.updateMatrix();
        mesh.setMatrixAt(idx, dummy.matrix);
        mesh.setColorAt(idx, utilToColor(0.15)); // start as "cold"
        idx++;
      }
    }
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    mouse.current.rotX = 0.3;
    mouse.current.rotY = 0.4;
    mesh.rotation.x = mouse.current.rotX;
    mesh.rotation.y = mouse.current.rotY;
    scene.add(mesh);

    // ─── Lights ─────────────────────────────────────────────────────
    const dirLight = new THREE.DirectionalLight(0xffffff, 2.5);
    dirLight.position.set(12, 12, 15);
    scene.add(dirLight);
    scene.add(new THREE.AmbientLight(0x404060, 1.8));
    const rimLight = new THREE.DirectionalLight(0x6060ff, 0.8);
    rimLight.position.set(-10, -8, -5);
    scene.add(rimLight);

    // ─── Grid Helper (floor reference) ──────────────────────────────
    const grid = new THREE.GridHelper(COLS, COLS, 0x1a1a2e, 0x1a1a2e);
    grid.position.y = -(ROWS / 2) - 1;
    scene.add(grid);

    // ─── Load live utilisation data ─────────────────────────────────
    invoke<{ core_utils: { core_id: number; util_pct: number }[] }>(
      "get_core_utilisation"
    )
      .then(({ core_utils }) => {
        const utilMap = new Map(core_utils.map((c) => [c.core_id, c.util_pct / 100]));
        let i2 = 0;
        for (let x = 0; x < COLS; x++) {
          for (let y = 0; y < ROWS; y++) {
            // Map 2-D position → core_id (row-major)
            const coreId = y * COLS + x;
            const util   = utilMap.get(coreId % core_utils.length) ?? 0.15;
            mesh.setColorAt(i2, utilToColor(util));
            i2++;
          }
        }
        if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
      })
      .catch(() => {
        // Keep "cold" colours if no trace is loaded
      });

    // ─── Pulsing animation: simulate live MAC activity ───────────────
    // Round-6 T-3: visibility-gated RAF loop with sparse instance-
    // colour updates via InstancedBufferAttribute.updateRange.  Only
    // columns whose wave-scalar *differs* from the previous frame are
    // re-uploaded to the GPU — cuts per-frame Webgl work from O(COUNT)
    // to O(active columns).
    //
    // References:
    //   - Three.js InstancedBufferAttribute.updateRange (https://threejs.org/docs/api/en/core/InstancedBufferAttribute.html)
    //   - Three.js "How to Update Things" (https://threejs.org/manual/en/how-to-update-things.html)
    //   - MDN Page Visibility API (https://developer.mozilla.org/en-US/docs/Web/API/Page_Visibility_API)
    //
    // Cache the baked per-instance colour so we don't pay a
    // `getColorAt` per frame — reads from the InstancedBufferAttribute
    // round-trip through a THREE.Color alloc and cost real time.
    const baked: { r: number; g: number; b: number }[] = [];
    for (let i = 0; i < COUNT; i++) {
      const c = new THREE.Color();
      mesh.getColorAt(i, c);
      baked.push({ r: c.r, g: c.g, b: c.b });
    }
    // Last-applied scalar per column so we only touch dirty instances.
    const lastWave = new Float32Array(COLS);
    for (let i = 0; i < COLS; i++) lastWave[i] = NaN;
    const DIRTY_EPS = 1 / 256; // 8-bit colour resolution threshold

    let phase = 0;
    const animate = () => {
      animIdRef.current = requestAnimationFrame(animate);

      // Round-6 T-3: skip the entire loop body when the panel is not
      // visible (tab hidden / docked panel collapsed).  Browsers
      // already auto-throttle main-thread RAF on hidden tabs, but we
      // additionally bail before touching the WebGL queue so the GPU
      // goes idle within one frame.
      if (!visibleRef.current) return;

      phase += 0.018;

      // Slow auto-rotate when not dragging
      if (!mouse.current.dragging) {
        mouse.current.rotY += 0.0008;
        mesh.rotation.y = mouse.current.rotY;
      }

      if (animRef.current) {
        // Sparse update pattern: per-column wave scalar; only re-upload
        // the instance colours whose column's scalar drifted by more
        // than a JPEG-level threshold.  On an idle frame with stable
        // wave, `setColorAt` fires for zero instances.
        let dirtyMin = COUNT;
        let dirtyMax = -1;
        for (let x = 0; x < COLS; x++) {
          const wave = 0.5 + 0.5 * Math.sin(phase * 2 - x * 0.4);
          if (!Number.isNaN(lastWave[x]) && Math.abs(wave - lastWave[x]) < DIRTY_EPS) continue;
          lastWave[x] = wave;
          const scale = 0.85 + 0.15 * wave;
          for (let y = 0; y < ROWS; y++) {
            const idx = x * ROWS + y;
            const b = baked[idx];
            // Mul scale into the baked colour; write back sparsely.
            const col = new THREE.Color(b.r * scale, b.g * scale, b.b * scale);
            mesh.setColorAt(idx, col);
            if (idx < dirtyMin) dirtyMin = idx;
            if (idx > dirtyMax) dirtyMax = idx;
          }
        }
        if (dirtyMax >= 0 && mesh.instanceColor) {
          // Three.js InstancedBufferAttribute.updateRange — only push
          // the dirty slice to the GPU instead of the full 1024-colour
          // array.  `.clearUpdateRanges` / `.addUpdateRange` is r169+
          // API; the `updateRange` property is the classic accessor
          // that works on every Three version we bundle.
          const attr = mesh.instanceColor;
          // Typed as any because Three.js's InstancedBufferAttribute
          // type predates the per-component `updateRange` narrowing.
          const range = (attr as unknown as { updateRange: { offset: number; count: number } }).updateRange;
          range.offset = dirtyMin * 3;
          range.count  = (dirtyMax - dirtyMin + 1) * 3;
          attr.needsUpdate = true;
        }
      }

      renderer.render(scene, camera);
    };
    animate();

    // ─── Mouse controls ──────────────────────────────────────────────
    const removeMouseHandlers = setupMouseHandlers(renderer.domElement, mesh, camera);

    // ─── Resize handler ──────────────────────────────────────────────
    const onResize = () => {
      if (!container) return;
      const nw = container.clientWidth;
      const nh = container.clientHeight;
      renderer.setSize(nw, nh);
      camera.aspect = nw / nh;
      camera.updateProjectionMatrix();
    };
    window.addEventListener("resize", onResize);

    return () => {
      cancelAnimationFrame(animIdRef.current);
      window.removeEventListener("resize", onResize);
      removeMouseHandlers();
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
      geo.dispose();
      mat.dispose();
      renderer.dispose();
    };
  }, [setupMouseHandlers]);

  return (
    <div
      ref={mountRef}
      className="w-full h-full bg-transparent cursor-grab active:cursor-grabbing"
      title="Drag to rotate · Scroll to zoom"
    />
  );
}
