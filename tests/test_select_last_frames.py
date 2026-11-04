"""Tests for tools/select_last_frames.py using the naming pattern written by TrueBeam Developer Mode."""
import sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import select_last_frames as slf  # noqa: E402

# File names from a real Imaging W-L session (empty placeholders are enough: selection uses names only)
SESSION = ["isocal_-000-0000", "isocal_-000-0107", "isocal_-001", "isocal_-002-0000", "isocal_-002-0048",
           "isocal_-003", "isocal_-004-0000", "isocal_-004-0106", "isocal_-005", "isocal_-006-0000",
           "isocal_-006-0119", "isocal_-007", "isocal_-013", "isocal_-014", "isocal_-015-0000", "isocal_-015-0118"]


def make(tmp, names):
    for n in names:
        (Path(tmp) / f"{n}.dcm").write_bytes(b"")
    return sorted(Path(tmp).glob("*.dcm"))


def test_last_frame_per_acquisition():
    with tempfile.TemporaryDirectory() as tmp:
        chosen, unmatched = slf.select(make(tmp, SESSION))
        names = {acq: p.name for (_, acq), (p, _, _) in chosen.items()}
        assert names[0] == "isocal_-000-0107.dcm" and names[2] == "isocal_-002-0048.dcm"
        assert names[6] == "isocal_-006-0119.dcm" and names[15] == "isocal_-015-0118.dcm"
        assert names[1] == "isocal_-001.dcm" and names[14] == "isocal_-014.dcm"     # single-frame kV images
        assert len(chosen) == 11 and not unmatched


def test_hyphenated_series_name_and_dry_run():
    with tempfile.TemporaryDirectory() as tmp:
        files = make(tmp, ["TB3-WL-2026-000-0000", "TB3-WL-2026-000-0012", "TB3-WL-2026-001", "notes"])
        chosen, _ = slf.select(files)
        assert {k: v[0].name for k, v in chosen.items()} == {
            ("TB3-WL-2026", 0): "TB3-WL-2026-000-0012.dcm", ("TB3-WL-2026", 1): "TB3-WL-2026-001.dcm"}
        slf.main([tmp, "--dry-run"])
        assert not (Path(tmp) / "last_frames").exists()


def test_copy_leaves_originals():
    with tempfile.TemporaryDirectory() as tmp:
        make(tmp, SESSION)
        slf.main([tmp])
        out = sorted(p.name for p in (Path(tmp) / "last_frames").glob("*.dcm"))
        assert len(out) == 11 and len(list(Path(tmp).glob("*.dcm"))) == len(SESSION)



def test_rename_from_header():
    import pydicom
    from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid
    with tempfile.TemporaryDirectory() as tmp:
        def rt_image(name, gantry, kvp=None):
            meta = FileMetaDataset(); meta.TransferSyntaxUID = ExplicitVRLittleEndian
            meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.481.1"; meta.MediaStorageSOPInstanceUID = generate_uid()
            ds = FileDataset(name, {}, file_meta=meta, preamble=b"\0" * 128)
            ds.SOPClassUID, ds.SOPInstanceUID = meta.MediaStorageSOPClassUID, meta.MediaStorageSOPInstanceUID
            ds.GantryAngle, ds.BeamLimitingDeviceAngle, ds.PatientSupportAngle = gantry, 0.0, 270.0
            if kvp:
                e = Dataset(); e.KVP = kvp; ds.ExposureSequence = pydicom.sequence.Sequence([e])
            ds.save_as(Path(tmp) / name, write_like_original=False)
        rt_image("s-000-0000.dcm", 315.5); rt_image("s-000-0107.dcm", 315.5); rt_image("s-001.dcm", 315.5, kvp=100)
        slf.main([tmp, "--rename"])
        out = sorted(p.name for p in (Path(tmp) / "last_frames").glob("*.dcm"))
        assert out == ["acq000_G315.5_C0_T270_MV.dcm", "acq001_G315.5_C0_T270_kV100.dcm"], out


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("PASS", name)
