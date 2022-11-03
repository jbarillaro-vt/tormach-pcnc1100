#!/bin/sh
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

#echo 'command line args sent to ' "$0"':'
#for word in "$*"; do echo "$word"; done

# source to set paths and file names
TSENV="$HOME/tmc/scripts/touchscreen_env"
if [ -e $TSENV ] ; then
  . $TSENV
else
  # no file to source - must not continue
  echo "Error cannot source file: $HOME/tmc/scripts/touchscreen_env"
  exit 1
fi

#
# script to apply provided touchscreen calibration data - called by PathPilot MDI entry
#
# arguments are min-x max-x min-y max-y
#
# typically in the range of 200 2000 2000 200
# note that Y is inverted so the values are swapped - depending upon the touchscreen sometimes it is X that needs swapping
#

echo "xinput --set-prop --format=32 \"$TS_DEVICE\" \"Evdev Axis Calibration\"" $1 $2 $3 $4
xinput --set-prop --format=32 "$TS_DEVICE" "Evdev Axis Calibration" $1 $2 $3 $4
result=$?
echo "xinput returned $result"
exit $result
