import hashlib
import io
import itertools
import tarfile
import zipfile
from collections import Counter

import pytest

from bass_pipeline.audit import inspect_archive, repository_path, safe_member
from bass_pipeline.core import (
    Note,
    Recording,
    excerpt_windows,
    notes_overlapping,
    onset_scores,
    plan_splits,
)


@pytest.mark.parametrize(
    "args",
    [
        (128, 0, 1),
        (True, 0, 1),
        (40, -1, 1),
        (40, 1, 1),
        (40, 0, float("nan")),
        (40, float("inf"), 2),
    ],
)
def test_invalid_notes(args):
    with pytest.raises(ValueError):
        Note(*args)


def test_group_splits_are_deterministic_and_per_dataset():
    rows = [
        Recording(f"{dataset}-{i}-{stem}", dataset, str(i), 10)
        for dataset in ("a", "b")
        for i in range(20)
        for stem in ("bass", "mix")
    ]
    splits = plan_splits(rows)
    assert splits == plan_splits(list(reversed(rows)))
    for dataset in ("a", "b"):
        assert Counter(splits[f"{dataset}-{i}-bass"] for i in range(20)) == {
            "train": 14,
            "validation": 3,
            "test": 3,
        }
        for i in range(20):
            assert splits[f"{dataset}-{i}-bass"] == splits[f"{dataset}-{i}-mix"]


def test_duplicate_ids_and_bad_ratios_rejected():
    row = Recording("a", "d", "song", 10)
    with pytest.raises(ValueError):
        plan_splits([row, row])
    with pytest.raises(ValueError):
        plan_splits([row], (0.8, 0.2, 0.2))
    assert plan_splits([]) == {}
    assert len(plan_splits([row])) == 1


def test_crops_preserve_carry_in_notes_and_do_not_invent_onsets():
    carry = Note(40, 1, 3)
    assert excerpt_windows(5, 2) == [(0, 2), (2, 4), (4, 5)]
    assert excerpt_windows(5, 2, False) == [(0, 2), (2, 4)]
    assert notes_overlapping([Note(41, 0, 2), carry, Note(42, 4, 5)], 2, 4) == [carry]
    assert carry.onset_seconds == 1


@pytest.mark.parametrize("duration,length", [(0, 2), (2, 0), (2, float("nan"))])
def test_bad_crop_dimensions(duration, length):
    with pytest.raises(ValueError):
        excerpt_windows(duration, length)


def test_scores_reject_octaves_duplicates_and_outside_tolerance():
    ref = [Note(40, 1, 2)]
    assert onset_scores(ref, [Note(40, 1.05, 2)])["f1"] == 1
    assert onset_scores(ref, [Note(40, 1.051, 2)])["f1"] == 0
    assert onset_scores(ref, [Note(52, 1, 2)])["f1"] == 0
    result = onset_scores(ref, ref * 2)
    assert result["true_positives"] == 1
    assert result["false_positives"] == 1
    assert onset_scores([], [])["f1"] == 0


def test_matching_agrees_with_exhaustive_small_cases():
    # Independent oracle checks one-to-one matching, including competing onsets.
    times = [0, 0.04, 0.08, 0.12]
    sets = [list(c) for k in range(4) for c in itertools.combinations(times, k)]
    for refs, preds in itertools.product(sets, repeat=2):
        best = 0
        for k in range(min(len(refs), len(preds)) + 1):
            for rs in itertools.combinations(refs, k):
                for ps in itertools.permutations(preds, k):
                    if all(abs(r - p) <= 0.05 for r, p in zip(rs, ps)):
                        best = max(best, k)
        result = onset_scores(
            [Note(40, t, t + 1) for t in refs],
            [Note(40, t, t + 1) for t in preds],
        )
        assert result["true_positives"] == best


@pytest.mark.parametrize(
    "name", ["../escape", "/absolute", "a/../../b", "C:/a", "a\\b"]
)
def test_unsafe_members(name):
    with pytest.raises(ValueError):
        safe_member(name)


@pytest.mark.parametrize("kind", ["zip", "tar"])
def test_archive_inventory_and_checksum(tmp_path, kind):
    path = tmp_path / ("example.zip" if kind == "zip" else "example.tar.gz")
    if kind == "zip":
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("song/label.mid", b"abc")
    else:
        with tarfile.open(path, "w:gz") as archive:
            member = tarfile.TarInfo("song/label.mid")
            member.size = 3
            archive.addfile(member, io.BytesIO(b"abc"))
    checksum = hashlib.md5(path.read_bytes(), usedforsecurity=False).hexdigest()
    result = inspect_archive(path, checksum)
    assert result["file_count"] == 1
    assert result["uncompressed_bytes"] == 3
    assert result["extensions"] == {".mid": 1}
    assert not (tmp_path / "song").exists()
    with pytest.raises(ValueError, match="checksum"):
        inspect_archive(path, "incorrect")


def test_archive_link_rejected(tmp_path):
    path = tmp_path / "link.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        member = tarfile.TarInfo("link")
        member.type = tarfile.SYMTYPE
        member.linkname = "/outside"
        archive.addfile(member)
    checksum = hashlib.md5(path.read_bytes(), usedforsecurity=False).hexdigest()
    with pytest.raises(ValueError, match="links"):
        inspect_archive(path, checksum)


def test_repository_boundary_includes_symlinks(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "link").symlink_to(tmp_path, target_is_directory=True)
    assert repository_path(root, "outputs/result.json") == root / "outputs/result.json"
    for relative in ("../outside", "link/outside", str(tmp_path / "absolute")):
        with pytest.raises(ValueError):
            repository_path(root, relative)
