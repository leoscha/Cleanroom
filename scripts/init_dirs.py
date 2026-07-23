from pathlib import Path

DIRECTORIES = ("dirty", "spotless", "spotless/quarantine", "processed", "failed", "reports")
for name in DIRECTORIES:
    Path(name).mkdir(parents=True, exist_ok=True)
print("Cleanroom directories initialized")
