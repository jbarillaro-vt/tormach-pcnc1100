#!/bin/bash
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


# sleeps $1 seconds, runs logrotate, goes back to sleep
# $2 is the logrotate configuration file path
# $3 is the logrotate status file path

while true; do
  #echo "logrotate $2 -s $3"
  logrotate $2 -s $3
  sleep $1
done

