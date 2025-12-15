"""
Simple chiplet DSL translator.

This module provides a tiny domain specific language used in conf.py files to
describe a chiplet platform and emit a Lua configuration (conf.lua). The DSL is
intentionally small: construct a ChipletPlatform, add modules (CPU, DRAM,
peripherals), optionally connect them, and call generate_configuration().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


def _hex(val: int) -> str:
	"""Render an integer as an 8-digit hex literal (0xXXXXXXXX)."""

	return f"0x{val:08x}"


def _sanitize(name: str) -> str:
	"""Upper-case name -> identifier with underscores."""

	cleaned = []
	for ch in name:
		if ch.isalnum():
			cleaned.append(ch.upper())
		else:
			cleaned.append("_")
	collapsed = "".join(cleaned)
	while "__" in collapsed:
		collapsed = collapsed.replace("__", "_")
	return collapsed.strip("_")


@dataclass
class CPUConfig:
	isa: str = "riscv64"
	reset_vector: int = 0x00000000
	bootrom_base: int = 0x00000000
	bootrom_size: int = 0x2000
	clint_base: int = 0x02004000
	clint_size: int = 0x8000
	plic_base: int = 0x0C000000
	plic_size: int = 0x400000
	reset_base: int = 0x00100000
	reset_size: int = 0x1000
	loader_entries: List[Dict[str, int | str]] = field(
		default_factory=lambda: [
			{"type": "bin", "path": "fw/bootstub.bin", "address": 0x00000000},
			{"type": "bin", "path": "fw/bootstub.bin", "address": 0x00001000},
			{"type": "elf", "path": "fw/cpu_demo.elf"},
		]
	)


@dataclass
class PeripheralConfig:
	addr_space_size: int
	base: Optional[int] = None
	irq: Optional[int] = None
	moduletype: Optional[str] = None
	tx_uri: Optional[str] = None        # for sb module
	rx_uri: Optional[str] = None
	queue_capacity: int = 0       
	fresh_queue: bool = False
	max_rate: int = -1
	regshift: Optional[int] = None      # only for UART
	baudbase: Optional[int] = None      



@dataclass
class DRAMConfig:
	size_mb: int
	base: int = 0x80000000

	@property
	def size_bytes(self) -> int:
		return self.size_mb * 1024 * 1024


class ChipletPlatform:
	def __init__(self, name: str):
		self.name = name
		self._modules: Dict[str, object] = {}
		self._connections: List[Tuple[str, str, str]] = []

	def add_module(self, name: str, config: object) -> None:
		self._modules[name] = config

	def connect_modules(self, src: str, dst: str, connection_type: str = "UCIe") -> None:
		self._connections.append((src, dst, connection_type))

	def _find(self, cls, required: bool = True) -> Optional[Tuple[str, object]]:
		for name, cfg in self._modules.items():
			if isinstance(cfg, cls):
				return name, cfg
		if required:
			raise ValueError(f"No module of type {cls.__name__} found")
		return None

	def _find_all(self, cls) -> List[Tuple[str, object]]:
		return [(n, c) for n, c in self._modules.items() if isinstance(c, cls)]

	def generate_configuration(self, output_path: str) -> None:
		cpu_entry = self._find(CPUConfig)
		dram_entry = self._find(DRAMConfig, required=False)
		peripherals = self._find_all(PeripheralConfig)

		cpu_name, cpu_cfg = cpu_entry  # type: ignore[misc]
		dram_cfg = dram_entry[1] if dram_entry else None

		peripheral_layout = self._assign_peripheral_layout(peripherals)

		lines: List[str] = []
		lines.extend(self._emit_header())
		lines.extend(self._emit_base_constants(cpu_cfg, dram_cfg, peripheral_layout))
		lines.append("")
		lines.extend(self._emit_platform(cpu_cfg, dram_cfg, peripheral_layout))
		lines.append("return platform")

		Path(output_path).write_text("\n".join(lines) + "\n")

	def _assign_peripheral_layout(
		self, peripherals: Iterable[Tuple[str, PeripheralConfig]]
	) -> List[Dict[str, object]]:
		defaults = {
			"UART": {
				"lua_name": "uart0",
				"module": "uart_16550",
				"regshift": 2,
				"baudbase": 3686400,
				"const_prefix": "UART",
			},
			"VADD": {
				"lua_name": "sb_vadd",
				"module": "SbVaddBridge",
				"tx_uri": "ipc:///tmp/qbox_vadd_tx",
				"rx_uri": "ipc:///tmp/qbox_vadd_rx",
				"const_prefix": "SB_VADD",
			},
			"GPU": {
				"lua_name": "sb_cuda",
				"module": "SbCudaBridge",
				"tx_uri": "ipc:///tmp/qbox_cuda_tx",
				"rx_uri": "ipc:///tmp/qbox_cuda_rx",
				"const_prefix": "SB_CUDA",
			},
			"SENSOR": {
				"lua_name": "sb_sensor",
				"module": "SbSensorBridge",
				"tx_uri": "ipc:///tmp/qbox_sensor_tx",
				"rx_uri": "ipc:///tmp/qbox_sensor_rx",
				"const_prefix": "SB_SENSOR",
			},
		}

		layout: List[Dict[str, object]] = []
		next_base = 0x30000000
		next_irq = 8

		for name, cfg in peripherals:
			key = name.upper()
			base_info = defaults.get(key, {})
			lua_name = base_info.get("lua_name", name.lower())
			const_prefix = base_info.get("const_prefix", _sanitize(name))
			modulestype = cfg.moduletype or base_info.get("module") or "generic_device"
			base_addr = cfg.base if cfg.base is not None else base_info.get("base", next_base)
			irq = cfg.irq if cfg.irq is not None else base_info.get("irq", next_irq)
			tx_uri = cfg.tx_uri or base_info.get("tx_uri")
			rx_uri = cfg.rx_uri or base_info.get("rx_uri")
			regshift = cfg.regshift if cfg.regshift is not None else base_info.get("regshift")
			baudbase = cfg.baudbase if cfg.baudbase is not None else base_info.get("baudbase")
            
			next_base += cfg.addr_space_size
			next_irq += 1

			layout.append(
				{
					"name": name,
					"lua_name": lua_name,
					"const_prefix": const_prefix,
					"module": modulestype,
					"base": int(base_addr),
					"size": int(cfg.addr_space_size),
					"irq": int(irq) if irq is not None else None,
					"tx_uri": tx_uri,
					"rx_uri": rx_uri,
					"regshift": regshift,
					"baudbase": baudbase,
					"queue_capacity": cfg.queue_capacity,
					"fresh_queue": cfg.fresh_queue,
					"max_rate": cfg.max_rate,
				}
			)

		return layout

	def _emit_header(self) -> List[str]:
		return [
			"-- Auto-generated by chiplet_dsl",
			"",
			"local function top()",
			'    local info = debug.getinfo(2, "S").source',
			'    if info:sub(1, 1) == "@" then',
			'        info = info:sub(2)',
			"    end",
			'    local dir = info:match("(.*/)")',
			"    if dir then",
			"        return dir",
			"    end",
			'    return "./"',
			"end",
			"",
			"-- Base and Size",
			"-- Qbox Space",
		]

	def _emit_base_constants(
		self, cpu_cfg: CPUConfig, dram_cfg: Optional[DRAMConfig], peripherals: List[Dict[str, object]]
	) -> List[str]:
		lines = [
			f"local BOOTROM_BASE = {_hex(cpu_cfg.bootrom_base)}",
			f"local BOOTROM_SIZE = {_hex(cpu_cfg.bootrom_size)}",
			"",
			f"local CLINT_BASE = {_hex(cpu_cfg.clint_base)}",
			f"local CLINT_SIZE = {_hex(cpu_cfg.clint_size)}",
			f"local PLIC_BASE = {_hex(cpu_cfg.plic_base)}",
			f"local PLIC_SIZE = {_hex(cpu_cfg.plic_size)}",
			f"local RESET_BASE = {_hex(cpu_cfg.reset_base)}",
			f"local RESET_SIZE = {_hex(cpu_cfg.reset_size)}",
			"",
			"-- Base, Size, IRQ for peripheral",
			"-- Base and IRQ_ID may be automatically generated by \"Translator\"",
			"-- User Space",
		]

		if dram_cfg:
			lines.extend(
				[
					f"local DRAM_BASE = {_hex(dram_cfg.base)}",
					f"local DRAM_SIZE = {_hex(dram_cfg.size_bytes)}",
					"",
				]
			)

		for periph in peripherals:
			prefix = periph["const_prefix"]
			lines.append(f"local {prefix}_BASE = {_hex(periph['base'])}")
			lines.append(f"local {prefix}_SIZE = {_hex(periph['size'])}")
			if periph.get("irq") is not None:
				lines.append(f"local {prefix}_IRQ = {periph['irq']}")
			lines.append("")

		# trim trailing blank line
		if lines and lines[-1] == "":
			lines.pop()
		return lines

	def _emit_platform(
		self, cpu_cfg: CPUConfig, dram_cfg: Optional[DRAMConfig], peripherals: List[Dict[str, object]]
	) -> List[str]:
		lines: List[str] = []
		lines.append("platform = {")
		lines.append('    moduletype = "Container";')
		lines.append('    quantum_ns = 100000; -- 100 us global quantum')
		lines.append("")

		lines.extend(
			[
				"    router = {",
				'        moduletype = "router";',
				"    };",
				"",
				"    bootrom = {",
				'        moduletype = "gs_memory";',
				'        target_socket = { address = BOOTROM_BASE, size = BOOTROM_SIZE, bind = "&router.initiator_socket" };',
				"    };",
				"",
				"    qemu_inst_mgr = {",
				'        moduletype = "QemuInstanceManager";',
				"    };",
				"",
				"    qemu_inst = {",
				'        moduletype = "QemuInstance";',
				'        args = { "&platform.qemu_inst_mgr", "RISCV64" };',
				'        tcg_mode = "MULTI";',
				'        sync_policy = "multithread-unconstrained";',
				"    };",
				"",
				"    cpu_0 = {",
				'        moduletype = "cpu_riscv64";',
				'        args = { "&platform.qemu_inst", 0 };',
				'        mem = { bind = "&router.target_socket" };',
				'        reset = { bind = "&reset.reset" };',
				f"        reset_vector = {_hex(cpu_cfg.reset_vector)};",
				"    };",
				"",
				"    clint = {",
				'        moduletype = "riscv_aclint_mtimer";',
				'        args = { "&platform.qemu_inst" };',
				'        mem = { address = CLINT_BASE, size = CLINT_SIZE, bind = "&router.initiator_socket" };',
				'        timecmp_base = 0x0;',
				'        time_base = 0x7ff8;',
				'        provide_rdtime = true;',
				'        aperture_size = 0x10000;',
				'        num_harts = 1;',
				"    };",
				"",
				"    plic_0 = {",
				'        moduletype = "plic_sifive";',
				'        args = { "&platform.qemu_inst" };',
				'        mem = { address = PLIC_BASE, size = PLIC_SIZE, bind = "&router.initiator_socket" };',
				'        num_sources = 16;',
				'        num_priorities = 7;',
				'        priority_base = 0x0;',
				'        pending_base = 0x1000;',
				'        enable_base = 0x2000;',
				'        enable_stride = 0x80;',
				'        context_base = 0x200000;',
				'        context_stride = 0x1000;',
				'        aperture_size = 0x400000;',
				'        hart_config = "MS";',
				"    };",
				"",
				"    reset = {",
				'        moduletype = "sifive_test";',
				'        args = { "&platform.qemu_inst" };',
				'        target_socket = { address = RESET_BASE, size = RESET_SIZE, bind = "&router.initiator_socket" };',
				"    };",
				"",
				"    loader = {",
				'        moduletype = "loader";',
				'        initiator_socket = { bind = "&router.target_socket" };',
			]
		)

		for entry in cpu_cfg.loader_entries:
			if entry.get("type") == "bin":
				lines.append(
					f"        {{ bin_file = top() .. \"{entry['path']}\", address = {_hex(entry['address'])} }};"
				)
			elif entry.get("type") == "elf":
				lines.append(f"        {{ elf_file = top() .. \"{entry['path']}\" }};")

		lines.extend(
			[
				'        reset = { bind = "&reset.reset" };',
				"    };",
				"",
			]
		)

		for periph in peripherals:
			lines.extend(self._emit_peripheral(periph))

		if dram_cfg:
			lines.extend(
				[
					"    dram = {",
					'        moduletype = "gs_memory";',
					'        target_socket = { address = DRAM_BASE, size = DRAM_SIZE, bind = "&router.initiator_socket" };',
					"    };",
				]
			)

		lines.append("}")
		return lines

	def _emit_peripheral(self, periph: Dict[str, object]) -> List[str]:
		module = periph["module"]
		lua_name = periph["lua_name"]
		prefix = periph["const_prefix"]
		base_line = f"        target_socket = {{ address = {prefix}_BASE, size = {prefix}_SIZE, bind = \"&router.initiator_socket\" }};"
		is_bridge = "Bridge" in module or str(module).lower().startswith("sb")

		block: List[str] = [f"    {lua_name} = {{", f'        moduletype = "{module}";']

		if module == "uart_16550":
			block.append('        args = { "&platform.qemu_inst" };')
			block.append(
				f"        mem = {{ address = {prefix}_BASE, size = {prefix}_SIZE, bind = \"&router.initiator_socket\" }};"
			)
			irq_val = periph.get("irq")
			if irq_val is not None:
				block.append(f"        irq_out = {{ bind = \"&plic_0.irq_in_{irq_val}\" }};")
			regshift = periph.get("regshift")
			baudbase = periph.get("baudbase")
			if regshift is not None:
				block.append(f"        regshift = {regshift};")
			if baudbase is not None:
				block.append(f"        baudbase = {baudbase};")
		elif is_bridge:
			block.append(base_line)
			irq_val = periph.get("irq")
			if irq_val is not None:
				block.append(f"        irq = {{ bind = \"&plic_0.irq_in_\" .. tostring({prefix}_IRQ) }};")
			tx_uri = periph.get("tx_uri")
			rx_uri = periph.get("rx_uri")
			block.append(f"        tx_uri = \"{tx_uri or 'ipc:///tmp/qbox_tx'}\";")
			block.append(f"        rx_uri = \"{rx_uri or 'ipc:///tmp/qbox_rx'}\";")
			block.append(f"        queue_capacity = {periph.get('queue_capacity')};")
			block.append(f"        fresh_queue = {'true' if periph.get('fresh_queue') else 'false'};")
			block.append(f"        max_rate = {periph.get('max_rate')};")
		else:
			block.append(base_line)
			irq_val = periph.get("irq")
			if irq_val is not None:
				block.append(f"        irq = {{ bind = \"&plic_0.irq_in_{irq_val}\" }};")

		block.append("    };")
		block.append("")
		return block
