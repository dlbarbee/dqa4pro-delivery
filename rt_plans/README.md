# DICOM RT plans (Machine QA mode)

Phantom QA plans for the Daily QA 4 Pro by David Barbee, PhD. Patient `DQA4^QA` / `DQA4_QA`, status UNAPPROVED,
dates set to 2026-01-01, all UIDs regenerated, all vendor private tags removed. Each plan's RT Plan Description repeats
the author, source and validation note.

> [!CAUTION]
> **Collision hazard: Active Measurement W-L moves the couch.** The AM W-L sequence rotates the couch to 90° and
> 270° (and the gantry through 8 angles) automatically in the Developer Mode XML, and through the couch-rotation
> fields in the DICOM plans. **Retract the kV and MV imager arms (or set them to mid position) before delivery.**
> Extended imager arms will collide with the couch or phantom when the couch rotates. Do a dry run, confirm
> clearance at every couch and gantry angle, watch the room monitor, and be ready to stop motion.

| Folder | File | Notes |
|---|---|---|
| `TrueBeam_M120/` | `DQA4_DailyQA_TrueBeam.dcm` | Complete daily QA: setup fields, photon and EDW dosimetry, AM W-L, electrons (20 × 20 cone). The "20 MeV" beam was exported at 16 MeV and corrected to 20 MeV here |
| `TrueBeam_M120/` | `DQA4_AMWL_TrueBeam.dcm` | Stand-alone AM W-L (14 fields) |
| `TrueBeam_M120/` | `DQA4_ImagingWL_TrueBeam.dcm` | Imaging W-L for Machine QA mode: 8 kV setup fields, 12 MV fields of two step-and-shoot segments (two sets of fiducial apertures, half-field jaws) with integrated portal imaging; needs IMRT delivery licensing |
| `Edge_HD120/` | `DQA4_DailyQA_Edge.dcm` | Jaw-defined daily QA dosimetry (no MLC, so no conversion needed) |
| `Edge_HD120/` | `DQA4_AMWL_Edge_HD120_DERIVED.dcm` | AM W-L converted to HD120 by `rp_retarget.py`; **not delivered by the author** |
| `Edge_HD120/` | `DQA4_ImagingWL_Edge_HD120_DERIVED.dcm` | Imaging W-L converted to HD120; fiducial apertures identical, outer scaling strips at \|Y\| 110–120 mm lost on gantry-0° fields; **not delivered by the author** |
| `Ethos/` | `DQA4_DailyQA_Ethos.dcm` | 6FFF dosimetry and AM W-L planned in the Ethos TPS (no couch rotation) |

Field sizes: dosimetry 20 × 20 cm; AM W-L 2 × 2 cm MLC aperture with 2.2 cm jaws (TrueBeam) or MLC only (Ethos);
50 MU per AM W-L field, 100 MU per dosimetry field. Couch angles in the TrueBeam plans follow IEC 61217
(beam "AM G0 T90" is couch 270° IEC).

Not included: the CT and structure set of the phantom. Use your own CT of your device as the reference image so
IGRT registers to your phantom and setup.

Set your machine name, energies, open field size and electron cone with `../tools/rp_retarget.py`; see the main README. Always review
the result in your TPS and validate delivery before use.
