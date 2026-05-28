uint8 JPEG=1

string<=32 device_id
string<=36 command_id
uint32 sequence
uint32 total_chunks
uint32 total_bytes
uint8 format
uint32 width
uint32 height
uint8 quality
bool end_of_stream
uint8[<=256] data
