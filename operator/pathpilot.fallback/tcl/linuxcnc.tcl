#    This is a part of LinuxCNC
#    Copyright 2006-2009 Jeff Epler <jepler@unpythonic.net>
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

namespace eval linuxcnc {
    variable HOME /home/operator/tmc
    variable BIN_DIR /home/operator/tmc/bin
    variable TCL_DIR /home/operator/tmc/tcl
    variable TCL_LIB_DIR /home/operator/tmc/tcl
    variable TCL_BIN_DIR /home/operator/tmc/tcl/bin
    variable TCL_SCRIPT_DIR /home/operator/tmc/tcl/scripts
    variable HELP_DIR /home/operator/tmc
    variable RTLIB_DIR /home/operator/tmc/rtlib
    variable CONFIG_PATH {/home/operator/tmc/configs}
    variable NCFILES_DIR /home/operator/gcode
    variable LANG_DIR /home/operator/tmc
    variable IMAGEDIR /home/operator/tmc
    variable REALTIME /home/operator/tmc/scripts/realtime

    variable SIMULATOR @SIMULATOR@
    variable CONFIG_DIR {}
    foreach _dir  [split {/home/operator/tmc/configs} :] {
	lappend CONFIG_DIR [file normalize $_dir]
    }
    unset _dir
    variable USER_CONFIG_DIR [lindex $CONFIG_DIR 0]
    variable _langinit 1
}

if {[string first $::linuxcnc::BIN_DIR: $env(PATH)] != 0} {
    set env(PATH) $::linuxcnc::BIN_DIR:$env(PATH)
}

proc linuxcnc::image_search i {
    set paths "$linuxcnc::IMAGEDIR $linuxcnc::HOME $linuxcnc::HOME/etc/linuxcnc /etc/linuxcnc ."
    foreach f $paths {
        if [file exists $f/$i] {
            return [image create photo -file $f/$i]
        }
        if [file exists $f/$i.gif] {
            return [image create photo -file $f/$i.gif]
        }
    }
    error "image $i is not available"
}

load [file join [file dirname [info script]] linuxcnc[info sharedlibextension]]

# Arrange to load hal.so when the 'hal' command is requested
proc hal {args} {
    load $::linuxcnc::TCL_LIB_DIR/hal.so
    eval hal $args
}

# Internationalisation (i18n)
# in order to use i18n, all the strings will be called [msgcat::mc "string-foo"]
# instead of "string-foo".
# Thus msgcat searches for a translation of the string, and in case one isn't 
# found, the original string is used.
# In order to properly use locale's the env variable LANG is queried.
# If LANG is defined, then the folder src/po is searched for files
# called *.msg, (e.g. en_US.msg).
package require msgcat
if {$linuxcnc::_langinit && [info exists env(LANG)]} {
    msgcat::mclocale $env(LANG)
    msgcat::mcload $linuxcnc::LANG_DIR
    set linuxcnc::_langinit 0
}

proc linuxcnc::standard_font_size {} {
    if {[info exists ::linuxcnc::standard_font_size]} { return $::linuxcnc::standard_font_size }
    set res1 [catch {exec gconftool -g /desktop/gnome/font_rendering/dpi} gnome_dpi]
    set res2 [catch {exec xlsfonts -fn -adobe-helvetica-medium-r-normal--*-*-*-*-p-*-iso10646-1} fonts]
    if {$res1 == 0 && $res2 == 0} {
        set pixels [expr {$gnome_dpi / 8.}]
        set min_diff [expr .2*$pixels]
        set best_size [expr {int($pixels)}]
        foreach f $fonts {
            regexp -- {-.*?-.*?-.*?-.*?-.*?-.*?-(.*?)-.*} $f _ sz
            set diff [expr {abs($pixels - $sz)}]
            if {$diff < $min_diff} {
                set min_diff $diff
                set best_size $sz
            }
        }
        return -$best_size
        set ::linuxcnc::standard_font_size -$best_size
    } else {
        set ::linuxcnc::standard_font_size 12
    }
}

proc linuxcnc::standard_font_family {} {
    if {[lsearch [font names] TkDefaultFont] != -1} {
	return [font configure TkDefaultFont -family]
    }
    return Helvetica
}

proc linuxcnc::standard_font {} {
    if {[lsearch [font names] TkDefaultFont] != -1} { return TkDefaultFont }
    list [standard_font_family] [standard_font_size]
}

proc linuxcnc::standard_fixed_font_family {} {
    if {[lsearch [font names] TkFixedFont] != -1} {
	return [font configure TkFixedFont -family]
    }
    return Courier
}

proc linuxcnc::standard_fixed_font {} {
    if {[lsearch [font names] TkFixedFont] != -1} { return TkFixedFont }
    set sz [standard_font_size]
    if {$sz < 0 && $sz >= -12 && [lsearch [font families] fixed] != -1} {
        return fixed
    }
    list [standard_fixed_font_family] [standard_font_size]
}
