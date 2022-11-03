#!/bin/bash
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


# once per minute check for excessive CPU use by kswapd0 and if found
# drop the caches to bring it back in check.

SLEEP_SECONDS=60

KSWAPD=kswapd

echo "$0 starting . . ."

while true; do

  CPU2=`top -b -n 1 | grep $KSWAPD | head -n 1 | awk '{print $9}'`
  if [ -z "$CPU2" ]; then
      echo "$0:  Unable to read kswapd CPU; exiting" >&2
      exit
  fi

  # truncate to integer
  CPU=${CPU2%.*}

  if [ ${CPU:-0} -gt 90 ]; then
    sudo bash -c "echo 1 > /proc/sys/vm/drop_caches"
    TIMESTAMP=`date`
    echo "$TIMESTAMP $0: cache dropped ($KSWAPD %CPU=$CPU)" >&2

    # now wait 5 seconds and log what the effect of the drop on kswapd was (if any)
    sleep 5
    CPU2=`top -b -n 1 | grep $KSWAPD | head -n 1 | awk '{print $9}'`
    # truncate to integer
    CPU=${CPU2%.*}
    TIMESTAMP=`date`
    echo "$TIMESTAMP $0: $KSWAPD %CPU 5 seconds after cache dropped = $CPU" >&2
  fi

  sleep $SLEEP_SECONDS
done
