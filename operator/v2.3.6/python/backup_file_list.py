# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


# list of files to be backed up and subsequently restored

# name of destination backup/restore file
# this will be created in the GCODE_BASE_PATH directory
file_name = 'PathPilotBackupSettings.zip'

# list of files and directories shared by settings-back and settings-restore
# these are located relative to the HOME directory

file_list = ('*_data/*',
             'gcode/pointercal.xinput',
             'smb.conf.netbios-name',
             'smb.conf.share',
             '/etc/timezone'
             )

# all files in these directories
dir_list = ('gcode/subroutines',
            'gcode/thread_data',
            'gcode/engraving_fonts'
            )
