"""
Quick pre-flight check for a widget file (no dependencies).

    python3 tools/check_widget.py examples/widgets/*.html

- size exactly as the server measures it (zlib level 9)
- heuristic warnings for the mistakes that most often break a widget.
  Heuristics only: the authoritative check is the official sandbox harness
  (see README, "Testing").
"""
import re
import sys
import zlib

MAX_RAW, MAX_ZLIB = 32768, 4096

CHECKS = [
    (r"opacity\s*:\s*(0?\.\d+|0)\b", "opacity < 1 makes a box 'heavy' (paint limit 16). Prefer rgba()/fill-opacity."),
    (r"@keyframes[^{]*\{[^}]*opacity", "animating opacity makes a box heavy for the whole animation. Animate transform."),
    (r"filter\s*:\s*(?!none)", "filter/backdrop-filter makes a box heavy (paint limit 16)."),
    (r"box-shadow\s*:[^;}]*\d+px\s+\d+px\s+[1-9]", "blurred box-shadow makes a box heavy (paint limit 16)."),
    (r"\d+(\.\d+)?d?s?vh\b", "vh units are out of the profile; use px, % or flex."),
    (r"text-shadow", "text-shadow is removed by the client."),
    (r"clip-path", "clip-path is removed by the client."),
    (r"background-clip\s*:\s*text", "background-clip: text is removed by the client."),
    (r"@font-face|@import", "@font-face / @import are removed: only system font families."),
    (r"(src|href)\s*=\s*[\"']https?:", "external resources are never loaded (no network)."),
    (r"\bfetch\(|XMLHttpRequest|WebSocket", "network APIs throw NetworkDisabledError."),
    (r"<(input|select|textarea)\b", "form controls are removed (no keyboard input in widgets)."),
    (r"rotate[XY]\(|translateZ|perspective|matrix3d", "3D transforms are removed."),
    (r"position\s*:\s*sticky", "position: sticky is removed."),
]


def check(path):
    raw = open(path, "rb").read()
    text = raw.decode("utf-8", "replace")
    z = len(zlib.compress(raw, 9))
    ok = len(raw) <= MAX_RAW and z <= MAX_ZLIB
    print(f"{path}\n  size: {len(raw)} B raw / {z} B zlib (limit {MAX_RAW} / {MAX_ZLIB}) {'OK' if ok else 'TOO LARGE'}")
    if not re.search(r"body\s*\{[^}]*margin\s*:\s*0", text):
        print("  warn: body margin not reset -> the client's ~8px 12px text padding shifts your layout")
    for rx, msg in CHECKS:
        n = len(re.findall(rx, text, re.I))
        if n:
            print(f"  warn: {msg} ({n}x)")
    return ok


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(0 if all([check(p) for p in sys.argv[1:]]) else 1)
