# Disclaimer

**Read this before using any file in this repository.**

1. **Reference only, not a medical device.** These files and tools are shared for education and research to help
   qualified medical physicists set up quality assurance. They are not a commercial product and are not cleared or
   approved by any regulatory body.

2. **Limited validation.** Plans marked "Delivered" in the README were delivered by the author on the listed machine
   models and software versions only. Files marked **DERIVED** (for example the HD120 AM W-L plan) and every plan made
   with `rp_retarget.py` for another machine were **not delivered by the author**. The Elekta and Accela profiles are
   untested. Plans edited with `rp_retarget.py` (energies, field size, applicator) must be re-baselined and validated.

3. **Collision hazard (Active Measurement W-L).** The AM W-L sequences rotate the couch to 90° and 270° and move
   the gantry through 8 angles; the Developer Mode XML does so automatically without operator input. Retract the kV
   and MV imager arms (or set them to mid position) before delivery: extended imager arms will collide with the
   couch or phantom when the couch rotates. Dry-run every sequence, confirm clearance at every angle, monitor the
   room, and be ready to stop motion. The author accepts no liability for collisions or equipment damage.

4. **Angle-error test files.** Files in `developer_mode/angle_error_tests/` deliberately command wrong gantry,
   collimator and couch angles to test analysis sensitivity. They must never be used for routine QA.

5. **You are responsible for validation.** Before any use, a qualified medical physicist must import and review every
   beam and control point in their own treatment planning system, confirm machine name, energy, dose rate, MU, jaw and
   MLC positions, gantry/collimator/couch angles, and imaging settings, perform a dry run, and validate delivery and
   analysis on their own equipment under local physics supervision and institutional policy.

6. **Developer Mode.** TrueBeam Developer Mode bypasses certain clinical interlocks and requires appropriate licensing
   and authorization from Varian. The XML files contain absolute couch positions for the author's room that must be
   changed. Use it only in non-clinical mode, with no patient in the room, under the conditions of
   your institution's Developer Mode agreement. Developer Mode XML files must be reviewed line by line before delivery.

7. **No vendor endorsement.** This work is not affiliated with, reviewed by, or endorsed by Sun Nuclear, Mirion,
   Varian, Siemens Healthineers, Elekta, or Vision RT. Vendor software updates may change behavior; findings apply to
   the versions tested.

8. **No patient data.** All plans are phantom QA plans with identifiers removed. Do not commit files containing
   patient or institutional identifiers; run `tools/check_phi.py` before every contribution.

9. **No warranty.** THE FILES AND SOFTWARE ARE PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED. IN NO
   EVENT SHALL THE AUTHOR BE LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER LIABILITY ARISING FROM THEIR
   USE. See [LICENSE](LICENSE).
