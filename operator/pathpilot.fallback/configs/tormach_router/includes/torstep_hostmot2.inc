[HOSTMOT2]
DRIVER=hm2_eth
BOARD=stmc
DRIVER_PARAMS=board_ip=10.10.10.10 config="num_encoders=0 num_pwmgens=1 num_3pwmgens=0 num_stepgens=4 sserial_port_0=0xxxxxxx enable_raw=1"
# need entry to make pathpilotmanager check network
# it needs to verify the firmware revision file for an 'stmc' board
BITFILE0=placeholder
