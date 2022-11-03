#!/bin/sh
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

#
# script to calibrate touchscreen called by PathPilot MDI entry
#

# source to set paths and file names
TSENV="$HOME/tmc/scripts/touchscreen_env"
if [ -e $TSENV ] ; then
  . $TSENV
else
  # no file to source - must not continue
  echo "Error cannot source file: $HOME/tmc/scripts/touchscreen_env"
  exit 1
fi

echo "list of xinput devices:"
xinput --list --long
echo "\n"

echo "xinput --list-props \"$TS_DEVICE\""
xinput --list-props "$TS_DEVICE"
echo "\n"

# create TSCALFILE
TSCALDATA=`$TSCAL_BINARY --misclick 0 --output-type xinput -v $* | tee $TSLOGFILE | grep '    xinput set' | sed 's/^    //g; s/$/;/g'`
if [ ! -z "$TSCALDATA" ] ; then
  echo "$TSCALDATA" > $TSCALFILE
  echo "Calibration data stored in $TSCALFILE, log data found in $TSLOGFILE"
  echo "xinput list-props \"$TS_DEVICE\""
  xinput list-props "$TS_DEVICE"
  exit 0
fi
exit 1
