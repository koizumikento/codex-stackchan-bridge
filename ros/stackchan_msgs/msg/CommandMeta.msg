uint8 PRIORITY_LOW=0
uint8 PRIORITY_NORMAL=1
uint8 PRIORITY_HIGH=2
uint8 PRIORITY_SAFETY=3

string<=32 device_id
string<=36 command_id
string<=32 source
builtin_interfaces/Time created_at
uint8 priority
