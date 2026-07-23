from pathlib import Path

source = Path("sample-customer-notes.txt")
destination = Path("dirty") / source.name
destination.parent.mkdir(parents=True, exist_ok=True)
if destination.exists():
    raise SystemExit(f"Refusing to overwrite {destination}")
destination.write_bytes(source.read_bytes())
print(f"Created {destination}")
