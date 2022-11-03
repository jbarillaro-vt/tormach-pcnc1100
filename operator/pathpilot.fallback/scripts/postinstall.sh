#!/bin/bash
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

# runtime context:
# this is the postinstall script run after a new tarball is put place
# and after the ~/tmc symlink has been moved to the new directory
# by the operator_login script
# the current directory is $HOME
# this script runs from $HOME/(version of software)/scripts

# Handy for debugging and profiling
#set -x
#PS4='$(date "+%s.%N")\011 '

LOGFILE=$HOME/postinstall.txt
export LOGFILE

RUNNING_FROM_TTY=0
if tty -s; then
  RUNNING_FROM_TTY=1
fi

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
TARBALL_DIR=$(dirname $SCRIPT_DIR)

echo "" &>>$LOGFILE
echo "" &>>$LOGFILE
echo "" &>>$LOGFILE
echo "----------------------------------------------------------------------------------------" &>>$LOGFILE
echo "New PathPilot Version:" &>>$LOGFILE
echo "cat $TARBALL_DIR/version.json" &>>$LOGFILE
cat $TARBALL_DIR/version.json &>>$LOGFILE
TIMESTAMP=`date`
echo "$TIMESTAMP: postinstall script has started" >> $LOGFILE
echo "script directory: "$SCRIPT_DIR &>>$LOGFILE
echo "tarball directory: "$TARBALL_DIR &>>$LOGFILE

# activate THIS version's virtualenv python environment
# because the pathpilotmanager.py that is running us is STILL the previous version
# and our inherited virtualenv is the OLD one also

VENV_DIR="$HOME/tmc/venv"
if [ -d $VENV_DIR ]; then
  echo "Entering Python virtual environment: $VENV_DIR" >> $LOGFILE
  source $VENV_DIR/bin/activate
else
  echo "No Python virtual environment available in this version." >> $LOGFILE
fi

if [ $RUNNING_FROM_TTY -eq 0 ]; then
    ls -lR $TARBALL_DIR &>>$LOGFILE
fi

#-------------------------------------------------------------------------------------------
# Slap up the status window letting user know we're installing. Sometimes the EULA in the preinstall
# can cover up the status window that pathpilotmanager is showing and its not pumping gtk paint events
# so it ends up as a white rectangle that looks locked up and broken for a long time.
# Don't bother in dev buidls from a terminal

INSTALLWINDOW_PID=0
if [ $RUNNING_FROM_TTY -eq 0 ]; then
    $SCRIPT_DIR/installwindow.py &
    INSTALLWINDOW_PID=$!
    echo "INSTALLWINDOW_PID: $INSTALL_WINDOW_PID"
fi

#-------------------------------------------------------------------------------------------
# Check if the kernel version we are running has any updates to install

KERNEL_VERSION=`uname -r`
echo "Checking for any image updates for kernel $KERNEL_VERSION" &>>$LOGFILE
if [ -f "$TARBALL_DIR/image-updates/$KERNEL_VERSION/install.sh" ]; then
  echo "Running $TARBALL_DIR/image-updates/$KERNEL_VERSION/install.sh" &>>$LOGFILE
  "$TARBALL_DIR/image-updates/$KERNEL_VERSION/install.sh"
fi

#-------------------------------------------------------------------------------------------
# copy threading diameter tables to ~/gcode/thread_data

# create directory if it does not exist
THREAD_DIR=$HOME/gcode/thread_data
echo "thread data directory: $THREAD_DIR" &>>$LOGFILE
if [ ! -d "$THREAD_DIR" ]; then
  # make directory (including parents if needed)
  echo "mkdir -p $THREAD_DIR" &>>$LOGFILE
  mkdir -p "$THREAD_DIR" &>>$LOGFILE
fi

for THREAD_FILE in threads_sae.txt threads_metric.txt; do
  # copy and preserve attributes, overwriting existing file if exists
  echo "cp -a $TARBALL_DIR/$THREAD_FILE $THREAD_DIR/$THREAD_FILE" &>>$LOGFILE
  cp -a $TARBALL_DIR/$THREAD_FILE $THREAD_DIR/$THREAD_FILE &>>$LOGFILE
done


##############################################################################
# deal with release notes (pdf) file
# create release notes directory
RNOTES_DIR=$HOME/gcode/ReleaseNotes
echo "release notes directory: $RNOTES_DIR" &>>$LOGFILE
if [ ! -d "$RNOTES_DIR" ]; then
  echo "mkdir -p $RNOTES_DIR"  &>>$LOGFILE
  mkdir -p "$RNOTES_DIR" &>>$LOGFILE
fi

# don't bother with release note updates for terminal runs
if [ $RUNNING_FROM_TTY -eq 0 ]; then
    VERSION_STR=$(head -n 1 $TARBALL_DIR/version.txt)
    SRC_RELEASE_NOTES_PDF=SB0046_PathPilot_Release_Notes_$VERSION_STR.pdf

    # copy and preserve attributes of release notes pdf.
    # we don't care about overwritting, or are doing so on purpose.
    # the tarball packaging step now does all the renaming and extension lowercase work.
    # all we need to do is replace the CurrentRelease.pdf.
    #
    # remove whatever the old CurrentRelease.pdf was. We will hopefully re-create it by matching the version
    # but if not, at least it isn't misleading someone since it won't match whatever version we are actually
    # running (maybe a pre-release)
    echo "rm $RNOTES_DIR/CurrentRelease.pdf" &>>$LOGFILE
    rm $RNOTES_DIR/CurrentRelease.pdf &>>$LOGFILE

    # Remove all *.PDF debris because of the older broken logic that resulted in multiple copies of
    # each release note being left over.
    echo "rm -v $RNOTES_DIR/*.PDF $RNOTES_DIR/*.pdf" &>>$LOGFILE
    rm -v $RNOTES_DIR/*.PDF $RNOTES_DIR/*.pdf &>>$LOGFILE

    echo "cp -av $TARBALL_DIR/releasenotes/*.pdf  $RNOTES_DIR/" &>>$LOGFILE
    cp -av $TARBALL_DIR/releasenotes/*.pdf  $RNOTES_DIR/  &>>$LOGFILE

    echo "cp -av $TARBALL_DIR/releasenotes/$SRC_RELEASE_NOTES_PDF  $RNOTES_DIR/CurrentRelease.pdf" &>>$LOGFILE
    cp -av $TARBALL_DIR/releasenotes/$SRC_RELEASE_NOTES_PDF  $RNOTES_DIR/CurrentRelease.pdf  &>>$LOGFILE
fi


##############################################################################
# replace ~/operator_login with new one only if the file in ~/ is different from the file in this new install
echo 'testing if ~/operator_login needs to be replaced' &>>$LOGFILE
if ! cmp ~/operator_login $TARBALL_DIR/operator_login >/dev/null 2>&1
then
  echo "replacing ~/operator_login" &>>$LOGFILE
  echo "cp -a $TARBALL_DIR/operator_login $HOME/ &>>$LOGFILE" &>>$LOGFILE
  cp -a $TARBALL_DIR/operator_login $HOME/ &>>$LOGFILE
fi

##############################################################################
# replace ~/monitorWatch with new one only if the file in ~/ is different from the file in this new install
echo 'testing if ~/monitorWatch needs to be replaced'  &>>$LOGFILE
if ! cmp ~/monitorWatch $TARBALL_DIR/monitorWatch >/dev/null 2>&1
then
  echo "replacing ~/monitorWatch" &>>$LOGFILE
  echo "cp -a $TARBALL_DIR/monitorWatch $HOME/ &>>$LOGFILE" &>>$LOGFILE
  cp -a $TARBALL_DIR/monitorWatch $HOME/ &>>$LOGFILE
fi

##############################################################################
# replace ~/tidy_image.sh with new one only if the file in ~/ is different from the file in this new install
echo 'testing if ~/tidy_image.sh needs to be replaced' &>>$LOGFILE
if ! cmp ~/tidy_image.sh $TARBALL_DIR/scripts/tidy_image.sh >/dev/null 2>&1
then
  echo "replacing ~/tidy_image.sh" &>>$LOGFILE
  echo "cp -a $TARBALL_DIR/scripts/tidy_image.sh $HOME/ &>>$LOGFILE" &>>$LOGFILE
  cp -a $TARBALL_DIR/scripts/tidy_image.sh $HOME/ &>>$LOGFILE
fi

##############################################################################
# copy font files to $HOME/gcode/engraving_fonts
echo "copying font files" &>>$LOGFILE
echo "mkdir -p $HOME/gcode/engraving_fonts &>>$LOGFILE" &>>$LOGFILE
mkdir -p $HOME/gcode/engraving_fonts &>>$LOGFILE
echo "removing badly named Bebas font file" &>>$LOGFILE
echo "rm $HOME/gcode/engraving_fonts/BEBAS___.ttf" &>>$LOGFILE
rm $HOME/gcode/engraving_fonts/BEBAS___.ttf &>>$LOGFILE
echo "cp -a $TARBALL_DIR/truetype/* $HOME/gcode/engraving_fonts" &>>$LOGFILE
cp -a $TARBALL_DIR/truetype/* $HOME/gcode/engraving_fonts &>>$LOGFILE
echo "ls -l $HOME/gcode/engraving_fonts" &>>$LOGFILE
ls -l "$HOME/gcode/engraving_fonts" &>>$LOGFILE

##############################################################################
# copy udev rules and reread them
echo "checking for new udev rules..." &>>$LOGFILE
UDEV_UPDATE_NEEDED=0
for RULE_PATH in $(ls ~/tmc/scripts/*.rules); do
    RULE_FILE=$(basename $RULE_PATH)
    cmp -s $RULE_PATH /etc/udev/rules.d/$RULE_FILE
    if [ $? != 0 ]; then
        UDEV_UPDATE_NEEDED=1
        echo "udev update triggered by $RULE_PATH"
    fi
done
if [ $UDEV_UPDATE_NEEDED -eq 0 ]; then
    echo "no new udev rules found, skipping update" &>>$LOGFILE
else
    echo "sudo cp -p ~/tmc/scripts/*.rules /etc/udev/rules.d/" &>>$LOGFILE
    sudo cp -p ~/tmc/scripts/*.rules /etc/udev/rules.d/
    echo "sudo udevadm trigger" &>>$LOGFILE
    sudo udevadm trigger
    echo "sudo udevadm settle" &>>$LOGFILE
    sudo udevadm settle
    echo "ls -l /etc/udev/rules.d" &>>$LOGFILE
    ls -l /etc/udev/rules.d &>>$LOGFILE

    # sigh. the 'sudo udevadm trigger' above whacks something enough that all of the
    # xinput calibration properties for the touchscreen are lost.  this makes it
    # difficult to interact with any dialog boxes.  restore it.
    echo "Restoring touchscreen calibration that may have been lost due to new udev rules" &>>$LOGFILE
    # Give the xsession just a bit more time after the udevadm poke above to settle down
    # so that when we apply calibration, it sticks.
    sleep 1
    $SCRIPT_DIR/xinput_calibrator_pointercal.sh
fi

# make sure the gtk file chooser prefs aren't stuck on for showing hidden files.
echo "Cleaning up any old GTK file chooser preferences." &>>$LOGFILE
echo "rm -f $HOME/.config/gtk-2.0/gtkfilechooser.ini" &>>$LOGFILE
rm -f "$HOME/.config/gtk-2.0/gtkfilechooser.ini" &>>$LOGFILE

# Update desktop background in case it changed
if [ $RUNNING_FROM_TTY -eq 0 ]; then
    echo "Installing updated desktop background."  &>>$LOGFILE
    echo "cp ~/tmc/python/splash/images/Tormach-Wallpaper.png $HOME"  &>>$LOGFILE
    cp ~/tmc/python/splash/images/Tormach-Wallpaper.png $HOME  &>>$LOGFILE
    echo "dconf write /org/mate/desktop/background/picture-filename "'/home/operator/Tormach-Wallpaper.png'""  &>>$LOGFILE
    dconf write /org/mate/desktop/background/picture-filename "'/home/operator/Tormach-Wallpaper.png'"  &>>$LOGFILE
fi

# Update plymouth power up and power down images in case they changed

echo "Checking if plymouth power up and down images need updating."  &>>$LOGFILE
cmp -s ~/tmc/python/images/pathpilot-powerdown.png /lib/plymouth/themes/tormach/pathpilot-powerdown.png
if [ $? != 0 ]; then
  echo "Installing updated plymouth power down image."  &>>$LOGFILE
  echo "sudo cp ~/tmc/python/images/pathpilot-powerdown.png /lib/plymouth/themes/tormach/"  &>>$LOGFILE
  sudo cp ~/tmc/python/images/pathpilot-powerdown.png /lib/plymouth/themes/tormach/
fi
cmp -s ~/tmc/python/images/pathpilot-powerup.png /lib/plymouth/themes/tormach/pathpilot-powerup.png
if [ $? != 0 ]; then
  echo "Installing updated plymouth power up image."  &>>$LOGFILE
  echo "sudo cp ~/tmc/python/images/pathpilot-powerup.png /lib/plymouth/themes/tormach/" &>>$LOGFILE
  sudo cp ~/tmc/python/images/pathpilot-powerup.png /lib/plymouth/themes/tormach/
  echo "Rebuilding initramfs to include new plymouth power up image."  &>>$LOGFILE
  echo "sudo update-initramfs -u"  &>>$LOGFILE
  sudo update-initramfs -u  &>>$LOGFILE
fi

#-----------------------------------------------------------------------
# Expand the /dev/sda3 partition to use all available free space on the drive
# Then grows the existing root ext4 filesystem in place to use all that free space
#
echo "Calling python ~/tmc/scripts/expand_partition_as_needed.py" &>>$LOGFILE
python ~/tmc/scripts/expand_partition_as_needed.py &>>$LOGFILE

#-----------------------------------------------------------------------
# Copy the Fusion 360 probing documentation into a folder in ~/gcode
#
F360PROBE_DOCS=f360_probe
echo "Copying Fusion 360 probing documentation to $HOME/gcode/$F360PROBE_DOCS" &>>$LOGFILE
mkdir -p ~/gcode/$F360PROBE_DOCS &>>$LOGFILE
cp ~/tmc/subroutines/f360_probe/*.cps ~/gcode/$F360PROBE_DOCS &>>$LOGFILE
cp ~/tmc/subroutines/f360_probe/*.pdf ~/gcode/$F360PROBE_DOCS &>>$LOGFILE
cp ~/tmc/subroutines/f360_probe/*.f3d ~/gcode/$F360PROBE_DOCS &>>$LOGFILE
cp ~/tmc/subroutines/f360_probe/README.txt ~/gcode/$F360PROBE_DOCS &>>$LOGFILE

if [ $INSTALLWINDOW_PID -ne 0 ]; then
    # Bring down the install status window
    kill -s SIGTERM $INSTALLWINDOW_PID
fi

TIMESTAMP=`date`
echo "$TIMESTAMP: postinstall script has finished" &>>$LOGFILE

exit 0
