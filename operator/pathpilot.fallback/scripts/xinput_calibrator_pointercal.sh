#!/bin/sh
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

# script to make the changes permanent (xinput is called with every Xorg start)
#
# can be used from Xsession.d
# script needs tee and sed (busybox variants are enough)
#
# original script: Martin Jansa <Martin.Jansa@gmail.com>, 2010-01-31
# updated by Tias Guns <tias@ulyssis.org>, 2010-02-15
# updated by Koen Kooi <koen@dominion.thruhere.net>, 2012-02-28
# modified for use by Tormach for PathPilot runtime environment, 2015-04-09

# mill/lathe gui calls this script after a 'plug in' event in case

echo "xinput_calibrator_pointercal.sh starting."

# source to set paths and file names
TSENV="$HOME/tmc/scripts/touchscreen_env"
if [ -e $TSENV ] ; then
  . $TSENV
else
  # no file to source - must not continue
  echo "Error cannot source file: $HOME/tmc/scripts/touchscreen_env"
  exit 1
fi

if [ -e $TSCALFILE ] ; then
  if grep replace $TSCALFILE ; then
    echo "Empty calibration file found, removing it"
    rm $TSCALFILE
  else
    echo "Using calibration data stored in $TSCALFILE"
    . $TSCALFILE && exit 0
  fi
else
  echo "No calibration file found: $TSCALFILE"
fi

# at this point there is no calibration file and we won't automatically create one
# we could with:
#touchscreen_calibrate.sh
