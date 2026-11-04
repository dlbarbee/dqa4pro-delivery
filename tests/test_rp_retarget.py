"""Tests for tools/rp_retarget.py on a synthetic TrueBeam RT Plan (no real plan data needed).

Run:  python -m pytest tests   (or)   python tests/test_rp_retarget.py
"""
import sys, tempfile
from pathlib import Path

import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import rp_retarget as rr  # noqa: E402

RTPLAN = "1.2.840.10008.5.1.4.1.1.481.5"


def m120_bounds():
    w = [10.0] * 10 + [5.0] * 40 + [10.0] * 10
    return (np.concatenate([[0], np.cumsum(w)]) - 200).tolist()


def make_plan(path, aperture_y=(75.0, 95.0), aperture_x=(70.0, 90.0)):
    """One 6X beam, 2 control points, MLC aperture 2 x 2 cm centred ~8 cm off-axis (like a fiducial field)."""
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID, meta.MediaStorageSOPInstanceUID = RTPLAN, generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID, ds.SOPInstanceUID = RTPLAN, meta.MediaStorageSOPInstanceUID
    ds.StudyInstanceUID, ds.SeriesInstanceUID, ds.FrameOfReferenceUID = generate_uid(), generate_uid(), generate_uid()
    ds.Modality = "RTPLAN"
    ds.PatientName, ds.PatientID, ds.PatientBirthDate = "Real^Person", "MRN123456", "19700101"
    ds.InstitutionName, ds.StationName, ds.OperatorsName = "Some Hospital", "TB3-CONSOLE", "Physicist^A"
    ds.RTPlanLabel, ds.RTPlanName, ds.RTPlanDate, ds.ApprovalStatus = "AMWL", "AM WL", "20260115", "APPROVED"
    ref = Dataset(); ref.ReferencedSOPInstanceUID = generate_uid(); ref.ReferencedSOPClassUID = "1.2.840.10008.5.1.4.1.1.481.3"
    ds.ReferencedStructureSetSequence = Sequence([ref])
    ds.add_new(0x30090010, "LO", "VARIAN PRIVATE")  # private tag that must be stripped

    bounds = m120_bounds()
    left = np.full(60, -0.25); right = np.full(60, 0.25)
    centres = (np.asarray(bounds[:-1]) + np.asarray(bounds[1:])) / 2
    open_ = (centres > aperture_y[0]) & (centres < aperture_y[1])
    left[open_], right[open_] = aperture_x
    beam = Dataset()
    beam.BeamNumber, beam.BeamName, beam.BeamDescription = 1, "G0 6X fid1", "6X fiducial 1"
    beam.TreatmentMachineName, beam.RadiationType, beam.Manufacturer = "TrueBeam_SN1234", "PHOTON", "Varian Medical Systems"
    beam.TreatmentDeliveryType = "TREATMENT"
    f = Dataset(); f.FluenceMode = "STANDARD"; beam.PrimaryFluenceModeSequence = Sequence([f])
    devs = []
    for t, n, b in (("ASYMX", 1, None), ("ASYMY", 1, None), ("MLCX", 60, bounds)):
        d = Dataset(); d.RTBeamLimitingDeviceType, d.NumberOfLeafJawPairs = t, n
        if b: d.LeafPositionBoundaries = b
        devs.append(d)
    beam.BeamLimitingDeviceSequence = Sequence(devs)
    cps = []
    for i in range(2):
        cp = Dataset(); cp.ControlPointIndex = i; cp.CumulativeMetersetWeight = float(i)
        if i == 0:
            cp.NominalBeamEnergy, cp.DoseRateSet, cp.GantryAngle = 6, 600, 0.0
            pos = []
            for t, v in (("ASYMX", [60.0, 100.0]), ("ASYMY", [65.0, 105.0]),
                         ("MLCX", np.concatenate([left, right]).tolist())):
                p = Dataset(); p.RTBeamLimitingDeviceType, p.LeafJawPositions = t, v; pos.append(p)
            cp.BeamLimitingDevicePositionSequence = Sequence(pos)
        cps.append(cp)
    beam.ControlPointSequence = Sequence(cps)
    ds.BeamSequence = Sequence([beam])
    ds.save_as(path, write_like_original=False)
    return ds


def run(args):
    rr.main(args)


def opening(ds, dev="MLCX"):
    beam = ds.BeamSequence[0]
    b = next(d for d in beam.BeamLimitingDeviceSequence if d.RTBeamLimitingDeviceType == dev)
    bounds = np.asarray(b.LeafPositionBoundaries, float)
    pos = np.asarray(next(p for p in beam.ControlPointSequence[0].BeamLimitingDevicePositionSequence
                          if p.RTBeamLimitingDeviceType == dev).LeafJawPositions, float)
    n = len(bounds) - 1
    gap = pos[n:] - pos[:n]
    rows = np.where(gap > 1.0)[0]
    return bounds[rows.min()], bounds[rows.max() + 1], pos[:n][rows].min(), pos[n:][rows].max()


def test_anonymize_and_energy():
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "RP_AMWL.dcm"
        orig = make_plan(src)
        run([str(src), "--machine-name", "TB3", "--energy", "10FFF", "--profile", "truebeam-m120", "-o", tmp])
        out = pydicom.dcmread(Path(tmp) / "RP_TB3_10FFF_RP_AMWL.dcm")
        assert str(out.PatientName) == "DQA4^QA" and out.PatientID == "DQA4_QA"
        for kw in ("PatientBirthDate", "InstitutionName", "StationName", "OperatorsName", "ReferencedStructureSetSequence"):
            assert kw not in out, kw
        assert not any(e.tag.is_private for e in out.iterall())
        assert out.SOPInstanceUID != orig.SOPInstanceUID and out.FrameOfReferenceUID != orig.FrameOfReferenceUID
        assert out.ApprovalStatus == "UNAPPROVED" and out.RTPlanDate == "20260101"
        b = out.BeamSequence[0]
        assert b.TreatmentMachineName == "TB3" and float(b.ControlPointSequence[0].NominalBeamEnergy) == 10
        assert b.PrimaryFluenceModeSequence[0].FluenceModeID == "FFF"
        assert b.BeamName == "G0 10FFF fid1"
        # same geometry: aperture unchanged
        assert opening(out) == opening(orig)


def test_retarget_hd120_and_agility():
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "RP.dcm"
        make_plan(src)
        for prof, n in (("truebeam-hd120", 60), ("elekta-agility", 80)):
            run([str(src), "--machine-name", "M", "--energy", "6X", "--profile", prof, "-o", f"{tmp}/{prof}"])
            out = pydicom.dcmread(Path(tmp) / prof / "RP_M_6X_RP.dcm")
            y0, y1, x0, x1 = opening(out)
            assert 70 <= y0 <= 80 and 90 <= y1 <= 100, (prof, y0, y1)   # 2 cm aperture survives in Y
            assert (x0, x1) == (70.0, 90.0)
            types = [d.RTBeamLimitingDeviceType for d in out.BeamSequence[0].BeamLimitingDeviceSequence]
            mlc = next(d for d in out.BeamSequence[0].BeamLimitingDeviceSequence if d.RTBeamLimitingDeviceType == "MLCX")
            assert mlc.NumberOfLeafJawPairs == n
            if prof == "elekta-agility":
                assert types == ["MLCX", "ASYMY"]


def test_template_dual_layer_no_jaws():
    """Jawless dual-layer target (Ethos/Halcyon-like geometry, illustrative boundaries): X jaws clip the MLC,
    Y jaws close leaves outside them, and both layers get the aperture."""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "RP.dcm"
        make_plan(src, aperture_y=(40.0, 140.0), aperture_x=(40.0, 140.0))   # MLC wider than the jaws
        tpl = Path(tmp) / "tpl.dcm"
        t = make_plan(tpl)
        b = t.BeamSequence[0]
        layers = []
        for name, offset in (("MLCX1", 0.0), ("MLCX2", 5.0)):
            d = Dataset(); d.RTBeamLimitingDeviceType = name; d.NumberOfLeafJawPairs = 28
            d.LeafPositionBoundaries = (np.arange(29) * 10.0 - 140 + offset).tolist(); layers.append(d)
        b.BeamLimitingDeviceSequence = Sequence(layers)
        t.save_as(tpl, write_like_original=False)
        run([str(src), "--machine-name", "ETHOS1", "--energy", "6FFF", "--template", str(tpl), "-o", tmp])
        out = pydicom.dcmread(Path(tmp) / "RP_ETHOS1_6FFF_RP.dcm")
        for layer in ("MLCX1", "MLCX2"):
            y0, y1, x0, x1 = opening(out, layer)
            assert 60 <= y0 <= 75 and 95 <= y1 <= 110, (layer, y0, y1)   # limited by source Y jaws 65..105
            assert (x0, x1) == (60.0, 100.0)                              # clipped to source X jaws


def test_energy_parsing():
    assert rr.parse_energy("6x") == (6.0, "PHOTON", False)
    assert rr.parse_energy("6X-FFF") == (6.0, "PHOTON", True)
    assert rr.parse_energy("10fff") == (10.0, "PHOTON", True)
    assert rr.parse_energy("9E") == (9.0, "ELECTRON", False)
    assert rr.parse_energy("12MeV") == (12.0, "ELECTRON", False)


REPO = Path(__file__).resolve().parents[1]


def test_shared_truebeam_amwl_converts_to_native_ethos():
    """Converting the shared TrueBeam AM W-L plan to the Ethos profile must reproduce the apertures of the
    native Ethos AM W-L beams (planned in the Ethos TPS) at control point 0."""
    src, native = REPO / "rt_plans/TrueBeam_M120/DQA4_AMWL_TrueBeam.dcm", REPO / "rt_plans/Ethos/DQA4_DailyQA_Ethos.dcm"
    if not (src.exists() and native.exists()):
        return
    with tempfile.TemporaryDirectory() as tmp:
        run([str(src), "--machine-name", "Ethos", "--energy", "6FFF", "--profile", "varian-ethos-halcyon",
             "-o", tmp, "--name", "conv"])
        conv, nat = pydicom.dcmread(Path(tmp) / "conv.dcm"), pydicom.dcmread(native)
    cp0 = lambda b: {p.RTBeamLimitingDeviceType: np.asarray(p.LeafJawPositions, float)
                     for p in b.ControlPointSequence[0].BeamLimitingDevicePositionSequence}
    key = lambda b: (float(b.ControlPointSequence[0].GantryAngle), float(b.ControlPointSequence[0].BeamLimitingDeviceAngle))
    ref = {key(b): b for b in nat.BeamSequence if str(b.BeamName).startswith("AMWL")}
    n = 0
    for b in conv.BeamSequence:
        if b.TreatmentDeliveryType != "TREATMENT" or float(b.ControlPointSequence[0].PatientSupportAngle) != 0:
            continue                                    # Ethos has no couch rotation
        c, r = cp0(b), cp0(ref[key(b)])
        for t in ("MLCX1", "MLCX2", "X", "Y"):
            assert np.allclose(c[t], r[t], atol=0.01), (b.BeamName, t)
        n += 1
    assert n == 12


def test_shared_imaging_wl_to_hd120_keeps_fiducial_apertures():
    """Imaging W-L converted to HD120: Y jaws stay on the MLC (+/-110 mm) and every leaf pair inside +/-100 mm
    (where the fiducial apertures are) is identical to the Millennium 120 source."""
    src = REPO / "rt_plans/TrueBeam_M120/DQA4_ImagingWL_TrueBeam.dcm"
    if not src.exists():
        return
    with tempfile.TemporaryDirectory() as tmp:
        run([str(src), "--machine-name", "Edge", "--profile", "truebeam-hd120", "-o", tmp, "--name", "hd"])
        a, b = pydicom.dcmread(src), pydicom.dcmread(Path(tmp) / "hd.dcm")
    for ba, bb in zip(a.BeamSequence, b.BeamSequence):
        if ba.TreatmentDeliveryType != "TREATMENT":
            continue
        ya = np.asarray(next(d.LeafPositionBoundaries for d in ba.BeamLimitingDeviceSequence if d.RTBeamLimitingDeviceType == "MLCX"), float)
        yb = np.asarray(next(d.LeafPositionBoundaries for d in bb.BeamLimitingDeviceSequence if d.RTBeamLimitingDeviceType == "MLCX"), float)
        for ca, cb in zip(ba.ControlPointSequence, bb.ControlPointSequence):
            if "BeamLimitingDevicePositionSequence" not in ca:
                continue
            pa = {p.RTBeamLimitingDeviceType: np.asarray(p.LeafJawPositions, float) for p in ca.BeamLimitingDevicePositionSequence}
            pb = {p.RTBeamLimitingDeviceType: np.asarray(p.LeafJawPositions, float) for p in cb.BeamLimitingDevicePositionSequence}
            yjaw = next(pb[t] for t in ("ASYMY", "Y") if t in pb)
            assert yjaw[0] >= -110 and yjaw[1] <= 110
            na, nb = len(ya) - 1, len(yb) - 1
            for j in range(nb):
                c = (yb[j] + yb[j + 1]) / 2
                if abs(c) < 100:
                    i = np.searchsorted(ya, c) - 1
                    if pa["MLCX"][na + i] - pa["MLCX"][i] > 1:       # open in the source
                        assert pb["MLCX"][j] == pa["MLCX"][i] and pb["MLCX"][nb + j] == pa["MLCX"][na + i], ba.BeamName


def test_energy_selection_field_size_and_applicator():
    src = REPO / "rt_plans/TrueBeam_M120/DQA4_DailyQA_TrueBeam.dcm"
    if not src.exists():
        return
    with tempfile.TemporaryDirectory() as tmp:
        run([str(src), "--machine-name", "TB9", "-o", tmp, "--name", "edit",
             "--drop-energy", "15X", "--map-energy", "10FFF=10X", "--beam-energy", "16 MeV=15E",
             "--field-size", "15", "--applicator", "A15",
             "--electron-jaws", "6E=200", "9E=190", "12E=190", "15E=180", "20E=180"])
        ds = pydicom.dcmread(Path(tmp) / "edit.dcm")
    beams = {str(b.BeamName): b for b in ds.BeamSequence}
    assert "15 MV" not in beams and "10 MV" in beams and "10 FFF" not in beams
    b10 = beams["10 MV"]
    assert rr.energy_label(*rr.source_energy(b10)) == "10X" and float(b10.ControlPointSequence[0].DoseRateSet) == 600
    assert rr.energy_label(*rr.source_energy(beams["15 MeV"])) == "15E"
    assert ds.FractionGroupSequence[0].NumberOfBeams == len(ds.FractionGroupSequence[0].ReferencedBeamSequence)
    assert {int(r.ReferencedBeamNumber) for r in ds.FractionGroupSequence[0].ReferencedBeamSequence} <=            {int(b.BeamNumber) for b in ds.BeamSequence}
    jaws = lambda b: {p.RTBeamLimitingDeviceType: list(map(float, p.LeafJawPositions))
                      for p in b.ControlPointSequence[0].BeamLimitingDevicePositionSequence}
    assert jaws(beams["6 MV"])["X"] == [-75.0, 75.0]                       # open photon field resized
    assert jaws(beams["AM G0"])["X"] == [-11.0, 11.0]                      # MLC fields untouched
    assert jaws(beams["CBCT"])["X"] == [-115.0, 115.0]                     # setup fields untouched
    e6 = beams["6 MeV"]
    assert e6.ApplicatorSequence[0].ApplicatorID == "A15" and jaws(e6)["X"] == [-100.0, 100.0]


def test_energy_text_renaming():
    assert rr.rename_energy_text("15 MV", (15, "PHOTON", False), (10, "PHOTON", False)) == "10 MV"
    assert rr.rename_energy_text("6 FFF", (6, "PHOTON", True), (6, "PHOTON", False)) == "6 MV"
    assert rr.rename_energy_text("6 MV EDW 60-OUT", (6, "PHOTON", False), (10, "PHOTON", False)) == "10 MV EDW 60-OUT"
    assert rr.rename_energy_text("G0 6X fid1", (6, "PHOTON", False), (10, "PHOTON", True)) == "G0 10FFF fid1"
    assert rr.rename_energy_text("20 MeV", (16, "ELECTRON", False), (20, "ELECTRON", False)) == "20 MeV"
    assert rr.rename_energy_text("16 MeV", (16, "ELECTRON", False), (15, "ELECTRON", False)) == "15 MeV"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("PASS", name)
