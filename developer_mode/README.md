# TrueBeam Developer Mode XML

By David Barbee, PhD. Each file starts with a header naming the author, source and license.

| Folder | File | Content |
|---|---|---|
| `active_measurement_wl/` | `DQA4_AMWL_MLC.xml` | AM W-L, 28 control points: gantry 225→180 (8 angles, IEC), collimator 0/90/270, couch 0/90/270; 50 MU each, 6 MV, 600 MU/min; 2 × 2 cm MLC aperture, 2.4 cm jaws |
| `active_measurement_wl/` | `DQA4_AMWL_Jaw.xml` | Same, 2 × 2 cm jaw-defined field |
| `imaging_wl/` | (nominal Imaging W-L, to be added) | |
| `angle_error_tests/` | `DQA4_AMWL_MLC_angle_offset.xml` | AM W-L with deliberate gantry/collimator/couch offsets of 0.5–2.0° |
| `angle_error_tests/` | `DQA4_ImagingWL_angle_offset.xml` | Imaging W-L, 50 control points: 8 gantry angles with integrated MV (two MLC apertures per angle, 8 MU each) and kV, then couch and collimator MV, with deliberate angle offsets |

**Angle-error files are for testing analysis sensitivity only. Never use them for routine QA.**

> [!CAUTION]
> **Collision hazard: Active Measurement W-L moves the couch.** The AM W-L sequence rotates the couch to 90° and
> 270° (and the gantry through 8 angles) automatically in the Developer Mode XML, and through the couch-rotation
> fields in the DICOM plans. **Retract the kV and MV imager arms (or set them to mid position) before delivery.**
> Extended imager arms will collide with the couch or phantom when the couch rotates. Do a dry run, confirm
> clearance at every couch and gantry angle, watch the room monitor, and be ready to stop motion.

Before delivery:
- Angles are in Varian scale (the comments give IEC and Varian values).
- Couch Vrt/Lat/Lng in CP0 are absolute positions for the author's room: replace them with your phantom's position or
  remove them.
- `MLCModel` is `NDS120` (Millennium 120). HD120 machines need new MLC positions.
- Imaging W-L acquisitions write one DICOM file per frame: keep only the last with `../tools/select_last_frames.py`.

Developer Mode bypasses certain clinical interlocks. Read [../DISCLAIMER.md](../DISCLAIMER.md), review each file
line by line, and deliver only in non-clinical mode with no patient in the room.
