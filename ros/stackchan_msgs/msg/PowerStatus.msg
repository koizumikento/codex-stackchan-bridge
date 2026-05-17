uint8 POWER_SOURCE_UNKNOWN=0
uint8 POWER_SOURCE_BATTERY=1
uint8 POWER_SOURCE_USB=2
uint8 POWER_SOURCE_EXTERNAL=3

string<=32 device_id
builtin_interfaces/Time stamp
float32 voltage_v
float32 current_ma
float32 power_mw
float32 percentage
uint8 power_source
bool charging
bool powered
bool low_battery
bool brownout_risk
string<=32 fault_code
