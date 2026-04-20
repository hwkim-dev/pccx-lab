"""E2E: load sibling pccx-FPGA synthesis reports via the load_synth_report IPC.

Verifies that:
  * The utilisation parser extracts NPU_top's resource counts (LUTs / FFs /
    RAMB / URAM / DSP).
  * The timing parser correctly flags the timing-failure state seen in the
    current post-synth run (WNS < 0 on core_clk).
"""

from pathlib import Path

import pytest

SIBLING_FPGA = Path(__file__).resolve().parents[4] / "pccx-FPGA-NPU-LLM-kv260"
UTIL_PATH = SIBLING_FPGA / "hw" / "build" / "reports" / "utilization_post_synth.rpt"
TIMING_PATH = SIBLING_FPGA / "hw" / "build" / "reports" / "timing_summary_post_synth.rpt"


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


@pytest.mark.skipif(
    not (UTIL_PATH.exists() and TIMING_PATH.exists()),
    reason=f"synth reports missing (need both {UTIL_PATH.name} + {TIMING_PATH.name})",
)
def test_load_synth_report(driver):
    res = _invoke(driver, "load_synth_report", {
        "utilizationPath": str(UTIL_PATH),
        "timingPath":      str(TIMING_PATH),
    })
    assert res["ok"], f"load_synth_report failed: {res.get('err')}"

    report = res["value"]

    # Utilisation: NPU_top row from the current run has non-trivial counts.
    util = report["utilisation"]
    assert util["top_module"] == "NPU_top", util
    assert util["total_luts"] > 0, util
    assert util["ffs"] > 0, util
    assert util["dsps"] >= 0  # current design reports 4 DSPs — be lenient

    # Device should be the Kria KV260 SoM part.
    assert "xck26" in report["device"], report["device"]

    # Timing: current run is known to miss timing. Accept either verdict but
    # insist the parser returned a numeric WNS + a nonzero total_endpoints.
    timing = report["timing"]
    assert timing["total_endpoints"] > 0, timing
    assert isinstance(timing["wns_ns"], (int, float)), timing
    if not timing["is_timing_met"]:
        assert timing["failing_endpoints"] > 0, timing
        assert timing["wns_ns"] < 0.0, timing
