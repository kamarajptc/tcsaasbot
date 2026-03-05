#!/usr/bin/env python3
import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET


def parse_junit(path: Path) -> dict:
    if not path.exists():
        return {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "duration_s": 0.0,
            "modules": [],
            "failures": [],
            "test_results": [],
        }

    root = ET.parse(path).getroot()
    suite = root.find("testsuite") if root.tag != "testsuite" else root
    tests = int(suite.attrib.get("tests", "0"))
    failures = int(suite.attrib.get("failures", "0"))
    errors = int(suite.attrib.get("errors", "0"))
    skipped = int(suite.attrib.get("skipped", suite.attrib.get("skip", "0")))
    duration = float(suite.attrib.get("time", "0") or 0)
    passed = max(0, tests - failures - errors - skipped)

    modules = {}
    failures_rows = []
    test_results = []
    for tc in suite.findall(".//testcase"):
        classname = tc.attrib.get("classname", "unknown")
        module = classname.split(".")[0] if "." in classname else classname
        test_id = f"{classname}::{tc.attrib.get('name', 'unknown')}"
        row = modules.setdefault(module, {"module": module, "total": 0, "failed": 0, "duration_s": 0.0})
        row["total"] += 1
        row["duration_s"] += float(tc.attrib.get("time", "0") or 0)
        fail_node = tc.find("failure") or tc.find("error")
        is_failed = fail_node is not None
        test_results.append({"test_id": test_id, "failed": is_failed})
        if is_failed:
            row["failed"] += 1
            failures_rows.append(
                {
                    "test_id": test_id,
                    "module": module,
                    "message": (fail_node.attrib.get("message") or fail_node.text or "")[:1200],
                }
            )

    return {
        "total": tests,
        "passed": passed,
        "failed": failures,
        "errors": errors,
        "skipped": skipped,
        "duration_s": round(duration, 2),
        "modules": sorted(modules.values(), key=lambda x: (x["failed"], x["module"]), reverse=True),
        "failures": failures_rows,
        "test_results": test_results,
    }


def main() -> int:
    if len(sys.argv) != 4:
        print("Usage: build_pytest_summary.py <junit.xml> <summary.json> <status>")
        return 2
    junit_path = Path(sys.argv[1])
    summary_path = Path(sys.argv[2])
    status = sys.argv[3]
    parsed = parse_junit(junit_path)
    summary = {
        "status": status,
        "pytest": parsed,
    }
    summary_path.write_text(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

