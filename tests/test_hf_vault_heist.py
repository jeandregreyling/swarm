import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

import hf_vault_heist as vault


def file(name, body=b"data", *, lfs=True):
    digest = hashlib.sha256(body).hexdigest() if lfs else hashlib.sha1(
        f"blob {len(body)}\0".encode() + body).hexdigest()
    return SimpleNamespace(rfilename=name, size=len(body), blob_id=digest,
                           lfs=SimpleNamespace(sha256=digest) if lfs else None)


def api_for(repo, files):
    kind, revision, license_id = vault.TARGETS[repo]

    def info(name, **kwargs):
        assert name == repo
        assert kwargs == dict(repo_type=kind, revision=revision, files_metadata=True)
        return SimpleNamespace(sha=revision, gated=False,
                               card_data={"license": license_id}, siblings=files)
    return SimpleNamespace(repo_info=info)


def test_selects_two_complete_quantizations_not_splits_or_other_weights():
    files = [file(name) for name in (
        "model-Q4_K_M.gguf", "model-Q8_0.gguf", "model-Q6_K.gguf",
        "model-q4_k_m-00001-of-00002.gguf", "README.md", "LICENSE")]
    assert [f.rfilename for f in vault.selected_files(SimpleNamespace(siblings=files), "model")] == [
        "model-Q4_K_M.gguf", "model-Q8_0.gguf", "README.md", "LICENSE"]
    with pytest.raises(ValueError, match="exactly one"):
        vault.selected_files(SimpleNamespace(siblings=[file("split-00001.gguf")]), "model")


@pytest.mark.parametrize("name", ["../outside", "/absolute", "a/../../outside", "a\\..\\outside"])
def test_rejects_traversal(tmp_path, name):
    with pytest.raises(ValueError, match="Unsafe"):
        vault.contained(tmp_path, name)


def test_rejects_symlink_escape(tmp_path):
    (tmp_path / "escape").symlink_to(tmp_path.parent, target_is_directory=True)
    with pytest.raises(ValueError, match="escapes"):
        vault.contained(tmp_path, "escape/file")


def test_requires_real_mount(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "is_mount", lambda _: False)
    with pytest.raises(ValueError, match="not mounted"):
        vault.validate_destination(tmp_path / "vault", tmp_path)


def test_rejects_unreviewed_licenses(tmp_path):
    kwargs = dict(accept_llama=False, max_bytes=1000, reserve_bytes=1)
    with pytest.raises(ValueError, match="separate review"):
        vault.preflight(None, ["bigcode/the-stack-smol"], tmp_path, **kwargs)
    with pytest.raises(ValueError, match="accept-llama"):
        vault.preflight(None, ["bartowski/Meta-Llama-3.1-8B-Instruct-GGUF"], tmp_path, **kwargs)


def test_dataset_kind_budget_and_integrity(tmp_path):
    repo = "HuggingFaceH4/ultrachat_200k"
    files = [file("data.parquet"), file("README.md", lfs=False)]
    plan = vault.preflight(api_for(repo, files), [repo], tmp_path, accept_llama=False,
                           max_bytes=8, reserve_bytes=1)
    entry = plan[0]
    directory = Path(entry["directory"])
    directory.mkdir(parents=True)
    for f in files:
        (directory / f.rfilename).write_bytes(b"data")
    assert all(vault.verify_file(directory, item)["source_integrity_verified"]
               for item in entry["files"])
    (directory / "data.parquet").write_bytes(b"fake")
    with pytest.raises(ValueError, match="hash mismatch"):
        vault.verify_file(directory, entry["files"][0])
    with pytest.raises(ValueError, match="above budget"):
        vault.preflight(api_for(repo, files), [repo], tmp_path, accept_llama=False,
                        max_bytes=7, reserve_bytes=1)


def test_disk_reserve_is_enforced(monkeypatch, tmp_path):
    monkeypatch.setattr(vault.shutil, "disk_usage", lambda _: SimpleNamespace(free=100))
    vault.check_space(tmp_path, 90, 10)
    with pytest.raises(ValueError, match="Insufficient"):
        vault.check_space(tmp_path, 91, 10)


def test_download_verifies_and_reads_back_receipt(monkeypatch, tmp_path):
    repo = "HuggingFaceH4/ultrachat_200k"
    plan = vault.preflight(api_for(repo, [file("data.parquet")]), [repo], tmp_path,
                           accept_llama=False, max_bytes=100, reserve_bytes=1)
    monkeypatch.setattr(vault, "validate_destination", lambda path: path)
    calls = []

    def download(**kwargs):
        calls.append(kwargs)
        path = Path(kwargs["local_dir"])
        path.mkdir(parents=True)
        (path / "data.parquet").write_bytes(b"data")
    vault.download_plan(plan, tmp_path, download, workers=2, reserve_bytes=1)
    assert calls[0]["repo_type"] == "dataset"
    assert calls[0]["revision"] == vault.TARGETS[repo][1]
    assert calls[0]["allow_patterns"] == ["data.parquet"]
    assert (Path(plan[0]["directory"]) / "archive-receipt.json").is_file()
