#!/bin/bash

#-------------------------------------------------------------------------------------------
# this script is run by postinstall.sh to apply an updates to the OS image that may be needed
# postinstall exports the POST_INSTALL_TXT variable so that logging is consistent
#
# install any updates for a specific kernel version
# this will get run repeatedly so make sure that any actions are harmless if run more than once
#
# the current directory is $HOME
# this script runs from $HOME/(version of software)/image-updates/(kernel version)/install.sh
#

TIMESTAMP=`date`
echo "----------------------------------------------------------------------------------------------------------" >> $LOGFILE
echo "$TIMESTAMP: image update script running for 4.11.9-rt7" >> $LOGFILE

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
echo "script directory: "$SCRIPT_DIR &>>$LOGFILE
TARBALL_DIR=$(dirname $SCRIPT_DIR)
echo "tarball directory: "$TARBALL_DIR &>>$LOGFILE

#-------------------------------------------------------------------------------------------
# Replace the USB serial controller so that it properly recognizes the ATC and USBIO boards.
#
echo "sudo cp $SCRIPT_DIR/cp210x.ko /lib/modules/4.11.9-rt7/kernel/drivers/usb/serial/" &>>$LOGFILE
sudo cp "$SCRIPT_DIR/cp210x.ko" /lib/modules/4.11.9-rt7/kernel/drivers/usb/serial/ &>>$LOGFILE

#-------------------------------------------------------------------------------------------
# Install the cloud-guest-utils package for the growpart tool which can grow partitions without reboot
# in a single command (much simpler than the fdisk delete and recreate and reboot stuff).
#
echo "installing cloud-guest-utils" &>>$LOGFILE
dpkg-query --status cloud-guest-utils > /dev/null
if [ $? -eq 0 ]; then
    echo
    echo "cloud-guest-utils already on the box" &>>$LOGFILE
    echo
else
    sudo dpkg --install $SCRIPT_DIR/cloud-guest-utils*.deb &>>$LOGFILE
    if [ $? -ne 0 ]; then
        echo "cloud-guest-utils install failed." &>>$LOGFILE
    fi
fi

TIMESTAMP=`date`
echo "$TIMESTAMP: install.sh has finished" &>>$LOGFILE
echo "----------------------------------------------------------------------------------------------------------" &>> $LOGFILE

exit 0
