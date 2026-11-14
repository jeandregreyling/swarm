import os
import sys
import json
import fnmatch
from huggingface_hub import HfApi, snapshot_download

# Manifest describing the three datasets to ingest
MANIFEST = [
    {
        "repo_id": "JetBrains/Kotlin_QA",
        "revision": "bc09ab4a3475f3d6e6caa40ebf7a0f4f5dacb21c",
        "patterns": ["README.md", "Kotlin_QA_version_parquet.parquet"],
        "license": None,
    },
    {
        "repo_id": "Inserloft/PyMini",
        "revision": "3076c2d21cbda27d3e7264dccdd057affb02502a",
        "patterns": ["train-*.parquet"],
        "license": "mit",
    },
    {
        "repo_id": "wikimedia/wikipedia",
        "revision": "b04c8d1ceb2f5cd4588862100d08de323dccfbaa",
        "patterns": ["20231101.en/*.parquet"],
        "license": ["cc-by-sa-3.0", "gfdl"],
    },
]

BASE_DIR = "/mnt/archive/projects/datasets/hf_cache"


def preflight():
    api = HfApi(token=False)
    total_bytes = 0
    stat = os.statvfs("/mnt/archive/projects")
    free_bytes = stat.f_bavail * stat.f_frsize
    report = {"repos": []}

    for entry in MANIFEST:
        info = api.dataset_info(entry["repo_id"], revision=entry["revision"], files_metadata=True)
        selected = []
        for f in info.siblings:
            if any(fnmatch.fnmatch(f.rfilename, pat) for pat in entry["patterns"]) or f.rfilename == "README.md":
                selected.append(f)
        # Verify license for each selected file
        for f in selected:
            license = f.card_data.get("license") if f.card_data else None
            if entry["license"]:
                if isinstance(entry["license"], list):
                    if license not in entry["license"]:
                        raise RuntimeError(f"License mismatch for {f.rfilename} in {entry['repo_id']}")
                else:
                    if license != entry["license"]:
                        raise RuntimeError(f"License mismatch for {f.rfilename} in {entry['repo_id']}")
        repo_total = sum(f.size for f in selected)
        total_bytes += repo_total
        report["repos"].append({
            "repo_id": entry["repo_id"],
            "revision": entry["revision"],
            "files": [f.rfilename for f in selected],
            "total": repo_total,
            "license": entry["license"],
        })

    if total_bytes > 500 * 1024**3:
        raise RuntimeError("Total size exceeds 500 GiB")
    if free_bytes < total_bytes + 1024**3:
        raise RuntimeError("Insufficient free space")

    report["total"] = total_bytes
    report["free"] = free_bytes
    print(json.dumps(report), flush=True)


def download():
    api = HfApi(token=False)
    for entry in MANIFEST:
        print(json.dumps({"status": "start", "repo_id": entry["repo_id"], "revision": entry["revision"]}), flush=True)
        local_dir = os.path.join(BASE_DIR, entry["repo_id"])
        snapshot_download(
            repo_id=entry["repo_id"],
            repo_type="dataset",
            revision=entry["revision"],
            allow_patterns=entry["patterns"],
            token=False,
            local_dir=local_dir,
        )
        # Verify each selected file size
        info = api.dataset_info(entry["repo_id"], revision=entry["revision"], files_metadata=True)
        for f in info.siblings:
            if any(fnmatch.fnmatch(f.rfilename, pat) for pat in entry["patterns"]) or f.rfilename == "README.md":
                local_path = os.path.join(local_dir, f.rfilename)
                if not os.path.exists(local_path):
                    raise RuntimeError(f"Missing file {f.rfilename} in {entry['repo_id']}")
                actual_size = os.path.getsize(local_path)
                if actual_size != f.size:
                    raise RuntimeError(f"Size mismatch for {f.rfilename} in {entry['repo_id']}")
        print(json.dumps({"status": "complete", "repo_id": entry["repo_id"]}), flush=True)


if __name__ == "__main__":
    preflight()
    if "--download" in sys.argv:
        download()
