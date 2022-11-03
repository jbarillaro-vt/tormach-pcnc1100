#!/bin/bash -x
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


echo "cleaning filesystem prior to imaging"

cd $HOME

rm -f ~/tmc/eula_agreed.txt
rm -rf ~/.local/share/Trash
rm -rf ~/.mozilla
rm -rf ~/.config/google-chrome
rm -rf ~/.thumbnails
rm -rf ~/.gnupg
rm -f ~/config_file.txt
rm -f ~/pathpilot.json
rm -f ~/preinstall.txt
rm -f ~/postinstall.txt
rm -f ~/gcode/logfiles/*
#This deletes the previous bash history, ASSUMING no other terminal sessions are running.
rm -f ~/.bash_history
#The below clears the present session's bash history, which is a cached copy of bash_history just deleted
#When all sessions exit, they create/append a new .bash_history ... unless it's nulled via this clear
#(or unless history recording has been disabled entirely, which we don't want to do)
history -c
# whack mill_data, lathe_data, maybe others without having to name them explicitly here
# including pluggable auth module state
rm -rf ~/*_data/
rm -f ~/gcode/pointercal.xinput
rm -rf ~/tmc.make_run
rm -f  ~/gcode/Dropbox
rm -f ~/.config/gtk-2.0/gtkfilechooser.ini
rm -f ~/upgrade.log

# delete recently used files
sudo rm -f /home/operator/.local/share/recently-used.xbel

sudo rm -f /etc/NetworkManager/system-connections/*

sudo rm -rf tmc.make_run
rm -rf tmc
DIR_COUNT=`ls -1d v* | wc -l`
echo DIR_COUNT
if [ $DIR_COUNT != 1 ] ; then
  echo 'ERROR!!! ERROR!!! ERROR!!! ERROR!!! ERROR!!! ERROR!!! ERROR!!! '
  echo 'No pathpilot directory or more than one exists with which to link ~/tmc!!!!!'
  exit 1
fi
DIR_NAME=`ls -1d v*`
ln -s $DIR_NAME tmc

ls -lR ~/gcode
ls -lR ~/updates
ls -ld ~/tmc

echo "clean apt cache"
sudo apt-get clean

set +x
echo "checking for things that don't belong on the image"

if [ -d "$HOME/repos" ]; then
  echo $'\nXXXXXXXXXXXXXXXXX WARNING XXXXXXXXXXXXXXXXXXXXXXXX WARNING XXXXXXXXXX'
  echo "There is a git repository on this disk !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
  ls -l ~/repos
fi

if [ -d "$HOME/.ssh" ]; then
  echo $'\nXXXXXXXXXXXXXXXXX WARNING XXXXXXXXXXXXXXXXXXXXXXXX WARNING XXXXXXXXXX'
  echo "Warning: There is .ssh key directory on this disk !!!!!!!!!!!!!!!!!!!"
  echo "ls -l ~/.ssh"
  ls -l ~/.ssh
fi

if [ -e "$HOME/.gitconfig" ]; then
  echo $'\nXXXXXXXXXXXXXXXXX WARNING XXXXXXXXXXXXXXXXXXXXXXXX WARNING XXXXXXXXXX'
  echo "Warning: There is .gitconfig on this disk !!!!!!!!!!!!!!!!!!!!!!!!!!!"
  echo "cat ~/.gitconfig"
  cat ~/.gitconfig
fi

if [ -d "/usr/lib/wingide5" ]; then
  echo $'\nXXXXXXXXXXXXXXXXX WARNING XXXXXXXXXXXXXXXXXXXXXXXX WARNING XXXXXXXXXX'
  echo "Wing IDE is installed on this disk !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
  echo "ls /usr/lib/wingide5"
  ls /usr/lib/wingide5
  echo "ls ~/.wingide5"
  ls ~/.wingide5
fi

# complain if there is a Wing IDE license file present
if [ -e "$HOME/.wingide5/license.act" ]; then
  echo $'\nXXXXXXXXXXXXXXXXX WARNING XXXXXXXXXXXXXXXXXXXXXXXX WARNING XXXXXXXXXX'
  echo "Warning: There is a Wing IDE software license on this disk !!!!!!!!!!"
  echo "ls ~/.wingide5/license.act"
  ls ~/.wingide5/license.act
  echo "cat ~/.wingide5/license.act"
  cat ~/.wingide5/license.act
fi

echo "checking for presense of pathpilot factory backup"
if ! ls /boot/pathpilot-factory-default-img/sda* ; then
  echo $'\nXXXXXXXXXXXXXXXXX WARNING XXXXXXXXXXXXXXXXXXXXXXXX WARNING XXXXXXXXXX'
  echo "Warning: No factory back in /boot/pathpilot-factory-default-img !!!!!"
#else
#  echo "ls -l /boot/pathpilot-factory-default-img"
#  ls -l /boot/pathpilot-factory-default-img
fi

if [ -e "/boot/pathpilot-backup-img/sda*" ]; then
  echo "XXXXXXXXXXXXXXXXX WARNING XXXXXXXXXXXXXXXXXXXXXXXX WARNING XXXXXXXXXX"
  echo "Warning: Disk backup found in /boot/pathpilot-backup-img !!!!!!!!!!!!"
  echo "ls -l /boot/pathpilot-*"
  ls -l /boot/pathpilot-*
fi

if [ ! -d "$HOME/pathpilot.fallback" ]; then
  echo $'\nXXXXXXXXXXXXXXXXX WARNING XXXXXXXXXXXXXXXXXXXXXXXX WARNING XXXXXXXXXX'
  echo "Error: No ~/pathpilot.fallback directory !!!!!"
fi

echo $'\nMake sure ~/updates does not contain unreleased versions'
echo "ls -l $HOME/updates"
ls -l $HOME/updates

PATHPILOT_DESKTOP="$HOME/.config/autostart/pathpilot.desktop"
if [ ! -e $PATHPILOT_DESKTOP ]; then
  echo $'ERROR: no pathpilot.desktop autostart file found in $HOME/.config/autostart'
  exit 1
fi

COUNT=`grep -ic X-MATE-Autostart-enabled=true $PATHPILOT_DESKTOP`

if [ $COUNT != 1 ]; then
  echo $'ERROR: PathPilot is not enabled in Startup Applications!!!!!!!!!!!!!!'
  echo "Go to Menu -> Preferences -> Start Applications and enabled it"
  exit 1
else
  echo $'Good. PathPilot is enabled in startup.'
fi

MATEPANEL_DESKTOP="$HOME/.config/autostart/mate-panel.desktop"
if [ ! -e $MATEPANEL_DESKTOP ]; then
  echo $'ERROR: no mate-panel.desktop autostart file found in $HOME/.config/autostart'
  exit 1
fi

COUNT=`grep -ic X-MATE-Autostart-enabled=true $MATEPANEL_DESKTOP`

if [ $COUNT == 1 ]; then
  echo $'ERROR: Mate Panel is enabled in Startup Applications!!!!!!!!!!!!!!'
  echo "Go to Menu -> Preferences -> Start Applications and disabled it"
  exit 1
else
  echo $'Good. Mate-Panel is disabled in startup.'
fi

# running this script means we are finalizing the image for USB bootable image creation
# so be sure to remove the flag file which stops the /dev/sda3 partition from being
# expanded to fill the drive on graceful shutdown.
rm ~/prevent-partition-expand

# test to see if the expand partition script would do its work
python tmc/scripts/expand_partition_as_needed.py testrun
if [ $? != 0 ]; then
    echo -e "\n\n\n\nSTOP  !!!!\n\nThe partition has already been expanded. You need to start over from a previous OS image\nand follow the wiki page instructions on how to prevent this while creating the USB bootable drive.\n\n"
    exit 1
else
    echo -e "\nGreat, partition is in good shape for creating USB bootable .rdr image\n"
fi


echo ''
echo 'THREE LAST STEPS!'
echo ''
echo '1. Now run Firefox once and get past the stupid dialog asking about importing bookmarks.'
echo '   This helps in case the user clicks on a link in a dropbox installer dialog and it tries'
echo '   to run the system browser and is then confusing.'
echo '   We blew away the entire firefox profile history above so just need to create a clean one now.'
echo ''
echo '2. Run Chrome once and accept it as the system default browser, but do not send stats or'
echo '   crash reports to Google.  Also maximize the chrome window and then shut it down.'
echo ''
echo '3. Manually set display resolution system-wide to 1024 x 768 (probably already is but check).'
echo ''
echo ''
echo 'WARNING and BEWARE: You are creating a new bash history in this terminal session, including'
echo '          your \"exit\" from this session.  Preface all commands with a space to avoid '
echo '          generating a new history in this terminal, or any other terminal sessions you'
echo '          must now open.'


