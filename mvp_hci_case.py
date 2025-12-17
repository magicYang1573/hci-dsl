# hci DSL case for MVP platform

from hci_dsl import *

platform = hciPlatform("MVP")

cpu_config = CPUConfig(isa="riscv64")
platform.add_module("CPU", cpu_config)

uart_peripheral_config = PeripheralConfig(addr_space_size=0x1000)
platform.add_module("UART", uart_peripheral_config)

vadd_peripheral_config = PeripheralConfig(addr_space_size=0x1000)
platform.add_module("VADD", vadd_peripheral_config)

gpu_peripheral_config = PeripheralConfig(addr_space_size=0x1000)
platform.add_module("GPU", gpu_peripheral_config)

sensor_peripheral_config = PeripheralConfig(addr_space_size=0x1000)
platform.add_module("SENSOR", sensor_peripheral_config)

dram_config = DRAMConfig(size_mb=256)
platform.add_module("DRAM", dram_config)

platform.connect_modules("CPU", "UART", connection_type="UCIe")
platform.connect_modules("CPU", "VADD", connection_type="UCIe")
platform.connect_modules("CPU", "GPU", connection_type="UCIe")
platform.connect_modules("CPU", "SENSOR", connection_type="UCIe")
platform.connect_modules("CPU", "DRAM", connection_type="DDR5")

platform.generate_configuration("mvp_hci_config.lua")