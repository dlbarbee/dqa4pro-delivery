#!/usr/bin/env python3
"""Keep only the final image of each acquisition from a TrueBeam Developer Mode imaging session.

Developer Mode writes one DICOM file for every recorded frame of an integrated (MV) acquisition:

    <series name>-<acquisition ID, 3 digits>-<frame, 4 digits>.dcm      e.g. isocal_-000-0000.dcm ... isocal_-000-0107.dcm
    <series name>-<acquisition ID, 3 digits>.dcm                         single-frame images (kV), e.g. isocal_-001.dcm

Only the LAST frame of each acquisition holds the complete integrated image, so analysis must use the highest frame
number for every acquisition ID, and the single file where there is no frame number. Series names that themselves
contain hyphens are handled: the acquisition ID is always the last 3-digit group before the optional frame number.

    python select_last_frames.py <session folder>                    # copy selected images to <folder>/last_frames
    python select_last_frames.py <folder> -o <out> --group-series    # also give them one study/series/frame of reference
    python select_last_frames.py <folder> --rename                   # name copies acq006_G270_C0_T0_MV.dcm etc.
    python select_last_frames.py <folder> --dry-run                  # list what would be selected

Originals are never modified or deleted.
"""
import argparse, re, shutil, sys
from pathlib import Path

PATTERN = re.compile(r"^(?P<series>.+)-(?P<acq>\d{3})(?:-(?P<frame>\d{4}))?\.dcm$", re.IGNORECASE)


def select(files):
    """Return ({(series, acq): (path, frame or None, n_frames)}, unmatched files)."""
    groups, unmatched = {}, []
    for f in files:
        m = PATTERN.match(f.name)
        if not m:
            unmatched.append(f)
            continue
        key = (m["series"], int(m["acq"]))
        frame = int(m["frame"]) if m["frame"] is not None else -1
        groups.setdefault(key, []).append((frame, f))
    chosen = {}
    for key, items in groups.items():
        frame, path = max(items, key=lambda t: t[0])
        chosen[key] = (path, None if frame < 0 else frame, len(items))
    return dict(sorted(chosen.items())), unmatched


def group_series(paths, patient_name, patient_id, machine):
    """Give the selected images one study, series and frame of reference so analysis software treats them as a set."""
    import pydicom
    from pydicom.uid import generate_uid
    study, series, frame_ref = generate_uid(), generate_uid(), generate_uid()
    for i, p in enumerate(sorted(paths), start=1):
        ds = pydicom.dcmread(p)
        ds.StudyInstanceUID, ds.SeriesInstanceUID = study, series
        ds.FrameOfReferenceUID = frame_ref
        ds.InstanceNumber = i
        if patient_name:
            ds.PatientName = patient_name
        if patient_id:
            ds.PatientID = patient_id
        if machine:
            ds.RadiationMachineName = machine
            ds.StationName = machine
        ds.save_as(p, write_like_original=False)


def _num(v):
    v = float(v)
    return f"{v:g}"


def descriptive_name(path, series, acq):
    """acq006_G270_C0_T0_MV.dcm from the image's own header (RT Image gantry, collimator and couch angles; kV when
    an X-ray tube voltage is recorded, otherwise MV with the nominal energy when present)."""
    import pydicom
    ds = pydicom.dcmread(path, stop_before_pixels=True)
    parts = [f"acq{acq:03d}"]
    for tag, key in (("G", "GantryAngle"), ("C", "BeamLimitingDeviceAngle"), ("T", "PatientSupportAngle")):
        if key in ds and ds.data_element(key).value not in (None, ""):
            parts.append(f"{tag}{_num(getattr(ds, key))}")
    exposure = ds.ExposureSequence[0] if "ExposureSequence" in ds and len(ds.ExposureSequence) else None
    kvp = getattr(ds, "KVP", None) or getattr(exposure, "KVP", None)
    if kvp:
        parts.append(f"kV{_num(kvp)}")
    else:
        energy = getattr(exposure, "NominalBeamEnergy", None) if exposure is not None else None
        parts.append(f"MV{_num(energy)}" if energy else "MV")
    return "_".join(parts) + ".dcm"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path, help="Folder with the Developer Mode image files")
    ap.add_argument("-o", "--out", type=Path, help="Output folder (default: <folder>/last_frames)")
    ap.add_argument("--dry-run", action="store_true", help="List the selection without copying")
    ap.add_argument("--rename", action="store_true",
                    help="Name copies from their headers, e.g. acq006_G270_C0_T0_MV.dcm (gantry, collimator, couch, kV/MV)")
    ap.add_argument("--group-series", action="store_true", help="Set common study/series/frame-of-reference UIDs")
    ap.add_argument("--patient-name", help="With --group-series: patient name to write")
    ap.add_argument("--patient-id", help="With --group-series: patient ID to write")
    ap.add_argument("--machine-name", help="With --group-series: RadiationMachineName / StationName to write")
    args = ap.parse_args(argv)

    files = sorted(p for p in args.folder.iterdir() if p.is_file() and p.suffix.lower() == ".dcm")
    if not files:
        sys.exit(f"No .dcm files in {args.folder}")
    chosen, unmatched = select(files)
    print(f"{len(files)} files, {len(chosen)} acquisitions\n")
    print(f"{'series':20s} {'acq':>4s} {'frames':>6s}  selected")
    for (series, acq), (path, frame, n) in chosen.items():
        kind = "single image" if frame is None else f"last frame {frame:04d}"
        print(f"{series[:20]:20s} {acq:4d} {n:6d}  {path.name}  ({kind})")
    if unmatched:
        print(f"\nIgnored {len(unmatched)} file(s) not named <series>-<NNN>[-<NNNN>].dcm:",
              ", ".join(p.name for p in unmatched[:10]))
    ids = sorted(acq for _, acq in chosen)
    gaps = sorted(set(range(ids[0], ids[-1] + 1)) - set(ids)) if ids else []
    if gaps:
        print(f"\nWARNING: acquisition IDs missing from the sequence: {gaps}. Check the session is complete.")
    if args.dry_run:
        return

    out = args.out or args.folder / "last_frames"
    out.mkdir(parents=True, exist_ok=True)
    copied = []
    for (series, acq), (path, _, _) in chosen.items():
        name = descriptive_name(path, series, acq) if args.rename else path.name
        copied.append(Path(shutil.copy2(path, out / name)))
        if args.rename:
            print(f"  {path.name} -> {name}")
    if args.group_series:
        group_series(copied, args.patient_name, args.patient_id, args.machine_name)
    print(f"\nCopied {len(copied)} images to {out}" + (" (grouped into one series)" if args.group_series else ""))


if __name__ == "__main__":
    main()
