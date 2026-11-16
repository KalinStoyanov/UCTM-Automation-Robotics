import asyncio
import json
from pathlib import Path

from go2_webrtc import LIVE_ENABLED
from go2_telemetry import TELEMETRY_TOPICS
from go2_telemetry_session import Go2TelemetrySession


async def validate():
    results = {}

    session = Go2TelemetrySession()

    # A.14: Initialization
    assert session.adapter.state == "DISCONNECTED"
    assert session.subscribed is False
    results["A14_initialization"] = "PASS"

    # A.15: Telemetry topics
    assert len(TELEMETRY_TOPICS) == 5
    assert len(set(TELEMETRY_TOPICS.values())) == 5
    results["A15_topics"] = "PASS"

    # A.16: Callback and message filtering
    for topic in TELEMETRY_TOPICS.values():
        session.receiver.on_message({
            "topic": topic,
            "data": {"offline_test": True},
        })

    session.receiver.on_message({
        "topic": "unknown/topic",
        "data": {},
    })

    assert len(session.receiver.messages) == 5
    assert all(
        session.receiver.counts[topic] == 1
        for topic in TELEMETRY_TOPICS.values()
    )
    results["A16_callbacks"] = "PASS"

    # A.17: LIVE connection must remain disabled
    assert LIVE_ENABLED is False

    try:
        await session.connect()
    except RuntimeError as exc:
        assert "disabled" in str(exc).lower()
    else:
        raise AssertionError("LIVE connection was not blocked")

    assert session.adapter.state == "DISCONNECTED"
    results["A17_live_guard"] = "PASS"

    # A.18: Safe offline disconnect
    await session.disconnect()

    assert session.adapter.state == "DISCONNECTED"
    assert session.subscribed is False
    results["A18_disconnect"] = "PASS"

    report = {
        "milestone": "M24-A",
        "mode": "OFFLINE",
        "live_enabled": LIVE_ENABLED,
        "results": results,
        "snapshot": session.snapshot(),
    }

    path = Path("results/m24/offline_report.json")
    path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print("\n=== M24-A FINAL VALIDATION ===")
    for name, status in results.items():
        print(f"{name}: {status}")

    print("TOTAL:", len(results), "/", len(results), "PASS")
    print("REPORT:", path)


asyncio.run(validate())
