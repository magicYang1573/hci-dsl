# chiplet-sim-dsl

Minimal DSL to describe a chiplet platform in Python (`conf.py`) and emit a Lua config (`conf.lua`) that can be consumed directly by QBox for co-simulation with QEMU-based platforms.

## Quick start
1) Edit `conf.py` using the DSL types in `chiplet_dsl.py` (see the existing example).
2) Run the translator:
   ```bash
   python main.py --input conf.py --output conf.lua
   ```
3) Consume the generated `conf.lua` in your simulator.

## DSL recap
- Construct `ChipletPlatform(name)`.
- Add modules with `add_module(name, config)` using:
  - `CPUConfig`
  - `PeripheralConfig`
  - `DRAMConfig`
- (Optional) Connect modules with `connect_modules(src, dst, connection_type="UCIe")`.
- Call `generate_configuration(path)` (or run `main.py`) to produce Lua.

## Notes
- Default addresses/IRQs are assigned for UART, VADD, GPU, SENSOR; others auto-increment bases/IRQs.
- Loader entries default to bootstub and demo ELF; adjust in `CPUConfig.loader_entries` if needed.
- Lua output mirrors the example `conf.lua` layout in this repo.
- Generated Lua is ready to drop into QBox: QemuInstance/Router/PLIC/CLINT/bridges are emitted with bindings consistent with the sample platform.
