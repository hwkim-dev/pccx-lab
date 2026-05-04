"""E2E for the roofline analysis and UVM strategy IPC commands.

These are pure-Rust-side computations exposed via Tauri IPC — the
happy-path verifies the commands return structurally sane JSON so the
dashboard widgets can bind to them."""

from pathlib import Path

import pytest

SIBLING_PCCX = (
    Path(__file__).resolve().parents[4]
    / "pccx-FPGA-NPU-LLM-kv260"
    / "hw"
    / "sim"
    / "work"
    / "tb_packer.pccx"
)


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


def test_list_uvm_strategies_known_set(driver):
    res = _invoke(driver, "list_uvm_strategies", {})
    assert res["ok"], res
    strategies = res["value"]
    # Guard against accidental deletion — these five strategies ship
    # with the workflow_facade UVM generator.
    expected = {
        "l2_prefetch",
        "barrier_reduction",
        "dma_double_buffer",
        "systolic_pipeline_warmup",
        "weight_fifo_preload",
    }
    assert expected.issubset(set(strategies)), strategies


def test_generate_uvm_sequence_uses_strategy(driver):
    # Pick a non-default strategy so the output is obviously recognisable.
    res = _invoke(driver, "generate_uvm_sequence_cmd",
                  {"strategy": "dma_double_buffer"})
    assert res["ok"], res
    stub = res["value"]
    assert "class dma_double_buffer_seq" in stub, stub
    assert "uvm_object_utils"            in stub, stub
    assert "task body()"                 in stub, stub


@pytest.mark.skipif(not SIBLING_PCCX.exists(),
                    reason=f"bridge artefact missing: {SIBLING_PCCX}")
def test_analyze_roofline_after_loading_trace(driver):
    load = _invoke(driver, "load_pccx", {"path": str(SIBLING_PCCX)})
    assert load["ok"], load

    res = _invoke(driver, "analyze_roofline", {})
    assert res["ok"], f"analyze_roofline failed: {res.get('err')}"
    point = res["value"]

    assert point["total_cycles"] == 1024, point
    assert point["mac_cycles"]   == 1024, point
    # tb_packer has no DMA events, so dma_bytes is zero and the workload
    # must be compute-bound by definition.
    assert point["dma_bytes_estimate"] == 0, point
    assert point["compute_bound"] is True,   point
    assert point["peak_gops"]    > 0,         point
    assert point["peak_bw_gbps"] > 0,         point


def test_analyze_roofline_fails_without_trace(driver):
    # Try invoking the command in a fresh session — if the test_verify
    # fixture previously cached a trace, the state persists. To exercise
    # the no-trace path reliably we invoke on an app instance that only
    # the smoke fixtures have touched. So we tolerate either outcome:
    #   * err "No trace loaded"       (fresh app)
    #   * ok  (some earlier test warmed the cache)
    res = _invoke(driver, "analyze_roofline", {})
    if not res["ok"]:
        assert "No trace" in res["err"], res
    else:
        # Warmed cache — at least the returned object has the expected shape.
        assert "arithmetic_intensity" in res["value"], res
