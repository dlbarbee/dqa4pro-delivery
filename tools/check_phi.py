#!/usr/bin/env python3
"""Scan the repository for identifying information before publishing. Exit code 1 if anything is found.

    python tools/check_phi.py                         # whole repo
    python tools/check_phi.py --forbid MyHospital SN1234  # also flag institution names, serial numbers, etc.

DICOM: flags non-placeholder patient name/ID, birth date, institution, station, operator and reviewer names,
device serial numbers, and any private tags. XML/text: flags e-mail addresses and every --forbid term.
"""
import argparse, re, sys
from pathlib import Path

import pydicom

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_NAMES = {"DQA4^QA", "DQA4_QA", ""}
DICOM_FLAGS = ["PatientBirthDate", "InstitutionName", "InstitutionAddress", "StationName", "OperatorsName",
               "ReviewerName", "PhysiciansOfRecord", "ReferringPhysicianName", "DeviceSerialNumber"]
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
SKIP_DIRS = {".git", "output", "raw", "__pycache__", ".venv"}


def scan_dicom(path):
    issues = []
    try:
        ds = pydicom.dcmread(path)
    except Exception as e:  # not DICOM or unreadable
        return [f"unreadable DICOM ({e})"]
    for kw in ("PatientName", "PatientID"):
        if str(getattr(ds, kw, "")) not in ALLOWED_NAMES:
            issues.append(f"{kw} = {getattr(ds, kw)}")
    for elem in ds.iterall():
        if elem.tag.is_private:
            issues.append("private tags present (re-run rp_retarget.py without --keep-private)")
            break
    stack = [ds]
    while stack:
        item = stack.pop()
        for kw in DICOM_FLAGS:
            if kw in item and str(getattr(item, kw)).strip():
                issues.append(f"{kw} = {getattr(item, kw)}")
        stack.extend(v for e in item if e.VR == "SQ" for v in e.value)
    return issues


def scan_text(path, forbid):
    text = path.read_text(encoding="utf-8", errors="ignore")
    issues = [f"e-mail address {m}" for m in sorted(set(EMAIL.findall(text)))]
    for term in forbid:
        if term.lower() in text.lower():
            issues.append(f"contains '{term}'")
    return issues


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", default=[str(ROOT / "developer_mode"), str(ROOT / "rt_plans")])
    ap.add_argument("--forbid", nargs="*", default=[], help="Extra terms that must not appear (site, serials, names)")
    args = ap.parse_args()
    files = []
    for p in map(Path, args.paths):
        files += [p] if p.is_file() else [f for f in p.rglob("*") if f.is_file()
                                          and not SKIP_DIRS & set(f.relative_to(p).parts)]
    found = 0
    for f in sorted(files):
        if f.suffix.lower() == ".dcm":
            issues = scan_dicom(f) + ([] if not args.forbid else scan_text(f, args.forbid))
        elif f.suffix.lower() in {".xml", ".txt", ".csv", ".json", ".md"}:
            issues = scan_text(f, args.forbid)
        else:
            continue
        for i in issues:
            print(f"{f.relative_to(ROOT) if f.is_relative_to(ROOT) else f}: {i}")
        found += len(issues)
    print(f"\n{len(files)} files scanned, {found} issue(s).")
    sys.exit(1 if found else 0)


if __name__ == "__main__":
    main()
