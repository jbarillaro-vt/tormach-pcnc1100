#!/bin/bash
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


# Make a backup first
sudo cp /etc/default/grub /etc/default/grub.backup

# Change args to force menu to display with 10 second timer countdown
sudo sed -e "s/GRUB_TIMEOUT=[0-9]\+/GRUB_TIMEOUT=0/" -e "s/^#GRUB_HIDDEN_TIMEOUT=0$//" -e "s/GRUB_HIDDEN_TIMEOUT_QUIET=true/GRUB_TIMEOUT_STYLE=hidden/" -e "s/GRUB_TIMEOUT_STYLE=\w\+/GRUB_TIMEOUT_STYLE=hidden/" /etc/default/grub > grub.tmp
sudo mv grub.tmp /etc/default/grub

# Update grub
sudo update-grub
