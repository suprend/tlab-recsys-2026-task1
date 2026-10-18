"""Fetch pinned original H&M tables from a documented mirror, verifying LFS SHA256.

The checksum authenticates the chosen mirror bytes, not independent equality with Kaggle.
Only the three original CSV tables are fetched; synthetic search data are excluded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download(config_path: Path, output: Path) -> dict:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    allowed = {"articles.csv", "customers.csv", "transactions_train.csv"}
    files = config["files"]
    names = [Path(spec["path"]).name for spec in files]
    if set(names) != allowed or len(names) != len(allowed):
        raise ValueError("Source config must contain exactly the three original CSV tables")
    if any(spec["path"] != "data/raw/" + name for spec, name in zip(files, names)):
        raise ValueError("Unexpected upstream path")
    output.mkdir(parents=True, exist_ok=True)
    needed = sum(spec["size"] for spec, name in zip(files, names) if not (output / name).exists())
    if shutil.disk_usage(output).free < needed + 2 * 1024**3:
        raise RuntimeError("Insufficient disk space for source tables and 2 GiB reserve")
    manifest = {
        "dataset": config["dataset"], "mirror": config["mirror"],
        "revision": config["revision"], "original_url": config["original_url"],
        "rules_url": config["rules_url"], "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "checksum_scope": "pinned mirror LFS identity; Kaggle byte equality not independently checked",
        "files": [], "status": "running",
    }
    receipt = output / "download.json"
    if receipt.exists():
        previous = json.loads(receipt.read_text(encoding="utf-8"))
        if previous.get("revision") != config["revision"] or previous.get("mirror") != config["mirror"]:
            raise ValueError("Existing receipt refers to another source")
    try:
        for spec, name in zip(files, names):
            target = output / name
            if target.exists():
                digest = sha256(target)
                if target.stat().st_size != spec["size"] or digest != spec["sha256"]:
                    raise ValueError(f"Existing {name} differs from pinned source; preserved")
                print(f"Verified existing {name}", flush=True)
            else:
                partial = target.with_suffix(target.suffix + ".part")
                url = f"https://huggingface.co/datasets/{config['mirror']}/resolve/{config['revision']}/{spec['path']}?download=true"
                request = Request(url, headers={"User-Agent": "tlab-recsys-research/0.1"})
                digest_state = hashlib.sha256()
                started = last_update = time.monotonic()
                total = 0
                # Exclusive creation protects partial downloads from an accidental rerun.
                with partial.open("xb") as sink, urlopen(request, timeout=60) as source:
                    while chunk := source.read(8 * 1024**2):
                        total += len(chunk)
                        if total > spec["size"]:
                            raise ValueError(f"{name}: upstream exceeded expected byte count")
                        sink.write(chunk)
                        digest_state.update(chunk)
                        now = time.monotonic()
                        if now - last_update >= 15:
                            print(f"{name}: {total / spec['size']:.1%}, {total/1024**2:.0f} MiB, {total/1024**2/(now-started):.1f} MiB/s", flush=True)
                            last_update = now
                digest = digest_state.hexdigest()
                if total != spec["size"] or digest != spec["sha256"]:
                    raise ValueError(f"{name}: byte count or SHA256 mismatch; partial preserved")
                # Path.rename on Windows does not replace an existing destination.
                partial.rename(target)
                print(f"Downloaded and SHA256-verified {name}: {total} bytes", flush=True)
            manifest["files"].append({"name": name, "size": target.stat().st_size, "sha256": digest})
            receipt.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        manifest["status"] = "complete"
    except BaseException as exc:
        manifest["status"] = "failed"
        manifest["error_type"] = type(exc).__name__
        raise
    finally:
        manifest["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        receipt.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = download(args.config, args.output)
    print(json.dumps({"status": result["status"], "files": len(result["files"])}))


if __name__ == "__main__":
    main()
