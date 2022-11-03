# do not put a she-bang! here as this script must modify the current environment, not a child shell

# coding=utf-8
# Portions Copyright © 2014-2018 Tormach® Inc. All rights reserved.

# script invoked as ". ./this_script" or "source ./this_script directory"

#echo "Setting enviroment to run Tormach LinuxCNC to run-in-place for development"

# the following is derived from LinuxCNC scripts/rip-environment:
# tcl, wish, and man page related parts removed

# Execute this file in the context of your shell, such as with
#  . /this_script
# and your shell environment will be properly configured to run commands like
# comp, halcmd, halrun, iosh, and python with the emc modules available.

#    Copyright 2006, 2007, 2008, 2009 Jeff Epler <jepler@unpythonic.net>
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

#case "$0" in
#    linuxcnc_rip|*/linuxcnc_rip)
#    cat <<EOF
#This script should be loaded in the context of your shell, by executing
#    . $0
#not executed as a separate command.
#EOF
#    exit 1 ;;
#esac

#if ! test "xyes" = "xyes"; then
#    echo "This script is only useful on run-in-place systems."
#    return
#fi

# run-in-place EMC2_HOME supplied on command line?
if [ -z $1 ]
then
    # no, use the current directory
    EMC2_HOME=`pwd`
#    echo "Using default current directory EMC2_HOME = $EMC2_HOME"
else
    EMC2_HOME="$1"
#    echo "Using command line supplied EMC2_HOME: $EMC2_HOME"

    # realpath -s doesn't grok "~" properly
    if [ "${EMC2_HOME:0:1}" == "~" ]; then
      #echo "$EMC2_HOME started with tilde"
      # replace "~" with $HOME
      EMC2_HOME="$HOME""${EMC2_HOME:1}"
    fi
    if [ -d $EMC2_HOME ]
    then
        # leaving "realpath" out for now - need to check return code for non-existant directory
        #EMC2_HOME=`realpath -s "$EMC2_HOME"`
        # yes, use the suplied directory for EMC2_HOME
#        echo "EMC2_HOME = $EMC2_HOME, absolute path for $1"
        foo="bar"
    else
#        echo "$1 is not a directory, cannot set EMC2_HOME!"
        return
    fi
fi

case "$PATH" in
    $EMC2_HOME/bin:*|*:$EMC2_HOME/bin:*)
#    echo "PATH: "$PATH""
#    echo "This script only needs to be run once per shell session."
    return ;;
esac

export EMC2_HOME
EMC2VERSION="2.6.0~pre"
export EMC2VERSION

# prepend to PATH
PATH="$EMC2_HOME"/python:"$EMC2_HOME"/bin:$EMC2_HOME/scripts:"$EMC2_HOME"/bin:"$PATH"

# append teamviewer to PATH
if [ -d "$HOME/teamviewer9qs" ] ; then
    PATH=$PATH:"$HOME/teamviewer9qs"
fi

# append /sbin and /usr/sbin to PATH
# debian does not include them by default
PATH=$PATH:/sbin:/usr/sbin

if [ -z "$LD_LIBRARY_PATH" ]; then
    LD_LIBRARY_PATH=$EMC2_HOME/lib
else
    LD_LIBRARY_PATH=$EMC2_HOME/lib:"$LD_LIBRARY_PATH"
fi
export LD_LIBRARY_PATH

TORMACH_PYTHON=$EMC2_HOME/python:$EMC2_HOME/python/config_picker:$EMC2_HOME/lib/python:$EMC2_HOME/python/scanner2

if [ -z "$PYTHONPATH" ]; then
    PYTHONPATH=$TORMACH_PYTHON
else
    PYTHONPATH=$TORMACH_PYTHON:"$PYTHONPATH"
fi
export PYTHONPATH

#echo "EMC2_HOME: $EMC2_HOME"
#echo "new PATH: "$PATH
#echo "new LD_LIBRARY_PATH: "$LD_LIBRARY_PATH
#echo "new PYTHONPATH: "$PYTHONPATH

# Set local RTLIB directory
LINUXCNC_RTLIB_DIR=$EMC2_HOME/rtlib
LINUXCNC_BIN_DIR=$EMC2_HOME/bin
export LINUXCNC_RTLIB_DIR
export LINUXCNC_BIN_DIR

#Define NML file location
NML_FILE=$EMC2_HOME/configs/common/linuxcnc.nml
export NML_FILE

# latency-test and friends need this
if [ -z "$TCLLIBPATH" ]; then
    TCLLIBPATH=$EMC2_HOME/tcl
else
    TCLLIBPATH=$EMC2_HOME/tcl:$TCLLIBPATH
fi
export TCLLIBPATH

TMP_DIR=/tmp/linuxcnc
mkdir -p $TMP_DIR
#echo "Temporary directory for linuxcnc: $TMP_DIR"
export TMP_DIR

# must activate virtualenv for python packages
source $EMC2_HOME/venv/bin/activate

#echo "RIP environment setup complete..."
