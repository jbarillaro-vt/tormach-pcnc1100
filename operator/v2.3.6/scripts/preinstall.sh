#!/bin/bash
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


# this is a place holder for preinstall script run before a new tarball is put place
# by the operator_login script

# runtime context:
# this script is running out of /home/operator/vN.N.N/scripts/preinstall.sh
# /home/operator/tmc is a symlink to the current version which is NOT vN.N.N
# it might be OLDER or might be NEWER
# it might have vN.N.N form or have trailing letters to deal with (ugh!)

#
# BE VERY CAREFUL so this script will run correctly even on ancient PathPilot 1.x
# systems.
#

LOGFILE=$HOME/preinstall.txt
export LOGFILE

echo "" &>>$LOGFILE
echo "" &>>$LOGFILE
echo "" &>>$LOGFILE
echo "----------------------------------------------------------------------------------------" &>>$LOGFILE
TIMESTAMP=`date`
echo "$TIMESTAMP: preinstall script has run" >> $LOGFILE

# get the directory from where this script is running
prg=$0
if [ ! -e "$prg" ]; then
  case $prg in
    (*/*) exit 1;;
    (*) prg=$(command -v -- "$prg") || exit;;
  esac
fi
dir=$(
  cd -P -- "$(dirname -- "$prg")" && pwd -P
) || exit
prg=$dir/$(basename -- "$prg") || exit
SCRIPT_DIR="$dir"
echo "script directory: "$SCRIPT_DIR &>> $LOGFILE

# REMEMBER!  We CANNOT use the tmc symlink here because that is the CURRENT version, not the
# version that this preinstall.sh script is part of!
PATHPILOT_DIR=`realpath "$dir"/..`
echo "PathPilot directory: $PATHPILOT_DIR" >> $LOGFILE

echo "Current working directory is:" >> $LOGFILE
pwd >> $LOGFILE

# activate THIS version's virtualenv python environment
# because the pathpilotmanager.py that is running us is STILL the previous version
# and our inherited virtualenv is the OLD one also

# PathPilot 1.x has no concept of virtual environments and the code will break.
KERNEL_VERSION=`uname -r`

VENV_DIR="$PATHPILOT_DIR/venv"
if [ -d $VENV_DIR ]; then
  if [ $KERNEL_VERSION != "2.6.32-122-rtai" ]; then
    echo "Entering Python virtual environment: $VENV_DIR" >> $LOGFILE
    source $VENV_DIR/bin/activate
  else
    echo "Detected PathPilot 1.x kernel so skipping venv" >> $LOGFILE
  fi
else
  echo "No Python virtual environment available in this version." >> $LOGFILE
fi

# show the EULA for this new version and see if the customer accepts it or not.
echo "python $PATHPILOT_DIR/python/eula/eula.py $PATHPILOT_DIR" >> $LOGFILE
python "$PATHPILOT_DIR/python/eula/eula.py" $PATHPILOT_DIR >> $LOGFILE
PYTHON_RESULT=$?
if [ $PYTHON_RESULT == 0 ]; then
    # eula accepted - keep going.
    echo "python $SCRIPT_DIR/preinstall.py" >> $LOGFILE
    python $SCRIPT_DIR/preinstall.py >> $LOGFILE
    PYTHON_RESULT=$?
fi

echo "$TIMESTAMP: preinstall.py returned $PYTHON_RESULT" >> $LOGFILE

exit $PYTHON_RESULT
