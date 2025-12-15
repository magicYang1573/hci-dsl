# chiplet-sim-dsl

Minimal DSL to describe a chiplet platform in Python (`conf.py`) and emit a Lua config (`conf.lua`) that can be consumed directly by QBox for co-simulation with QEMU-based platforms.

## Quick start
1) Open `mvp_chiplet_case.py` and build a `ChipletPlatform` named `platform` using the configs in `chiplet_dsl.py` (the repo ships a minimal example).
2) Translate to Lua:
  ```bash
  python mvp_chiplet_case.py --output mvp_chiplet_conf.lua
  ```
3) Use the emitted `mvp_chiplet_conf.lua` directly in QBox/QEMU co-sim.

## DSL recap
- Construct `ChipletPlatform(name)`.
- Add modules with `add_module(name, config)` using:
  - `CPUConfig`
  - `PeripheralConfig`
  - `DRAMConfig`
- (Optional) Connect modules with `connect_modules(src, dst, connection_type="UCIe")`.
- Call `generate_configuration(path)` to produce Lua.

## Notes
- Current supports: UART, VADD, GPU, SENSOR (addresses/IRQs/URIs); automatically generate auto-incremented bases/IRQs.
- Loader entries default to bootstub + demo ELF; tweak `CPUConfig.loader_entries` to point at your firmware images.
- The generated Lua matches the structure of the provided `mvp_chiplet_ref.lua` (Container, QemuInstance, router, boot ROM, CLINT, PLIC, reset, loader, peripherals, DRAM) and is ready for QBox.
