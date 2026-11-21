# Smart Home Voice AI — KiCad 10 Full-System 3D Assembly

Generic, deterministic, re-runnable KiCad 10 full-system hardware assembly project combining the Central Hub PCB (`smarthome_hub.kicad_pcb`), a seated NodeMCU ESP8266 v2 Amica (`Z = +8.5 mm` on `U1`/`U2`), all **14 off-board actuators, sensors, and power modules**, all **40 color-coded 3D Dupont/screw-terminal wires (`W01..W40`)**, and **15 raised 3D nameplate label plaques**.

> **Zero fan, zero AC, zero IR anywhere.**
> `hardware/kicad/smarthome_hub/` is treated strictly **read-only** and is never modified by this generator.

---

## Single-Command Regeneration

### Regenerate from the default 80x65 mm Hub PCB
```powershell
& "C:\Users\LENOVO\AppData\Local\Programs\KiCad\10.0\bin\python.exe" `
    hardware/kicad/smarthome_assembly/build_assembly.py
```

### Regenerate from ANY redesigned Hub PCB (e.g., 100x80 mm)
All board dimensions, connector coordinates (`J1..J15`, `U1`, `U2`), edge assignments, module placements, NodeMCU seating, wire endpoints, and banner text (`SMARTHOME HUB ASSEMBLY (<W>X<H> MM)`) are computed **dynamically** via KiCad 10 `pcbnew` — zero hardcoded board dimensions or fixed pad coordinates:

```powershell
& "C:\Users\LENOVO\AppData\Local\Programs\KiCad\10.0\bin\python.exe" `
    hardware/kicad/smarthome_assembly/build_assembly.py `
    --hub-pcb path/to/redesigned_100x80_hub.kicad_pcb `
    --out-dir hardware/kicad/smarthome_assembly
```

### Regenerate + Render 3D Views (`top`, `iso`, `closeup`)
```powershell
& "C:\Users\LENOVO\AppData\Local\Programs\KiCad\10.0\bin\python.exe" `
    hardware/kicad/smarthome_assembly/build_assembly.py `
    --render-dir path/to/renders `
    --render-width 1920 --render-height 1080
```

### CLI Options
| Flag | Default | Description |
|---|---|---|
| `--hub-pcb` | `hardware/kicad/smarthome_hub/smarthome_hub.kicad_pcb` | Read-only source hub `.kicad_pcb` (any size/origin) |
| `--out-dir` | `hardware/kicad/smarthome_assembly` | Output KiCad 10 assembly project directory |
| `--manifest` | `hardware/kicad/smarthome_assembly/3dmodels/modules_manifest.json` | 3D CAD module manifest (dimensions, pins, Z offsets) |
| `--render-dir` | *(omitted)* | Optional output directory for `kicad-cli pcb render` PNGs |
| `--render-width` / `--render-height` | `1600` / `1000` | Rendered image resolution in pixels |
| `--render-quality` | `basic` | KiCad 3D render quality (`basic`, `high`, `user`, `job_settings`) |
| `--no-verify` | `False` | Skip strict overlap/wiring self-verification (not recommended) |

---

## Project Contents

| File / Directory | Purpose |
|---|---|
| `build_assembly.py` | Pure stdlib + KiCad 10 `pcbnew` deterministic assembly generator & verifier |
| `build_3dmodels.py` | FreeCAD 1.1 parametric 3D CAD generator for all 15 `.wrl` + `.step` module models |
| `smarthome_assembly.kicad_pro` | Self-contained KiCad 10 project file |
| `smarthome_assembly.kicad_pcb` | Complete 2D + 3D assembly board (hub + 15 modules + 2D/3D wires + 2D/3D labels) |
| `fp-lib-table` | Project footprint library table referencing `${KIPRJMOD}/smarthome_modules.pretty` + KiCad 10 standard libs |
| `smarthome_modules.pretty/` | 17 deterministic KiCad 10 `.kicad_mod` footprints (15 modules + `Assembly_Wiring_Harness` + `Assembly_Labels`) |
| `3dmodels/*.wrl`, `*.step` | Datasheet-accurate multi-color 3D models + `modules_manifest.json` |
| `3dmodels/wiring_harness.wrl` | Generated 3D VRML 2.0 harness: all 40 colored wires (`W01..W40`, `Ø1.30 mm`) + 49 matte-black Dupont boots |
| `3dmodels/assembly_labels.wrl` | Generated 3D VRML 2.0 dark-slate beveled nameplates with category borders & raised white vector text |
| `assembly_verification.json` | Machine-readable verification proof (dimensions, alignment, 40/40 wires, 0 overlaps, clearances) |

---

## How the Assembly Works

1. **Dynamic Hub Parsing**: Loads `--hub-pcb` via `pcbnew.LoadBoard()`, preserving all original `Edge.Cuts`, copper traces, zones, mounting holes, silkscreen, and hub footprints/3D models intact. Measures the exact board outline and every pad coordinate of `J1..J15`, `U1`, `U2`.
2. **Dynamic Placement Engine**:
   - Snaps `M_NODEMCU` (`nodemcu_v2_amica`) to the exact midpoint and orientation of `U1`/`U2` at `Z = +8.5 mm` (`0.000 mm` pad alignment error).
   - Assigns all 14 off-board modules around the four hub edges close to their connected headers (with `yl69_soil_probe` paired to `soil_lm393_board` and `speaker_28mm` paired to `pam8403_amp`), rotated so pins face their hub/companion connections.
   - Runs anchored 1D interval relaxation + a 2D corner clearance guard across all modules and plaques to guarantee `>= 6.0 mm` inter-module clearance and `0` XY overlaps on any hub board size.
3. **Exact Pad-Based 3D Dupont Wiring (`wiring_harness.wrl`)**:
   - Reads the **actual** rotated world `(X, Y)` of every module pad directly from `pcbnew` (`pad.GetPosition()`) after footprint placement.
   - Routes all **40 wires (`W01..W40`)** from `hardware/wiring_contract.py` (36 hub-to-module + 4 inter-module: `W28/W29` PAM8403→Speaker BTL, `W36/W37` LM393→YL-69) using the exact SSOT `WIRE_COLORS` palette.
   - Routes `W13`/`W14` (`J8 RLY1_SW` → Relay 1 `COM`/`NO`) cleanly over the hub (apex `Z = 23.0..24.6 mm`, verified `>= 1.61 mm` surface clearance above NodeMCU top `15.64 mm` and `>= 0.55 mm` surface clearance above Relay 1's cube `18.5 mm`, zero clipping).
   - Also draws 2D wire polylines on `User.1` (power), `User.2` (GND), `User.3` (signals), and `User.4` (inter-module) for 2D PCB Editor clarity.
4. **3D & 2D Readable Labels (`assembly_labels.wrl` + `F.SilkS` + `Dwgs.User`)**:
   - Because KiCad's 3D viewer clips `F.SilkS` outside `Edge.Cuts`, every module gets a 3D beveled dark-slate plaque (`Z = 0.0..0.75 mm`) with category-colored accent rim (blue = Sensor, amber = Actuator, red = Power, cyan = Title Banner) and crisp raised pure-white stroke-vector lettering (`Z = 0.75..1.40 mm`), plus matching native KiCad text on `F.SilkS` and `Dwgs.User`.

---

## Verification Summary

Verified against `hardware/kicad/smarthome_hub/smarthome_hub.kicad_pcb` (80.0 x 65.0 mm) and a synthetic 100.0 x 80.0 mm redesigned hub board:

- **Modules placed**: `15 / 15` (`nodemcu_v2_amica` + 14 off-board modules)
- **NodeMCU `U1`/`U2` pad alignment error**: `0.000 mm`
- **Wires resolved**: `40 / 40` (`W01..W40`) + `49` matte-black Dupont boots
- **3D label plaques**: `15 / 15` (14 module plaques + dynamic title banner)
- **XY bounding-box overlaps**: `0`
- **Minimum inter-module/plaque clearance**: `8.0 mm` (`>= 6.0 mm` required)
- **Forbidden hardware tokens (fan / AC / IR)**: `0`
