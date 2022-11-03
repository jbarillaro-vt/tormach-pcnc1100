#!/bin/bash
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

echo "Uninstalling Dropbox software . . ."

#if dropbox already running
killall -q -0 dropbox
STATUS=$?
if [ $STATUS -eq 0 ]; then
  echo "Stopping currently running Dropbox process"
  killall -q -9 dropbox
  STATUS=$?
  if [ $? -ne 0 ]; then
    echo "Error stopping Dropbox process"
    exit 1
  fi
fi

#  remove ~/.dropbox-dist
rm -rf $HOME/.dropbox-dist

#  remove ~/.dropbox
rm -rf $HOME/.dropbox

#  remove python dropbox bootstrapper and cli
rm -f $HOME/dropbox.py

# removing the dropbox local sync folder(s) is handled by the dropbox_helper.py app
# so no need to do it here.

exit 0
