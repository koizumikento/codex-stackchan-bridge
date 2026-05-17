uint8 ZONE_1=1
uint8 ZONE_2=2
uint8 ZONE_3=4

uint8 INTENSITY_NONE=0
uint8 INTENSITY_LOW=1
uint8 INTENSITY_MEDIUM=2
uint8 INTENSITY_HIGH=3

string<=32 device_id
builtin_interfaces/Time stamp
uint8 zone_mask
uint8 zone_count
uint8[<=3] intensities
string<=32 surface
