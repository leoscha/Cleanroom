"""Generate privacy-safe terminal screenshots and the animated README demo."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
SCREENSHOTS = ASSETS / "screenshots"
WIDTH, HEIGHT = 1280, 720
BACKGROUND = "#0b1220"
PANEL = "#111c2f"
TEXT = "#dbeafe"
MUTED = "#94a3b8"
BLUE = "#60a5fa"
GREEN = "#4ade80"
YELLOW = "#facc15"


SESSIONS: dict[str, list[tuple[str, str]]] = {
    "doctor": [
        ("$ cleanroom doctor", BLUE),
        ("", TEXT),
        ("Cleanroom Doctor", TEXT),
        ("✓ Configuration loaded", GREEN),
        ("✓ Workspace directories writable", GREEN),
        ("✓ Policy valid", GREEN),
        ("✓ SQLite available", GREEN),
        ("", TEXT),
        ("Ollama", TEXT),
        ("✓ Connection mode: Local", GREEN),
        ("✓ Endpoint: http://127.0.0.1:11434", GREEN),
        ("✓ Endpoint classification: Loopback", GREEN),
        ("✓ Ollama reachable", GREEN),
        ("✓ Model installed: gemma3:4b", GREEN),
        ("✓ Structured output supported", GREEN),
        ("", TEXT),
        ("Cleanroom is ready.", GREEN),
    ],
    "scan": [
        ("$ cp demo/customer.txt dirty/", BLUE),
        ("$ cleanroom scan", BLUE),
        ("", TEXT),
        ("Scanning dirty/", TEXT),
        ("1 supported file found", TEXT),
        ("1 file processed", TEXT),
        ("", TEXT),
        ("✓ customer.txt                 completed      6 findings", GREEN),
        ("", TEXT),
        ("Summary", TEXT),
        ("Completed: 1", GREEN),
        ("Quarantined: 0", TEXT),
        ("Failed: 0", TEXT),
        ("Skipped: 0", MUTED),
        ("", TEXT),
        ("spotless/customer-clean.txt", BLUE),
        ("reports/customer-report.md", BLUE),
    ],
    "status": [
        ("$ cleanroom status --limit 3", BLUE),
        ("", TEXT),
        ("                         Cleanroom Jobs", TEXT),
        ("Job      Filename        Type  Status      Findings  Model", MUTED),
        ("────────  ──────────────  ────  ──────────  ────────  ─────────", MUTED),
        ("a17c42e9  customer.txt    txt   completed          6  gemma3:4b", GREEN),
        ("c34e0bd1  employee.txt    txt   quarantined        7  gemma3:4b", YELLOW),
        ("f98410ac  invoice.txt     txt   completed          5  gemma3:4b", GREEN),
        ("", TEXT),
        ("Pending supported files: 0", MUTED),
    ],
    "show": [
        ("$ cleanroom show a17c42e9", BLUE),
        ("", TEXT),
        ('{', TEXT),
        ('  "id": "a17c42e9-demo-job",', TEXT),
        ('  "source_filename": "customer.txt",', TEXT),
        ('  "status": "completed",', GREEN),
        ('  "findings_count": 6,', TEXT),
        ('  "model": "gemma3:4b",', TEXT),
        ('  "verification": {"passed": true},', GREEN),
        ('  "findings_by_category": {', TEXT),
        ('    "EMAIL": 1, "PHONE": 1, "PERSON_NAME": 1,', TEXT),
        ('    "ADDRESS": 1, "PROJECT_NAME": 1, "INDIRECT_IDENTIFIER": 1', TEXT),
        ('  },', TEXT),
        ('  "quarantine_reason": null', TEXT),
        ('}', TEXT),
        ("", TEXT),
        ("Matched plaintext is never included in this view.", MUTED),
    ],
    "evaluate": [
        ("$ cleanroom evaluate --detector combined --model gemma3:4b", BLUE),
        ("", TEXT),
        ("Synthetic evaluation dataset: 7 TXT cases", MUTED),
        ("Precision: 0.714", GREEN),
        ("Recall: 0.833", GREEN),
        ("F1: 0.769", GREEN),
        ("Required recall: 1.000", GREEN),
        ("Invalid model responses/findings: 0", GREEN),
        ("", TEXT),
        ("Evaluation thresholds passed.", GREEN),
        ("", TEXT),
        ("Results: evaluation-results/summary.json", BLUE),
        ("Hardware and model builds affect timing and contextual findings.", MUTED),
    ],
}


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Monaco.ttf",
        "/System/Library/Fonts/SFNSMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def render(name: str, lines: list[tuple[str, str]]) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((32, 28, WIDTH - 32, HEIGHT - 28), radius=22, fill=PANEL,
                           outline="#263752", width=2)
    for index, color in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        x = 62 + index * 30
        draw.ellipse((x, 54, x + 15, 69), fill=color)
    draw.text((WIDTH - 250, 49), f"cleanroom · {name}", font=_font(17), fill=MUTED)
    draw.line((48, 91, WIDTH - 48, 91), fill="#263752", width=2)
    font = _font(20)
    y = 116
    for line, color in lines:
        draw.text((70, y), line, font=font, fill=color)
        y += 28
    draw.text((70, HEIGHT - 62), "Synthetic demonstration — no real personal data",
              font=_font(16), fill=MUTED)
    return image


def main() -> None:
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    frames: list[Image.Image] = []
    for name, lines in SESSIONS.items():
        image = render(name, lines)
        image.save(SCREENSHOTS / f"{name}.png", optimize=True)
        frames.append(image)
    frames[0].save(
        ASSETS / "terminal-demo.gif",
        save_all=True,
        append_images=frames[1:],
        duration=[2200] * len(frames),
        loop=0,
        optimize=True,
    )


if __name__ == "__main__":
    main()
