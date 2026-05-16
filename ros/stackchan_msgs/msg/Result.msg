uint8 STATE_ACCEPTED=1
uint8 STATE_COMPLETED=2
uint8 STATE_REJECTED=3
uint8 STATE_TIMEOUT=4

bool ok
uint8 state
string<=48 error_code
string<=160 message
bool recoverable
