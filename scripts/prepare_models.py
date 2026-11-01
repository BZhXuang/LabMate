"""Download pinned BGE snapshots locally and configure this checkout to use them."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    "LOCAL_EMBEDDING_MODEL": (
        "BAAI/bge-small-zh-v1.5",
        "7999e1d3359715c523056ef9478215996d62a620",
    ),
    "CROSS_ENCODER_MODEL": (
        "BAAI/bge-reranker-base",
        "2cfc18c9415c912f9d8155881c133215df768a70",
    ),
}
CONFIG_FILES = {
    "config.json",
    "config_sentence_transformers.json",
    "modules.json",
    "sentence_bert_config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "vocab.txt",
    "sentencepiece.bpe.model",
    "1_Pooling/config.json",
    "README.md",
    "LICENSE",
}


def configure_env(values: dict[str, str]) -> None:
    """Change only model settings; preserve all unrelated settings and secrets."""
    path = ROOT / ".env"
    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []
    remaining = dict(values)
    output = []
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if key in values:
            if key in remaining:
                output.append(f"{key}={remaining.pop(key)}")
        else:
            output.append(line)
    output.extend(f"{key}={value}" for key, value in remaining.items())
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="https://huggingface.co")
    args = parser.parse_args()
    os.environ.setdefault("HF_HOME", str(ROOT / "data/local/huggingface"))
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "120")
    from huggingface_hub import HfApi, snapshot_download

    api = HfApi(endpoint=args.endpoint)
    manifest = {"downloaded_at": datetime.now(UTC).isoformat(), "models": []}
    settings = {"LOCAL_EMBEDDING_ENABLED": "true", "CROSS_ENCODER_ENABLED": "true"}
    for key, (repo_id, revision) in MODELS.items():
        print(f"Resolving {repo_id}", flush=True)
        info = api.model_info(repo_id, revision=revision, timeout=30)
        if info.sha != revision:
            raise RuntimeError(f"Model revision mismatch for {repo_id}")
        names = {item.rfilename for item in info.siblings}
        weights = "model.safetensors" if "model.safetensors" in names else "pytorch_model.bin"
        if weights not in names:
            raise RuntimeError(f"No supported model weights in {repo_id}")
        selected = sorted((CONFIG_FILES & names) | {weights})
        relative = Path("data/local/models") / repo_id.rsplit("/", 1)[1]
        local_dir = ROOT / relative
        snapshot_download(
            repo_id,
            revision=info.sha,
            endpoint=args.endpoint,
            local_dir=local_dir,
            allow_patterns=selected,
            max_workers=3,
            etag_timeout=30,
        )
        files = []
        for name in selected:
            path = local_dir / name
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            files.append({"name": name, "bytes": path.stat().st_size, "sha256": digest})
        manifest["models"].append(
            {"repo_id": repo_id, "revision": info.sha, "path": relative.as_posix(), "files": files}
        )
        settings[key] = relative.as_posix()
        print(f"Downloaded {repo_id} at {info.sha}", flush=True)
    output = ROOT / "data/local/models/manifest.json"
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    configure_env(settings)
    print("Both snapshots verified; model paths saved to .env. No secrets printed.", flush=True)


if __name__ == "__main__":
    main()
