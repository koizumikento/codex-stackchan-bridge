uint8 PLAYBACK=1
uint8 CAPTURE=2
uint8 PCM_S16LE=1
uint8 IMA_ADPCM_4BIT=2

string<=32 device_id
string<=36 command_id
uint8 direction
uint32 sequence
uint8 format
uint32 sample_rate
uint8 channels
uint8[<=1280] pcm
