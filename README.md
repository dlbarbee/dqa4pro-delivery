# Daily QA 4 Pro delivery files

DICOM RT plans, TrueBeam Developer Mode XML, and small tools for running the Sun Nuclear / Mirion
**Daily QA 4 Pro** daily QA, including **Active Measurement Winston–Lutz (AM W-L)** and **Imaging Winston–Lutz**.

Author: **David Barbee, PhD**. These files accompany:

> Barbee D. *Characterization of the Daily QA 4 Pro for beam, image-guidance, surface-guidance, and active isocenter
> verification on modern linear accelerators.* J Appl Clin Med Phys (submitted). <!-- add DOI on acceptance -->

They are shared so other clinics can get started quickly. They are **reference files, not a validated product,
and not endorsed by any vendor.** Read [DISCLAIMER.md](DISCLAIMER.md) before using anything here.

> [!CAUTION]
> **Collision hazard: Active Measurement W-L moves the couch.** The AM W-L sequence rotates the couch to 90° and
> 270° (and the gantry through 8 angles) automatically in the Developer Mode XML, and through the couch-rotation
> fields in the DICOM plans. **Retract the kV and MV imager arms (or set them to mid position) before delivery.**
> Extended imager arms will collide with the couch or phantom when the couch rotates. Do a dry run, confirm
> clearance at every couch and gantry angle, watch the room monitor, and be ready to stop motion.

## Contents

### DICOM RT plans: [`rt_plans/`](rt_plans/)
Phantom QA plans for TrueBeam **Machine QA mode**. Patient `DQA4^QA`, status UNAPPROVED, identifiers and all vendor
private tags removed (standard DICOM import does not need them).

| File | Machine / MLC | Beams | Status |
|---|---|---|---|
| `TrueBeam_M120/DQA4_DailyQA_TrueBeam.dcm` | TrueBeam, Millennium 120 | Setup (CBCT, AP MV, Rt Lat kV); 20 × 20 cm photons 6X, 15X, 6FFF, 10FFF; 6X EDW 60 OUT; AM W-L (8 gantry, collimator 90/270, couch 90/270); electrons 6–20 MeV, 20 × 20 cone | Delivered |
| `TrueBeam_M120/DQA4_AMWL_TrueBeam.dcm` | TrueBeam, Millennium 120 | CBCT + full AM W-L (8 gantry; collimator 0/90/270; couch 0/90/270), 50 MU each | Delivered |
| `TrueBeam_M120/DQA4_ImagingWL_TrueBeam.dcm` | TrueBeam, Millennium 120 | Imaging W-L without Developer Mode: CBCT; kV at 8 gantry angles; MV at 8 gantry angles plus collimator 90/270 and couch 90/270, each a 2-segment step-and-shoot field (20 MU) with integrated portal imaging | Delivered |
| `Edge_HD120/DQA4_DailyQA_Edge.dcm` | Edge, HD120 | Setup; jaw-defined 20 × 20 cm photons 6X, 15X, 6FFF, 10FFF; 6X EDW | Delivered |
| `Edge_HD120/DQA4_AMWL_Edge_HD120_DERIVED.dcm` | Edge, HD120 | AM W-L converted from the TrueBeam plan by `rp_retarget.py` | **Not delivered**; check apertures |
| `Edge_HD120/DQA4_ImagingWL_Edge_HD120_DERIVED.dcm` | Edge, HD120 | Imaging W-L converted by `rp_retarget.py`. Fiducial apertures identical; the 1 cm scaling strips at \|Y\| 110–120 mm on the five gantry-0° fields cannot be formed (HD120 leaves end at ±110 mm) | **Not delivered**; check apertures |
| `Ethos/DQA4_DailyQA_Ethos.dcm` | Ethos, dual-layer MLC | kV CBCT; 6FFF 20 × 20 cm; AM W-L (8 gantry; collimator 0/90/270; Ethos has no couch rotation) | Delivered |

Machine names are generic (`TrueBeam`, `Edge`, `Ethos`): set yours with `rp_retarget.py` before import.

### Developer Mode XML: [`developer_mode/`](developer_mode/)

| File | Purpose |
|---|---|
| `active_measurement_wl/DQA4_AMWL_MLC.xml` | AM W-L in one beam: 8 gantry angles, collimator 0/90/270, couch 0/90/270, 50 MU each; 2 × 2 cm MLC field (2.4 cm jaws). Recommended |
| `active_measurement_wl/DQA4_AMWL_Jaw.xml` | Same sequence with a 2 × 2 cm jaw-defined field |
| `angle_error_tests/DQA4_AMWL_MLC_angle_offset.xml` | **Error-injection test**: AM W-L with gantry, collimator and couch deliberately offset 0.5–2.0° |
| `angle_error_tests/DQA4_ImagingWL_angle_offset.xml` | **Error-injection test**: Imaging W-L (8 gantry kV + integrated MV, couch and collimator MV) with deliberate angle offsets |

The angle-error files reproduce the sensitivity tests in the paper. **Never use them for routine QA.** A nominal
Imaging W-L file will be added to `developer_mode/imaging_wl/`.

### Tools: [`tools/`](tools/)

| Tool | What it does |
|---|---|
| `rp_retarget.py` | Anonymizes a plan and sets your machine name; for single-energy plans (AM W-L) sets the energy; remaps MLC apertures to another MLC model |
| `select_last_frames.py` | Keeps only the final frame of each Developer Mode image acquisition; optionally renames by gantry/collimator/couch and kV/MV |
| `check_phi.py` | Scans files for identifying data before you share them |
| `machine_profiles.json` | MLC geometry dictionary (below) |

## The tests

**Active Measurement W-L.** Gantry at 8 (or 4) angles, plus collimator and couch at ±90°, with fields of 2 × 2 cm or
less for gantry and 2–10 cm for collimator and couch. After IGRT places the phantom at isocenter, the diode arrays
measure each field centroid; the phantom itself is the target. Gantry 90° and 270° are read by the sideboard arrays
12.5 cm from isocenter, so the **net gantry − couch-roll angle error must be within ±0.2° for a 0.5 mm isocenter
goal** (2.18 mm per degree; see the paper).

**Imaging W-L.** kV and MV images of the eight off-axis tungsten-carbide fiducials at 4 or 8 gantry angles, plus
collimator and couch exposures. Each MV exposure uses 2 × 2 cm MLC apertures around the fiducials. Because the
fiducials lie roughly symmetric across the MLC travel direction, each set needs two exposures, or one integrated
exposure with MLC motion (the Developer Mode version), which requires large-field IMRT planning or delivery licenses.

## Quick start

```bash
pip install -r tools/requirements.txt

# 1. Your machine name (exactly as configured in your TPS/OIS); energies kept as in the plan
python tools/rp_retarget.py rt_plans/TrueBeam_M120/DQA4_DailyQA_TrueBeam.dcm --machine-name TB3 -o my_plans

# 2. AM W-L at other energies, one plan per energy
python tools/rp_retarget.py rt_plans/TrueBeam_M120/DQA4_AMWL_TrueBeam.dcm --machine-name TB3 --energy 6X 6FFF -o my_plans

# 3. Another MLC model: built-in profile ...
python tools/rp_retarget.py rt_plans/TrueBeam_M120/DQA4_AMWL_TrueBeam.dcm --machine-name EDGE1 --profile truebeam-hd120 -o my_plans
#    ... or any machine: export ANY plan for it from your TPS and use it as the geometry template
python tools/rp_retarget.py rt_plans/TrueBeam_M120/DQA4_AMWL_TrueBeam.dcm --machine-name LINAC2 --template any_plan_for_linac2.dcm -o my_plans

python tools/rp_retarget.py --list-profiles
```

**Match the plan to your machine's energies, fields and cones** (treatment beams only; setup and imaging fields are
left alone):

```bash
# No 15X; 10X instead of 10FFF
python tools/rp_retarget.py rt_plans/TrueBeam_M120/DQA4_DailyQA_TrueBeam.dcm --machine-name TB3     --drop-energy 15X --map-energy 10FFF=10X -o my_plans

# 15 x 15 cm open photon fields instead of 20 x 20 (DQA4 range 5-20 cm; re-baseline output and profiles)
python tools/rp_retarget.py <plan> --machine-name TB3 --field-size 15 -o my_plans

# Electron cone: give the jaw opening your machine uses for that cone at each energy (from your electron beam data)
python tools/rp_retarget.py <plan> --machine-name TB3 --applicator A15 --electron-jaws 6E=200 9E=190 12E=190 16E=180 20E=180 -o my_plans

# One beam by name
python tools/rp_retarget.py <plan> --machine-name TB3 --beam-energy "16 MeV=15E" -o my_plans
```

Beam names follow the new energy ("15 MV" becomes "10 MV"), FFF fluence flags are set, and a beam changed from FFF
to flattened gets 600 MU/min. Electron jaw openings are not guessed: they differ by machine, cone and energy.

Output plans are UNAPPROVED, carry no patient or institutional identifiers, and have new UIDs. Import them into
your TPS, review every beam and control point, and validate delivery before use.

## MLC geometry dictionary

`rp_retarget.py` rebuilds each aperture on the target leaves: a target leaf pair opens if any source pair it
overlaps (inside the source jaws) is open, so the target field covers the source field; machines without
field-shaping jaws are clipped to the source jaws; closed pairs are parked as the target machine parks them. With
different leaf widths the 2 × 2 cm apertures change shape slightly: check every field in your TPS and confirm field
size detection on the device.

| Profile | Leaves (pairs × width at isocenter) | Jaws | Source | Status |
|---|---|---|---|---|
| `truebeam-m120` | 10 × 10 mm, 40 × 5 mm, 10 × 10 mm (±200 mm) | X, Y | Author's TrueBeam plans | Delivered |
| `truebeam-hd120` | 14 × 5 mm, 32 × 2.5 mm, 14 × 5 mm (±110 mm) | X, Y | Published HD120 geometry [1] | Derived only |
| `varian-ethos-halcyon` | MLCX1 28 × 10 mm (±140 mm); MLCX2 29 × 10 mm (±145 mm), half-leaf offset | none (fixed ±140 mm) | Author's Ethos plan | Converting the TrueBeam AM W-L reproduces the native Ethos AM W-L apertures exactly (automated test) |
| `elekta-agility` | 80 × 5 mm (±200 mm) | Y diaphragms | Vendor specification [2] | Not delivered |
| `elekta-mlci2` | 40 × 10 mm (±200 mm) | X, Y | Vendor specification | Not delivered |
| `varian-accela` | not yet published | — | — | Use `--template` |

**`--template` works for any machine**, including ones not listed: every RT plan stores its own leaf boundaries,
device names, closed-leaf parking positions and gaps, and the tool copies them. Profiles for new MLC models are
welcome (open an issue or pull request with a plan's leaf boundaries).

[1] Central 32 pairs 2.5 mm and outer 28 pairs 5 mm at isocenter, 22 cm span; see e.g.
[PMC7807868](https://pmc.ncbi.nlm.nih.gov/articles/PMC7807868).
[2] 160 leaves, 5 mm at isocenter, 40 × 40 cm field
([Elekta, 2012](https://ir.elekta.com/investors/press-releases/2012/agility-elektas-innovative-beam-shaping-solution-for-cancer-treatment-ships-globally)).

## Things to know before you deliver

**Developer Mode XML.**
- Angles are in **Varian scale**, not IEC (the comments give both): e.g. IEC gantry 225° is Varian 315°; collimator
  and couch 0° IEC are 180° Varian.
- **Couch Vrt/Lat/Lng in CP0 are absolute positions** for the author's room. Replace them with your phantom's
  treatment position, or remove them, before delivery.
- `MLCModel` is `NDS120` (Millennium 120). HD120 machines need the MLC positions rebuilt.
- Energy (`6x`) and dose rate (600 MU/min) are set in CP0.

**Developer Mode images: use the last frame only.** Integrated MV acquisitions write one DICOM file per recorded
frame, named `<series>-<acquisition>-<frame>.dcm` (`isocal_-000-0000.dcm` … `isocal_-000-0107.dcm`); kV images are a
single file (`isocal_-001.dcm`). Only the last frame of each acquisition is the complete image:

```bash
python tools/select_last_frames.py <session folder> --rename      # last_frames/acq000_G225_C0_T0_MV.dcm, ...
python tools/select_last_frames.py <session folder> --group-series --patient-name "DQA4^QA" --patient-id DQA4_QA --machine-name TB3
```

Originals are never modified. Series names containing hyphens are handled.

**Machine QA mode and AlignRT (VisionRT).** All SGRT-related QA was delivered in TrueBeam Machine QA mode from
DICOM files. AlignRT closes a plan it detects was loaded outside clinical Treatment mode. Workaround validated on the
author's versions: log out of the VisionRT system completely, mode up the plan in Machine QA mode, log in to AlignRT,
open the patient browser, select the patient, and select Treatment.

**Ethos plan.** Ethos writes plans in a Varian-specific DICOM class; the file keeps that class, with private tags
removed like every other plan here.

## Sharing your own files back

1. Put raw exports in `raw/` (git-ignored).
2. `python tools/rp_retarget.py raw/<plan>.dcm --machine-name TrueBeam -o rt_plans/<Machine_MLC> --name <name>`
3. `python tools/check_phi.py --forbid <institution> <machine names> <serial numbers> <staff names>`: must report 0.
4. Open a pull request.

## Citation and license

Please cite the paper if these files help your work (see [CITATION.cff](CITATION.cff)).
Code and files: [MIT](LICENSE). Not affiliated with or endorsed by Sun Nuclear, Mirion, Varian, Siemens Healthineers,
Elekta, or Vision RT. Product names are trademarks of their owners.
