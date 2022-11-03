[REDIS]
# The 3 save args provide this logic for the RDB file format (snapshot)
#    save after 1 hour if at least 1 key has changed
#    save after 5 min if at least 100 keys have changed
#    save after 60 sec if at least 1000 keys have changed
# The appendonly db is way more durable (log structured) and will sync every second as needed
# The append only log is rewritten once it grows over 64 mb
SERVER_PATH = ~/tmc/bin/redis-server
SERVER_ARGS = --dir ~/router_data --dbfilename dump.rdb --save 3600 1 --save 300 100 --save 60 10000 --appendonly yes --appendfsync everysec --auto-aof-rewrite-percentage 100 --auto-aof-rewrite-min-size 64mb
