#!/usr/bin/env python3
"""Anonymize and retarget DICOM RT Plan (RP) files to a new machine name, energy, and MLC geometry.

Typical use
-----------
    # Same MLC, new machine name and energy
    python rp_retarget.py ../rt_plans/TrueBeam/RP_AMWL.dcm --machine-name TB3 --energy 6X --profile truebeam-m120

    # Several energies at once
    python rp_retarget.py RP_AMWL.dcm --machine-name TB3 --energy 6X 10FFF 15X --profile truebeam-hd120

    # Any other machine: take the geometry from a plan exported for that machine from your own TPS
    python rp_retarget.py RP_AMWL.dcm --machine-name ETHOS1 --energy 6FFF --template my_ethos_plan.dcm

    python rp_retarget.py --list-profiles
    python rp_retarget.py --check some_plan.dcm      # report identifying tags only, write nothing

Output plans are UNAPPROVED and must be imported, reviewed, and validated in your own TPS before use.
"""
import argparse, json, re
from pathlib import Path

import numpy as np
import pydicom
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence
from pydicom.uid import generate_uid

HERE = Path(__file__).resolve().parent
PROFILES = json.loads((HERE / "machine_profiles.json").read_text(encoding="utf-8"))

# Attributes cleared or replaced during anonymization (top-level and in nested sequences)
CLEAR = ["PatientBirthDate", "PatientBirthTime", "PatientSex", "PatientAge", "OtherPatientIDs",
         "OtherPatientNames", "OtherPatientIDsSequence", "PatientComments", "InstitutionName", "InstitutionAddress",
         "InstitutionalDepartmentName", "ReferringPhysicianName", "PhysiciansOfRecord", "OperatorsName",
         "ReviewerName", "StationName", "DeviceSerialNumber", "AccessionNumber", "StudyID", "StudyDescription",
         "SeriesDescription", "ManufacturerModelName", "SoftwareVersions", "PrescriptionDescription",
         "RTPlanDescription", "ReviewDate", "ReviewTime"]
REMOVE_SEQ = ["ReferencedStructureSetSequence", "ReferencedDoseSequence", "ReferencedRTPlanSequence",
              "ReferencedImageSequence", "ReferencedReferenceImageSequence"]
DATE_TAGS = ["StudyDate", "SeriesDate", "ContentDate", "InstanceCreationDate", "RTPlanDate", "AcquisitionDate"]
TIME_TAGS = ["StudyTime", "SeriesTime", "ContentTime", "InstanceCreationTime", "RTPlanTime", "AcquisitionTime"]
# UIDs that identify a DICOM class or encoding, not an instance; every other UID is regenerated
# (vendor instance UIDs often embed the database or device serial number).
# Standard RT Plan, and Varian's proprietary plan class written by Ethos/Halcyon
RTPLAN_CLASSES = ["1.2.840.10008.5.1.4.1.1.481.5", "1.2.246.352.70.1.70"]
KEEP_UID = re.compile(r".*(ClassUID|TransferSyntaxUID|CodingSchemeUID)$")
PHI_REPORT = ["PatientName", "PatientID", "PatientBirthDate", "InstitutionName", "StationName",
              "DeviceSerialNumber", "OperatorsName", "ReviewerName", "PhysiciansOfRecord", "ReferringPhysicianName"]


# ----------------------------------------------------------------------------- energy
def parse_energy(text):
    """'6X' / '6MV' -> (6, PHOTON, False); '6FFF' / '6X-FFF' -> (6, PHOTON, True); '9E' / '9MeV' -> (9, ELECTRON, False)."""
    t = text.strip().upper().replace(" ", "").replace("_", "-")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(?:X|MV)?-?(FFF|SRS)?", t)
    if m and not t.endswith(("E", "MEV")):
        return float(m.group(1)), "PHOTON", bool(m.group(2))
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(?:E|MEV)", t)
    if m:
        return float(m.group(1)), "ELECTRON", False
    raise ValueError(f"Unrecognized energy '{text}'. Use e.g. 6X, 10FFF, 15X, 9E.")


def energy_label(value, rtype, fff):
    v = int(value) if float(value).is_integer() else value
    return f"{v}E" if rtype == "ELECTRON" else (f"{v}FFF" if fff else f"{v}X")


def source_energy(beam):
    cp0 = beam.ControlPointSequence[0]
    fff = any(getattr(f, "FluenceModeID", "") == "FFF" for f in getattr(beam, "PrimaryFluenceModeSequence", []))
    return float(cp0.NominalBeamEnergy), str(getattr(beam, "RadiationType", "PHOTON")), fff


# ----------------------------------------------------------------------------- geometry
def profile_geometry(name):
    p = PROFILES[name]
    if not p.get("mlc"):
        raise SystemExit(f"Profile '{name}' has no built-in MLC geometry. Use --template with a plan "
                         f"exported for that machine instead. Notes: {p.get('notes', '')}")
    devices = []
    for d in p["mlc"]:
        widths = [w for n, w in d["leaf_widths_mm"] for _ in range(n)]
        bounds = np.concatenate([[0], np.cumsum(widths)]) - sum(widths) / 2
        devices.append({"type": d["type"], "pairs": len(widths), "bounds": bounds.round(3).tolist(),
                        "park": d.get("park_mm"), "gap": d.get("min_gap_mm"), "fixed": None})
    for j in p.get("jaws", []):
        devices.append({"type": j, "pairs": 1, "bounds": None, "park": None, "gap": None,
                        "fixed": p.get("fixed_jaws_mm")})
    return devices, p


def template_geometry(path):
    """Geometry from a plan exported for the target machine: device types, leaf boundaries, where closed leaf
    pairs are parked, and (for jawless dual-layer machines such as Ethos/Halcyon) the fixed jaw values."""
    ds = pydicom.dcmread(path)
    beam = next(b for b in ds.BeamSequence
                if getattr(b, "TreatmentDeliveryType", "TREATMENT") == "TREATMENT"
                and any("LeafPositionBoundaries" in d for d in b.BeamLimitingDeviceSequence))
    pos = {p.RTBeamLimitingDeviceType: np.asarray(p.LeafJawPositions, float)
           for p in beam.ControlPointSequence[0].BeamLimitingDevicePositionSequence}
    layers = sum("LeafPositionBoundaries" in d for d in beam.BeamLimitingDeviceSequence)
    devices = []
    for d in beam.BeamLimitingDeviceSequence:
        t = d.RTBeamLimitingDeviceType
        bounds = [float(v) for v in d.LeafPositionBoundaries] if "LeafPositionBoundaries" in d else None
        park = fixed = closed_gap = None
        if bounds is not None and t in pos:
            n = len(pos[t]) // 2
            gap = pos[t][n:] - pos[t][:n]
            closed = gap <= OPEN_MM
            park = float(np.median(((pos[t][n:] + pos[t][:n]) / 2)[closed])) if closed.any() else None
            closed_gap = float(np.median(gap[closed])) if closed.any() else None
        elif bounds is None and layers > 1 and t in pos:
            fixed = pos[t].tolist()          # dual-layer machines: jaws are not used to shape fields
        devices.append({"type": t, "pairs": int(d.NumberOfLeafJawPairs), "bounds": bounds,
                        "park": park, "gap": closed_gap, "fixed": fixed})
    return devices, str(beam.TreatmentMachineName)


def device_sequence(devices):
    seq = Sequence()
    for d in devices:
        item = Dataset()
        item.RTBeamLimitingDeviceType = d["type"]
        item.NumberOfLeafJawPairs = d["pairs"]
        if d["bounds"] is not None:
            item.LeafPositionBoundaries = [float(v) for v in d["bounds"]]
        seq.append(item)
    return seq


JAW_ALIASES = {"X": ["ASYMX", "X"], "ASYMX": ["ASYMX", "X"], "Y": ["ASYMY", "Y"], "ASYMY": ["ASYMY", "Y"]}


OPEN_MM = 1.0   # a source leaf pair counts as open when its gap exceeds this


def remap_mlc(src_bounds, src_pos, dst_bounds, xjaw, yjaw, min_gap, park):
    """Rebuild the source aperture on the target leaf pairs.

    A target pair opens if any source pair it overlaps (inside the source Y jaws) is open, spanning the union of
    those openings, so the target field covers the source field. If the target has no field-shaping X jaws, the
    opening is clipped to the source X jaws. Closed pairs go to `park` (the target machine's parking position, e.g.
    outside the field on jawless machines) or, if None, to where the source parked its closed leaves (under a jaw)."""
    src_bounds = np.asarray(src_bounds, float)
    n_s, n_t = len(src_bounds) - 1, len(dst_bounds) - 1
    left_s, right_s = np.asarray(src_pos[:n_s], float), np.asarray(src_pos[n_s:], float)
    is_open = right_s - left_s > OPEN_MM
    closed_mid = ((left_s + right_s) / 2)[~is_open]
    default = park if park is not None else (float(np.median(closed_mid)) if len(closed_mid) else 0.0)
    left, right = np.full(n_t, default - min_gap / 2), np.full(n_t, default + min_gap / 2)
    for j in range(n_t):
        lo, hi = dst_bounds[j], dst_bounds[j + 1]
        if yjaw:
            lo, hi = max(lo, yjaw[0]), min(hi, yjaw[1])
        overlap = np.minimum(src_bounds[1:], hi) - np.maximum(src_bounds[:-1], lo) > 0.01
        rows = overlap & is_open
        if not rows.any():
            continue
        x1, x2 = left_s[rows].min(), right_s[rows].max()
        if xjaw:
            x1, x2 = max(x1, xjaw[0]), min(x2, xjaw[1])
        if x2 - x1 > OPEN_MM:
            left[j], right[j] = x1, x2
    return np.concatenate([left, right]).round(2).tolist()


def jaw_match(state, name):
    return next((state[a] for a in JAW_ALIASES.get(name, [name]) if a in state), None)


def retarget_geometry(beam, dst_devices, min_gap, park):
    src = {d.RTBeamLimitingDeviceType: d for d in beam.BeamLimitingDeviceSequence}
    src_mlc = next((t for t in src if t.startswith("MLC")), None)
    if src_mlc is None:
        # Jaw-only beam (setup/imaging fields, open dosimetry fields): nothing to remap.
        missing = [d["type"] for d in dst_devices if d["bounds"] is None and d["fixed"] is None
                   and not any(a in src for a in JAW_ALIASES.get(d["type"], [d["type"]]))]
        if missing or any(d["fixed"] for d in dst_devices):
            print(f"  NOTE: beam '{beam.BeamName}' has no MLC; left unchanged. Recreate it in your TPS if the "
                  f"target machine needs MLC-defined fields.")
        return
    src_bounds = np.asarray(src[src_mlc].LeafPositionBoundaries, float)
    shaping_x = any(d["type"] in ("ASYMX", "X") and d["fixed"] is None for d in dst_devices)
    spans = [(d["bounds"][0], d["bounds"][-1]) for d in dst_devices if d["bounds"] is not None]
    y_span = (min(s[0] for s in spans), max(s[1] for s in spans)) if spans else None
    clip_noted = False

    state = {}   # current position of every source device (DICOM carries positions forward between control points)
    for cp in beam.ControlPointSequence:
        if "BeamLimitingDevicePositionSequence" not in cp:
            continue
        for p in cp.BeamLimitingDevicePositionSequence:
            state[p.RTBeamLimitingDeviceType] = [float(v) for v in p.LeafJawPositions]
        xjaw, yjaw = jaw_match(state, "X"), jaw_match(state, "Y")
        new = Sequence()
        for d in dst_devices:
            item = Dataset()
            item.RTBeamLimitingDeviceType = d["type"]
            if d["bounds"] is not None:
                item.LeafJawPositions = remap_mlc(
                    src_bounds, state[src_mlc], d["bounds"], None if shaping_x else xjaw, yjaw,
                    min_gap if min_gap is not None else (d["gap"] if d["gap"] is not None else 0.5),
                    park if park is not None else d["park"])
            elif d["fixed"] is not None:
                item.LeafJawPositions = d["fixed"]
            else:
                match = jaw_match(state, d["type"])
                if match is None:
                    raise SystemExit(f"No source position for target device {d['type']}.")
                if d["type"] in ("ASYMY", "Y") and y_span and (match[0] < y_span[0] or match[1] > y_span[1]):
                    # Outside the target leaves nothing blocks the beam except the Y jaws, so keep them on the MLC.
                    clipped = [max(match[0], y_span[0]), min(match[1], y_span[1])]
                    if not clip_noted:
                        print(f"  NOTE: beam '{beam.BeamName}': Y jaws {match} clipped to the target MLC span {clipped}.")
                        clip_noted = True
                    match = clipped
                item.LeafJawPositions = match
            new.append(item)
        cp.BeamLimitingDevicePositionSequence = new
    beam.BeamLimitingDeviceSequence = device_sequence(dst_devices)


# ----------------------------------------------------------------------------- anonymization
def anonymize(ds, patient_name, patient_id, keep_private, uid_map):
    if not keep_private:
        ds.remove_private_tags()
    stack = [ds]
    while stack:
        item = stack.pop()
        for kw in CLEAR:
            if kw in item:
                delattr(item, kw)
        for kw in REMOVE_SEQ:
            if kw in item:
                delattr(item, kw)
        for elem in item:
            if elem.VR == "UI" and elem.value and not KEEP_UID.match(elem.keyword or ""):
                elem.value = uid_map.setdefault(str(elem.value), generate_uid())
            elif elem.VR == "SQ":
                stack.extend(elem.value)
    ds.PatientName, ds.PatientID = patient_name, patient_id
    for kw in DATE_TAGS:
        if kw in ds:
            setattr(ds, kw, "20260101")
    for kw in TIME_TAGS:
        if kw in ds:
            setattr(ds, kw, "000000")
    if "ApprovalStatus" in ds:
        ds.ApprovalStatus = "UNAPPROVED"
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    ds.PatientIdentityRemoved, ds.DeidentificationMethod = "YES", "rp_retarget.py (DQA4 Pro delivery files)"


# ----------------------------------------------------------------------------- energy / machine
def set_energy(beam, value, rtype, fff, dose_rate):
    change_beam_energy(beam, (value, rtype, fff))
    if dose_rate:
        for cp in beam.ControlPointSequence:
            if "DoseRateSet" in cp:
                cp.DoseRateSet = dose_rate


def energy_text_patterns(value, rtype, fff):
    """Regexes for how an energy is commonly written in beam names: '6X', '6 MV', '6MV', '6 FFF', '6X-FFF', '20 MeV', '9E'."""
    v = re.escape(f"{value:g}")
    if rtype == "ELECTRON":
        return [rf"(?<![\d.]){v}\s*(MeV|E)\b"]
    if fff:
        return [rf"(?<![\d.]){v}\s*(X|MV)?[\s_-]*FFF\b"]
    return [rf"(?<![\d.]){v}\s*(X|MV)\b(?![\s_-]*FFF)"]


def rename_energy_text(text, old, new):
    value, rtype, fff = new
    words = {("ELECTRON", False): f"{value:g} MeV", ("PHOTON", True): f"{value:g} FFF", ("PHOTON", False): f"{value:g} MV"}
    for pat in energy_text_patterns(*old):
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            compact = " " not in m.group(0)
            rep = energy_label(*new) if compact else words[(rtype, fff)]
            return text[:m.start()] + rep + text[m.end():]
    return text


def change_beam_energy(beam, new):
    """Set a beam's energy (same radiation type), fluence mode, beam name text, and a valid dose rate."""
    old = source_energy(beam)
    value, rtype, fff = new
    if rtype != old[1]:
        raise SystemExit(f"Beam '{beam.BeamName}' is {old[1]}; cannot change it to {rtype}.")
    for cp in beam.ControlPointSequence:
        if "NominalBeamEnergy" in cp:
            cp.NominalBeamEnergy = value
    if rtype == "PHOTON":
        f = Dataset()
        f.FluenceMode = "NON_STANDARD" if fff else "STANDARD"
        if fff:
            f.FluenceModeID = "FFF"
        beam.PrimaryFluenceModeSequence = Sequence([f])
        cp0 = beam.ControlPointSequence[0]
        if old[2] and not fff and float(getattr(cp0, "DoseRateSet", 0)) > 600:
            cp0.DoseRateSet = 600
            print(f"  NOTE: beam '{beam.BeamName}': dose rate set to 600 MU/min for a flattened beam.")
        elif fff and not old[2]:
            print(f"  NOTE: beam '{beam.BeamName}': now FFF at {getattr(cp0, 'DoseRateSet', '?')} MU/min; "
                  "set the dose rate you use for FFF with --dose-rate if needed.")
    for kw in ("BeamName", "BeamDescription"):
        if kw in beam:
            setattr(beam, kw, rename_energy_text(str(getattr(beam, kw)), old, new)[:64])


def drop_beams(ds, beams):
    numbers = {int(b.BeamNumber) for b in beams}
    ds.BeamSequence = Sequence([b for b in ds.BeamSequence if int(b.BeamNumber) not in numbers])
    for fg in getattr(ds, "FractionGroupSequence", []):
        fg.ReferencedBeamSequence = Sequence([r for r in fg.ReferencedBeamSequence
                                              if int(r.ReferencedBeamNumber) not in numbers])
        fg.NumberOfBeams = len(fg.ReferencedBeamSequence)
    for b in beams:
        print(f"  removed beam '{b.BeamName}' ({energy_label(*source_energy(b))})")


def is_open_jaw_field(beam):
    return (getattr(beam, "TreatmentDeliveryType", "TREATMENT") == "TREATMENT"
            and not any(d.RTBeamLimitingDeviceType.startswith("MLC") for d in beam.BeamLimitingDeviceSequence)
            and "ApplicatorSequence" not in beam)


def set_jaws(beam, x_mm, y_mm):
    for cp in beam.ControlPointSequence:
        for p in getattr(cp, "BeamLimitingDevicePositionSequence", []):
            t = p.RTBeamLimitingDeviceType
            if t in ("X", "ASYMX"):
                p.LeafJawPositions = [-x_mm / 2, x_mm / 2]
            elif t in ("Y", "ASYMY"):
                p.LeafJawPositions = [-y_mm / 2, y_mm / 2]


def edit_plan(ds, args):
    """Energy selection, field size and electron applicator edits (treatment beams only)."""
    treat = lambda b: getattr(b, "TreatmentDeliveryType", "TREATMENT") == "TREATMENT"
    if args.drop_energy:
        drop = {energy_label(*parse_energy(e)) for e in args.drop_energy}
        drop_beams(ds, [b for b in ds.BeamSequence if treat(b) and energy_label(*source_energy(b)) in drop])
    for spec in args.map_energy or []:
        old, new = (parse_energy(x) for x in spec.split("="))
        hits = [b for b in ds.BeamSequence if treat(b) and energy_label(*source_energy(b)) == energy_label(*old)]
        for b in hits:
            change_beam_energy(b, new)
        print(f"  {energy_label(*old)} -> {energy_label(*new)}: {len(hits)} beam(s)")
    for spec in args.beam_energy or []:
        name, e = spec.rsplit("=", 1)
        hits = [b for b in ds.BeamSequence if str(b.BeamName) == name]
        if not hits:
            raise SystemExit(f"No beam named '{name}'.")
        for b in hits:
            change_beam_energy(b, parse_energy(e))
            print(f"  beam '{name}' -> {energy_label(*parse_energy(e))}")
    if args.field_size:
        fs = args.field_size
        if not 5 <= fs <= 20:
            print("  WARNING: the DQA4 ion chambers need at least 5 x 5 cm and field-size detection covers 2-20 cm.")
        hits = [b for b in ds.BeamSequence if is_open_jaw_field(b) and source_energy(b)[1] == "PHOTON"]
        for b in hits:
            set_jaws(b, fs * 10, fs * 10)
        print(f"  photon open fields set to {fs:g} x {fs:g} cm: {len(hits)} beam(s). Re-baseline output and profiles.")
    if args.applicator:
        jaws = {}
        for item in args.electron_jaws or []:
            e, mm = item.split("=")
            jaws[energy_label(*parse_energy(e))] = float(mm)
        for b in ds.BeamSequence:
            if "ApplicatorSequence" not in b:
                continue
            label = energy_label(*source_energy(b))
            if label not in jaws:
                raise SystemExit(f"--applicator needs --electron-jaws for {label} (full symmetric jaw opening in mm for "
                                 f"{args.applicator}, from your machine's electron beam data).")
            b.ApplicatorSequence[0].ApplicatorID = args.applicator
            if "ApplicatorDescription" in b.ApplicatorSequence[0]:
                b.ApplicatorSequence[0].ApplicatorDescription = args.applicator
            set_jaws(b, jaws[label], jaws[label])
            print(f"  beam '{b.BeamName}': applicator {args.applicator}, jaws {jaws[label]:g} mm")


def treatment_energies(ds):
    return {energy_label(*source_energy(b)) for b in ds.BeamSequence
            if getattr(b, "TreatmentDeliveryType", "TREATMENT") == "TREATMENT"}


def retarget(path, out_dir, machine, energy, devices, profile, args):
    """energy=None keeps every beam's energy (anonymize/rename/remap only, e.g. multi-energy daily QA plans)."""
    ds = pydicom.dcmread(path)
    if ds.SOPClassUID not in RTPLAN_CLASSES:
        raise SystemExit(f"{path} is not an RT Plan (SOP class {ds.SOPClassUID}).")
    suffix = ""
    if energy:
        if len(treatment_energies(ds)) > 1:
            raise SystemExit(f"{path} has several treatment energies ({', '.join(sorted(treatment_energies(ds)))}); "
                             "--energy is for single-energy plans such as AM W-L. Omit --energy to keep them.")
        value, rtype, fff = parse_energy(energy)
        suffix = energy_label(value, rtype, fff)
        allowed = (profile or {}).get("energies")
        if allowed and suffix not in allowed:
            print(f"  WARNING: {suffix} is not listed for this profile ({', '.join(allowed)}).")
    anonymize(ds, args.patient_name, args.patient_id, args.keep_private, {})
    edit_plan(ds, args)
    for beam in ds.BeamSequence:
        beam.TreatmentMachineName = machine
        if "Manufacturer" in beam and profile and profile.get("manufacturer"):
            beam.Manufacturer = profile["manufacturer"]
        if energy:
            set_energy(beam, value, rtype, fff, args.dose_rate)
        if devices is not None:
            retarget_geometry(beam, devices, args.min_gap, args.park)
    if args.description:
        ds.RTPlanDescription = args.description[:1024]
    label = args.label or str(getattr(ds, "RTPlanLabel", "DQA4"))
    ds.RTPlanLabel = "_".join(filter(None, [label, suffix]))[:16]
    ds.RTPlanName = " ".join(filter(None, [label, machine, suffix]))[:64]
    name = args.name or "_".join(filter(None, ["RP", machine, suffix, Path(path).stem]))
    out = Path(out_dir) / (f"{name}_{suffix}.dcm" if args.name and suffix and len(args.energy) > 1 else f"{name}.dcm")
    out.parent.mkdir(parents=True, exist_ok=True)
    ds.save_as(out, write_like_original=False)
    return out


def check(path):
    ds = pydicom.dcmread(path)
    print(f"{path}:")
    for kw in PHI_REPORT:
        if kw in ds and str(getattr(ds, kw)).strip():
            print(f"  {kw}: {getattr(ds, kw)}")
    priv = sum(1 for e in ds.iterall() if e.tag.is_private)
    print(f"  private tags: {priv}")
    for b in getattr(ds, "BeamSequence", []):
        e = source_energy(b)
        print(f"  beam {b.BeamNumber} '{b.BeamName}': machine {b.TreatmentMachineName}, {energy_label(*e)}, "
              f"devices {[d.RTBeamLimitingDeviceType for d in b.BeamLimitingDeviceSequence]}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="*", help="RT Plan file(s)")
    ap.add_argument("--machine-name", help="TreatmentMachineName exactly as configured in your TPS/OIS")
    ap.add_argument("--energy", nargs="+", help="One or more energies, e.g. 6X 10FFF 15X (single-energy plans "
                                                "only; omit to keep each beam's energy)")
    ap.add_argument("--name", help="Output file name without .dcm (default: RP_<machine>_<energy>_<input name>)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--profile", choices=sorted(PROFILES), help="Built-in target MLC geometry")
    g.add_argument("--template", help="RT Plan exported for the target machine; its MLC/jaw geometry is used")
    ap.add_argument("-o", "--out-dir", default="output")
    ap.add_argument("--dose-rate", type=float, help="Set DoseRateSet (MU/min) on control points that carry it")
    ap.add_argument("--label", help="Base RT Plan label (default: keep the source label)")
    ap.add_argument("--description", help="RT Plan Description to write (e.g. author, source, validation note)")
    ap.add_argument("--patient-name", default="DQA4^QA")
    ap.add_argument("--patient-id", default="DQA4_QA")
    ap.add_argument("--min-gap", type=float, help="Gap (mm) for closed leaf pairs (default: profile/template, else 0.5)")
    ap.add_argument("--park", type=float, help="X position (mm) for closed leaf pairs (default: profile/template "
                                               "parking position, else where the source closed them)")
    ed = ap.add_argument_group("plan edits (treatment beams only; setup/imaging fields are untouched)")
    ed.add_argument("--drop-energy", nargs="+", metavar="E", help="Remove beams at energies you don't have, e.g. 15X 20E")
    ed.add_argument("--map-energy", nargs="+", metavar="OLD=NEW", help="Change energies, e.g. 15X=10X 6FFF=6X")
    ed.add_argument("--beam-energy", nargs="+", metavar="NAME=E", help="Set one beam's energy by name, e.g. '20 MeV=20E'")
    ed.add_argument("--field-size", type=float, metavar="CM",
                    help="Square size (cm) for jaw-defined open photon fields (dosimetry, EDW); DQA4 range 5-20 cm")
    ed.add_argument("--applicator", help="Electron applicator ID for all electron beams, e.g. A15 (needs --electron-jaws)")
    ed.add_argument("--electron-jaws", nargs="+", metavar="E=MM",
                    help="Full symmetric jaw opening per electron energy for --applicator, e.g. 6E=200 9E=190")
    ap.add_argument("--keep-private", action="store_true", help="Keep vendor private tags (may contain identifiers)")
    ap.add_argument("--list-profiles", action="store_true")
    ap.add_argument("--check", action="store_true", help="Report identifying tags and beam setup; write nothing")
    args = ap.parse_args(argv)

    if args.list_profiles:
        for k, p in sorted(PROFILES.items()):
            status = "built-in geometry" if p.get("mlc") else "needs --template"
            print(f"{k:22s} {p['description']}  [{status}]")
        return
    if not args.inputs:
        ap.error("no input files")
    if args.check:
        for f in args.inputs:
            check(f)
        return
    if not args.machine_name:
        ap.error("--machine-name is required")

    devices, profile = None, None
    if args.profile:
        devices, profile = profile_geometry(args.profile)
    elif args.template:
        devices, _ = template_geometry(args.template)
    for f in args.inputs:
        for e in (args.energy or [None]):
            print("wrote", retarget(f, args.out_dir, args.machine_name, e, devices, profile, args))
    print("\nPlans are UNAPPROVED. Import into your TPS, review every beam and control point, "
          "and validate delivery on your machine before clinical QA use.")


if __name__ == "__main__":
    main()
