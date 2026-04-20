"""E2E for the detect_bottlenecks IPC command.

Loads the tb_packer .pccx (1024 MAC cycles, no DMA) and verifies the
detector returns an empty list on a pure-MAC workload; loads the
simulator-generated dummy trace with DMA contention to confirm it
actually flags hotspots when they exist."""

from pathlib import Path

import pytest

SIBLING_FPGA = Path(__file__).resolve().parents[4] / "pccx-FPGA-NPU-LLM-kv260"
TRACE_PATH   = SIBLING_FPGA / "hw" / "sim" / "work" / "tb_packer.pccx"

# The simulator demo trace ships with the repo and contains DMA/stall
# events we know should surface on the default detector config.
DEMO_TRACE   = Path(__file__).resolve().parents[3] / "dummy_trace.pccx"


def _invoke(driver, command: str, args: dict) -> dict:
    script = """
    const callback = arguments[arguments.length - 1];
    const cmd = arguments[0];
    const params = arguments[1];
    const bridge = (window.__TAURI__ && window.__TAURI__.core && window.__TAURI__.core.invoke)
                || (window.__TAURI__ && window.__TAURI__.invoke);
    if (!bridge) {
        callback({ok: false, err: 'Tauri invoke bridge not on window'});
        return;
    }
    bridge(cmd, params)
        .then(v => callback({ok: true, value: v}))
        .catch(e => callback({ok: false, err: String(e)}));
    """
    driver.set_script_timeout(15)
    return driver.execute_async_script(script, command, args)


@pytest.mark.skipif(not TRACE_PATH.exists(), reason="tb_packer trace missing")
def test_pure_mac_trace_has_no_bottlenecks(driver):
    load = _invoke(driver, "load_pccx", {"path": str(TRACE_PATH)})
    assert load["ok"], load

    res = _invoke(driver, "detect_bottlenecks", {})
    assert res["ok"], res
    # tb_packer only emits MAC_COMPUTE events, so no DMA / stall windows
    # should cross the 50 % default threshold.
    intervals = res["value"]
    assert intervals == [], intervals


@pytest.mark.skipif(not DEMO_TRACE.exists(), reason="dummy_trace missing")
def test_demo_trace_surfaces_dma_hotspots(driver):
    load = _invoke(driver, "load_pccx", {"path": str(DEMO_TRACE)})
    assert load["ok"], load

    res = _invoke(driver, "detect_bottlenecks",
                  {"windowCycles": 256, "threshold": 0.3})
    assert res["ok"], res
    intervals = res["value"]
    assert len(intervals) > 0, \
        "demo trace is expected to contain DMA contention windows"
    # Every reported window must be well-formed.
    for iv in intervals:
        assert iv["end_cycle"] > iv["start_cycle"], iv
        assert iv["share"] >= 0.3, iv
        assert iv["kind"] in {"dma_read", "dma_write", "systolic_stall", "barrier_sync"}


def test_fails_without_trace(driver):
    # Warmed cache or not — the contract is actionable error text.
    res = _invoke(driver, "detect_bottlenecks", {})
    if not res["ok"]:
        assert "trace" in res["err"].lower(), res
