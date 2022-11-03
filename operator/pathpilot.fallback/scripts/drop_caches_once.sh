#!/bin/bash

sync
sudo bash -c "echo 3 > /proc/sys/vm/drop_caches"
echo "File system flushed and cache memory returned to VM system."
