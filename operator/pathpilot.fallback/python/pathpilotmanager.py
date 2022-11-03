#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------



# This program is a Python replacement for the bulk of ~/operator_login
# It handles checking the machine interface cards both PCI and Ethernet
# and updates their respective .bit file programming.
# It starts PathPilot and installs PathPilot updates.

# for debugging within Wing IDE
try:
    import wingdbstub
except ImportError:
    pass

from locsupport import *
# This is a temp definition of _ to make it visible to pylint without complaint.
# At runtime below it is deleted right away and the _ alias that the gettext module import creates takes over
def _(msgid):
    return msgid

import pygtk
pygtk.require("2.0")
import gtk
import gobject
import glib

import os
import sys
import errno
import linecache
import subprocess
import time
import apt
import glob
from iniparse import SafeConfigParser
import tarfile
import zipfile
import btn
import popupdlg
import traceback
import filecmp
import ui_misc
import shutil
import string
import makeini
import json
import versioning
import vmcheck
import grub
import samba
import memory
import crashdetection
import timer

# these packages are included with PathPilot in case they are needed
# on controllers where the package(s) will be missing from the released
# controller image
deb_packages = [
    # order here is critical as lower .debs may depend are higher .debs
    'blt'
]

HOME_DIR = os.getenv('HOME')
PATHPILOTJSON_FILE = os.path.join(HOME_DIR, 'pathpilot.json')
NOCONFIGPICKER_FILE = os.path.join(HOME_DIR, '.pp_noconfigpicker')
TMC_DIR = os.path.join(HOME_DIR, 'tmc')
DEB_DIR = os.path.join(TMC_DIR, 'debs')
SCRIPTS_DIR = os.path.join(TMC_DIR, 'scripts')
PYTHON_DIR = os.path.join(TMC_DIR, 'python')
RIP_SCRIPT = os.path.join(SCRIPTS_DIR, 'rip-environment.sh')
RTAPI_APP_PROG = os.path.join(TMC_DIR, 'bin/rtapi_app')

PREINSTALL_PATH = 'scripts/preinstall.sh'
POSTINSTALL_PATH = 'scripts/postinstall.sh'
SETTINGS_RESTORE_FILE = os.path.join(HOME_DIR, 'settings_restore_file.txt')

CONTROLLER_INTERFACE = 'eth0'
CONTROLLER_IP = '10.10.10.9'

MESA_IP = '10.10.10.10'


PATHPILOTJSON_FILE_NOT_FOUND = 1
CONFIG_MAKE_INI_FAILURE = 2
PATHPILOTJSON_FILE_CORRUPT = 3

def PrintException():
    exc_type, exc_obj, tb = sys.exc_info()
    f = tb.tb_frame
    lineno = tb.tb_lineno
    filename = f.f_code.co_filename
    linecache.checkcache(filename)
    line = linecache.getline(filename, lineno, f.f_globals)
    print 'EXCEPTION: ({}, line {} "{}"): {} {}'.format(filename, lineno, line.strip(), type(exc_obj).__name__, exc_obj)


class manager():
    def __init__(self):
        self.ini_file = ''
        self.pingproc = None
        self.testing_connectivity = False
        self._splash_proc = None
        self.sim_mode = False


    def run_cmd(self, cmd):
        result = ''
        try:
            result = subprocess.check_output(cmd, shell=True)
            print '%s: %s' % (cmd, result.strip())
        except subprocess.CalledProcessError:
            print 'Failed to run %s' % cmd
        return result


    def start_drop_caches(self):
        # this keeps an eye on kswapd0 from running wild and consuming an entire CPU core
        # this sleeps for 60 seconds between checks
        # it will terminate when this program terminates
        # or we can kill it by self.drop_caches_popen.kill()
        self.drop_caches_popen = subprocess.Popen(
            [os.environ.get('SHELL', '/bin/bash'), os.path.join(SCRIPTS_DIR, 'drop_caches.sh')])


    def check_window_manager(self):
        totalmb = memory.get_total_ram_mb()

        cmdread = 'dconf read /org/mate/marco/general/compositing-manager'
        cmdwrite = 'dconf write /org/mate/marco/general/compositing-manager {}'
        compositing_mgr = subprocess.check_output(cmdread, shell=True).strip()

        # Due to X graphics bugs on Brix we haven't figured out yet we can't risk doing compositing
        # regardless of resources
        if True:  # totalmb < 2000:
            # we don't use a compositing window manager in this case, too resource constrained
            if compositing_mgr == 'true':
                print "Changing to non-compositing window manager due to limited RAM"
                subprocess.check_output(cmdwrite.format('false'), shell=True)  # turn it off
                subprocess.call('nohup marco --no-composite --replace &', shell=True)  # make it take effect without reboot
        else:
            # use a compositing window manager here for better visuals, esp. with tool tips
            if compositing_mgr == 'false':
                print "Changing to compositing window manager since we have enough RAM"
                subprocess.check_output(cmdwrite.format('true'), shell=True)  # turn it on
                subprocess.call('nohup marco --composite --replace &', shell=True)  # make it take effect without reboot


    def start_dropbox(self):
        # start dropbox if ~/dropbox.py is present
        dropbox_py = os.path.join(os.environ['HOME'], 'dropbox.py')
        if os.path.isfile(dropbox_py) and os.access(dropbox_py, os.X_OK):
            print 'starting dropbox via %s start' % dropbox_py
            # dropbox stdout is SUPER noisy and fills our log with useless "tornado" library warnings.
            # use separate stdout and stderr for it to avoid this.
            nullwritablefile = open("/dev/null", "w", 0)
            failed = subprocess.call(['%s start' % dropbox_py], stdout=nullwritablefile, stderr=nullwritablefile, shell=True)
            if failed:
                print 'failed to start Dropbox software.'
            else:
                # And because dropbox occasionally has memory leaks (at least with the verison that was current at the time
                # of testing), start the reaper which periodically restarts dropbox to contain it.
                self.dropbox_reaper_popen = subprocess.Popen(
                    ["/usr/bin/env", "python", os.path.join(SCRIPTS_DIR, 'dropbox_reaper.py')])

        else:
            print '%s not present and executable.' % dropbox_py


    def check_grub(self, vm):
        if vm.is_virtualized_os():
            print "Skipping checking for proper grub configuration due to virtualized OS."
        else:
            print "Checking for proper grub configuration..."
            grub.change_grub_to_vga_terminal()


    def check_samba(self):
        print "Checking for proper samba configuration..."
        samba.change_samba_to_user_security()


    def check_debs(self):
        if len(deb_packages) == 0:
            return

        cache = apt.Cache()
        print 'Checking required additional .deb packages are installed'
        # TODO: this could be wrapped in try/except
        for pkg_name in deb_packages:
            print 'Checking for package %s installed' % pkg_name
            if (not cache.has_key(pkg_name)) or (not cache[pkg_name].is_installed):
                pkg_deb_files = glob.glob(os.path.join(DEB_DIR, pkg_name + '*'))
                if len(pkg_deb_files) == 0:
                    print 'No .deb file found for package: %s' % pkg_name
                    # TODO: this needs to be a popup
                    continue
                elif len(pkg_deb_files) > 1:
                    print 'More than one .deb file found for package: %s' % pkg_name
                    print pkg_deb_files
                    # TODO: this needs to be a popup
                    continue
                deb_filename = pkg_deb_files[0]
                print 'Found .deb file: %s for package %s' % (deb_filename, pkg_name)
                print 'package named: %s not installed. Will now install: %s' % (pkg_name, deb_filename)
                cmd = 'sudo dpkg -i %s' % deb_filename
                result = self.run_cmd(cmd)
            else:
                print 'package: %s already installed.' % pkg_name

        # post package install actions can happen here . . .
        pass


    def set_environment(self, vm):
        print 'Setting environment...'
        # these create or replace environment variables
        environment_new = {
            ('NML_FILE', os.path.join(HOME_DIR, 'tmc/configs/common/linuxcnc.nml')),
            ('LD_LIBRARY_PATH', os.path.join(HOME_DIR, 'tmc/lib')),
            ('TMP_DIR', '/tmp/linuxcnc'),
            ('EMC2VERSION', '2.8.0~pre1'),
            ('LINUXCNC_BIN_DIR', os.path.join(HOME_DIR, 'tmc/bin')),
            ('EMC2_HOME', os.path.join(HOME_DIR, 'tmc')),
            ('LINUXCNC_RTLIB_DIR', os.path.join(HOME_DIR, 'tmc/rtlib')),
            }
        # these get inserted before existing environment variables
        environment_append = {
            ('PATH', os.path.join(HOME_DIR, 'tmc/python') + ':' + os.path.join(HOME_DIR, 'tmc/bin') + ':' + os.path.join(HOME_DIR, 'tmc/scripts')),
            ('PYTHONPATH', os.path.join(HOME_DIR, 'tmc/python') + ':' + os.path.join(HOME_DIR, 'tmc/lib/python') + ':' + os.path.join(HOME_DIR, 'tmc/python/config_chooser'))
            }

        # new variables
        for key, envar in environment_new:
            os.environ[key] = envar
            print key + '=' + os.environ[key]

        # appended variables
        for key, envar in environment_append:
            if key in os.environ:
                os.environ[key] = os.environ[key] + ':' + envar
            else:
                os.environ[key] = envar
            print key + '=' + os.environ[key]
            if key == 'PYTHONPATH':
                # add to sys.path
                print 'appending to Python sys.path'
                for toke in envar.split(':'):
                    print 'appending: %s' % toke
                    sys.path.append(toke)

        if vm.is_virtualized_os():
            self.sim_mode = True

            # force selection of machine type each time, this way we don't rely on the
            # state of the VM leftover from a previous student.
            # You can disable this with "touch ~/.pp_noconfigpicker"
            if os.path.exists(PATHPILOTJSON_FILE) and not os.path.exists(NOCONFIGPICKER_FILE):
                os.unlink(PATHPILOTJSON_FILE)
                print "Removing config file to force selection of machine type in sim mode."
            if 'VirtualBox' in vm.get_vendor():
                print 'VirtualBox detected. Attempting to mount shared folder.'
                # try to mount the VirtualBox shared folder
                # make the mount directory if needed
                uid = self.run_cmd('id -u').strip().split()[-1]
                gid = self.run_cmd('id -g').strip().split()[-1]
                user_name = os.environ['USER']
                mnt_dir = '/media/%s/sf_PathPilotSharedFolder' % user_name
                if not os.path.isdir(mnt_dir):
                    dir_cmd = 'sudo mkdir %s' % mnt_dir
                    print self.run_cmd(dir_cmd)
                    dir_cmd = 'sudo chown %s:%s %s' % (uid, gid, mnt_dir)
                    print self.run_cmd(dir_cmd)
                mnt_cmd = 'sudo mount -t vboxsf -o uid=%s,gid=%s PathPilotSharedFolder %s' % (uid, gid, mnt_dir)
                print self.run_cmd(mnt_cmd)


    def set_monitor_resolution(self, width, height):
        '''
        Returns True if the monitor resolution had to be changed.
        '''
        if os.environ['RUNNING_FROM_TTY'] == '1':
            # don't alter setting if running from terminal
            return

        # GTK is already initialized and knows the monitor resolution. If we end up changing it here,
        # GTK is clueless about the change and is completely broken for things like:
        #
        #     self.window.set_position(gtk.WIN_POS_CENTER)
        #
        # Haven't found a way to "poke" GTK to get it to update so most reliable way
        # to fix this is to understand if we did end up changing resolution
        # and to restart pathpilotmanager.py in that case.

        screen = gtk.gdk.screen_get_default()
        if screen.get_width() != width or screen.get_height() != height:
            print "Changing screen resolution to %dx%d" % (width, height)
            cmd = 'xrandr -s %dx%d' % (width, height)
            exitcode = subprocess.call(cmd, shell=True)
            if exitcode == 0:
                # Successfully changed monitor resolution, need to return to operator_login to restart
                return True

        # Either we don't need to change or trying to change failed so just march ahead
        return False


    def set_monitor_power_saving(self, on_off):
        if os.environ['RUNNING_FROM_TTY'] == '1':
            # don't alter setting if running from terminal
            return

        if on_off:
            cmd = 'xset +dpms'
        else:
            cmd = 'xset -dpms'
        self.run_cmd(cmd)


    def set_screensaver_enabled(self, on_off):
        if os.environ['RUNNING_FROM_TTY'] == '1':
            # don't alter setting if running from terminal
            return

        if on_off:
            cmd = 'xset s on'
        else:
            cmd = 'xset s off'
        self.run_cmd(cmd)


    def check_rtapi_app_permissions(self):
        try:
            s_stat = os.stat(RTAPI_APP_PROG)
            print '%s owner: %d, group: %d, mode" %o' % (RTAPI_APP_PROG, s_stat.st_uid, s_stat.st_gid, s_stat.st_mode)
            if s_stat.st_mode != 0100755 or s_stat.st_uid != 0 or s_stat.st_gid != 0:
                # set to setuid owner root
                cmd = 'sudo chown root:root %s' % (RTAPI_APP_PROG)
                self.run_cmd(cmd)
                cmd = 'sudo chmod 4755 %s' % (RTAPI_APP_PROG)
                self.run_cmd(cmd)
                s_stat = os.stat(RTAPI_APP_PROG)
                print '%s owner: %d, group: %d mode" %o' % (RTAPI_APP_PROG, s_stat.st_uid, s_stat.st_gid, s_stat.st_mode)
        except:
            print 'Failed to stat rtapi_app: %s' % RTAPI_APP_PROG


    def read_pathpilotjson_file(self):
        result = 0     # assume success

        # read contents of pathpilot.json file for info on how to generate linuxcnc ini to use
        try:
            jsonfile = open(PATHPILOTJSON_FILE, 'r')
        except IOError:
            # file not present or unreadable
            result = PATHPILOTJSON_FILE_NOT_FOUND

        if result == 0:
            try:
                force_regen = False
                config = json.load(jsonfile)
                if config["fileversion"] == 2:
                    self.machine_class = config["machine"]["class"]
                    self.rapidturn_mode = config["machine"]["rapidturn"]

                    self.launch_test = ('launch_test' in config["pathpilot"] and config["pathpilot"]["launch_test"])

                    # ethernet or db25parallel   (aka mesa card)
                    self.communication_method = config["machine"]["communication_method"]

                    # sim mode may already be set before we get here so this
                    if os.getenv('PATHPILOT_SIM_MODE') == '1':
                        self.sim_mode = True
                    else:
                        # no previous existing override so let's use what is in the config file
                        self.sim_mode = config["machine"]["sim"]

                    # linuxcnc ini file path almost certainly starts with ~/
                    # fixup paths for both regular and rapidturn flavors if applicable

                    # NOTE! For internal dev purposes, not every linuxcnc ini file is generated from a specific + base version
                    # the generate_from values below may be empty strings instead of file paths

                    if config["machine"]["rapidturn"] is True:
                        if config["machine"]["rapidturn_generate_from"] is None:
                            config["machine"]["rapidturn_generate_from"] = ""
                        config["machine"]["rapidturn_generate_from"] = os.path.expanduser(config["machine"]["rapidturn_generate_from"])
                        config["machine"]["rapidturn_linuxcnc_filepath"] = os.path.expanduser(config["machine"]["rapidturn_linuxcnc_filepath"])
                        self.ini_file = config["machine"]["rapidturn_linuxcnc_filepath"]
                        ini_file_genfrom = config["machine"]["rapidturn_generate_from"]
                    else:
                        if config["machine"]["generate_from"] is None:
                            config["machine"]["generate_from"] = ""
                        config["machine"]["generate_from"] = os.path.expanduser(config["machine"]["generate_from"])
                        config["machine"]["linuxcnc_filepath"] = os.path.expanduser(config["machine"]["linuxcnc_filepath"])
                        self.ini_file = config["machine"]["linuxcnc_filepath"]
                        ini_file_genfrom = config["machine"]["generate_from"]

                    if os.path.isfile(self.ini_file) and os.path.isfile(ini_file_genfrom):
                        # we must be using a generated ini file because we have a source file that exists
                        # the source file could have any number of dependent subfiles due to the new pp_include
                        # structure so don't bother trying to check modified times on all of these things.
                        # just regen the file every time.
                        force_regen = True
                        print "Regenerating %s because its dependent source files may have changed." % self.ini_file
                else:
                    print "Unexpected %s file version %d, forcing a fresh config choice" % (PATHPILOTJSON_FILE, config["fileversion"])
                    result = PATHPILOTJSON_FILE_CORRUPT
            except:
                ex = sys.exc_info()
                traceback_txt = "".join(traceback.format_exception(*ex))
                print 'pathpilotmanager exception: {}'.format(traceback_txt)
                print "Corrupted %s file (syntax broken - missing quotes or commas? missing or mis-spelled keys?)" % PATHPILOTJSON_FILE
                result = PATHPILOTJSON_FILE_CORRUPT
            finally:
                jsonfile.close()

            if result == 0:
                if not os.path.isfile(self.ini_file) or force_regen:
                    print 'Generating linuxcnc ini file: %s' % self.ini_file
                    # try to generate it
                    mki = makeini.IniFactory()
                    result = mki.make_ini_file(config)    # returns 0 for success
                    if result != 0:
                        print 'Failed to generate linuxcnc ini file: %s' % self.ini_file
                        result = CONFIG_MAKE_INI_FAILURE

        return result


    def strip_quote_pair(self, s):
        if (s[0] == s[-1]) and s.startswith(("'", '"')):
            return s[1:-1]
        return s


    def touch(self, fname):
        open(fname, 'a').close()


    def get_interface_present(self, iface):
        # returns True if link exists
        #
        # if no eth0 present throws exception: subprocess.CalledProcessError
        try:
            cmd = 'ip addr show %s' % (iface)
            result = subprocess.check_output(cmd, shell=True)
            print '%s: %s' % (cmd, result)
        except subprocess.CalledProcessError:
            print 'Failed to find network interface %s' % iface
            return False
        return True


    def get_link_status(self, iface):
        try:
            cmd = 'ip addr show %s | grep -w %s:' % (iface, iface)
            result = subprocess.check_output(cmd, shell=True)
            print '%s: %s' % (cmd, result)
            words = result.split()
            for x in range(0, len(words)):
                if words[x] == 'state':
                    if words[x + 1] == 'UP':
                        return True
                    else:
                        return False
            print 'state UP|DOWN not found in %s status' % iface
            return False

        except subprocess.CalledProcessError:
            print 'Failed to get link status for interface %s' % iface
            return False
        return True


    def try_ping_ip(self, ip_addr, blockseconds = 0.0):
        '''
        "Give me a ping, Vasili. One ping only, please.", IP address not name
        Returns True on success, False on failure, or None if answer isn't known yet (child proc is still working on it)
        This is setup this way because ping has a minimum timeout of 1 second and in the failure situation,
        blocking the entire UI in a tight ping loop all the time destroys the user ability to click
        buttons interactively.  So we always do the ping in a child process that we don't wait for and
        we check to see if it is completed frequently and kick off another as needed.
        '''
        answer = None

        if self.pingproc is None:
            nullwritablefile = open("/dev/null", "w", 0)
            nullreadablefile = open("/dev/null", "r", 0)
            self.pingproc = subprocess.Popen(["/bin/ping",
                                              "-W1",
                                              "-c1",
                                              "-n",
                                              ip_addr], stdin=nullreadablefile, stdout=nullwritablefile, stderr=nullwritablefile)

        if blockseconds != 0.0:
            # caller is willing to block a bit for completion
            time.sleep(blockseconds)

        if self.pingproc.poll() != None:
            # we have a definitive answer
            answer = (self.pingproc.returncode == 0)
            self.pingproc = None   # on next method call we will kick off another ping

        return answer


    def get_ip_address_and_mask(self, iface):
        # if no eth0 present prints: Device "eth0" does not exist. to stderr
        # And throws exception: subprocess.CalledProcessError
        try:
            cmd = 'ip addr show %s | grep -w inet' % (iface)
            result = subprocess.check_output('ip addr show %s | grep -w inet' % (iface), shell=True)
            print 'ip addr show %s | grep -w inet: %s' % (iface, result)
        except subprocess.CalledProcessError:
            print 'Failed to get IP address for interface %s' % iface
            return '', ''

        # result should look like: inet 10.10.10.9/8 brd 10.255.255.255 scope global eth0
        if result:
            strs = result.split()
            if strs[0] == 'inet':
                ip, mask_bits = strs[1].split('/')
        return ip, mask_bits


    def get_ip_address(self, iface):
        ip, mask_bits = self.get_ip_address_and_mask(iface)
        return ip


    def set_ip_address(self, iface, ip, mask_bits = '8'):
        # Should only call this after confirming the interface is up & present,
        # as we don't handle those cases here. No harm if called anyway
        # but error messages may be less accurate
        #
        # delete any IP addresses on interface, if there is one
        # then set IP address to what PP wants

        try:  #see if there is a current IP address
            cmd = 'ip addr show %s | grep -w inet' % iface
            result = subprocess.check_output(cmd, shell=True)
            print '%s: %s' % (cmd, result)
        except subprocess.CalledProcessError:
            print 'Failed to get IP address for interface %s, continuing' % iface
            result = '' #result will now exist for "if result check below"

        if result != '' : # delete IP address if one exists
            strs = result.split()
            try:
                if strs[0] == 'inet':
                    cmd = 'sudo ip addr del %s dev %s' % (strs[1], iface)
                    result = subprocess.check_output(cmd, shell=True)
                    print '%s: %s' % (cmd, result)
            except subprocess.CalledProcessError:
                print 'Failed to del IP %s address for interface %s' % (strs[1],iface)

        # add requested IP address
        try:
            cmd = 'sudo ip addr add %s/%s dev %s' % (ip, mask_bits, iface)
            result = subprocess.check_output(cmd, shell=True)
            print '%s: %s' % (cmd, result)
        except subprocess.CalledProcessError:
            print 'Failed to add IP address for interface %s' % iface

        return

    def check_for_pathpilot_update(self):
        # check for presence of UPDATE_PTR_FILE
        if os.path.exists(const.UPDATE_PTR_FILE):
            self.kill_splash()

            # all of the below can take awhile, esp. on slower controllers so put up a warm fuzzy 'we're working on it'
            # message or its easy to think things are locked up...
            statusdlg = popupdlg.status_popup(None, 'Installing PathPilot software update...')
            statusdlg.show_all()
            statusdlg.present()  # make sure it is top of z-order stack so user can see it since there's no parent window
            ui_misc.force_window_painting()

            try:
                print 'Update ptr file exists: %s' % const.UPDATE_PTR_FILE
                # get file contents
                tgp_filename = ''
                try:
                    with open(const.UPDATE_PTR_FILE, 'r') as ufile:
                        # removes leading and trailing white space but CRITICALLY leaves any embedded white space alone
                        # some customers had browsers that renamed the file to v2.2.4 (2).tgp for example.
                        tgp_filename = ufile.readline().strip()
                except Exception as e:
                    msg = 'An exception of type {0} occured, errno and description: {1!r}'
                    print msg.format(type(e).__name__, e.args)
                    with popupdlg.ok_cancel_popup(None, 'Error reading file: %s' % const.UPDATE_PTR_FILE, cancel=False, checkbox=False) as dialog:
                        pass
                    return 2

                print '.tgp filename: %s' % tgp_filename

                # delete UPDATE_PTR_FILE
                os.unlink(const.UPDATE_PTR_FILE)
                # verify .tgp file exists
                if not os.path.exists(tgp_filename):
                    msg = 'Update .tgp file not found: %s' % tgp_filename
                    print msg
                    with popupdlg.ok_cancel_popup(None, msg, cancel=False, checkbox=False) as dialog:
                        pass
                    return 2

                # make .tgz filename
                tgz_filename = os.path.splitext(tgp_filename)[0] + '.tgz'
                print '.tgz filename: %s' % tgz_filename
                # decrypt file
                # gpg --yes --no-use-agent --decrypt --passphrase=moravianvalley --output="$TGZ_UPDATE_FILE_PATH" "$LCNC_UPDATE_FILE_PATH"
                gpg_command = ['gpg', '--yes', '--no-use-agent', '--decrypt',
                               '--passphrase=moravianvalley',
                               '--output=%s' % tgz_filename,
                               tgp_filename]
                p = subprocess.Popen(gpg_command, stdout=subprocess.PIPE)
                exit_code = p.wait()

                if exit_code == 0:
                    # decrypt successful
                    # test that file exists and decrypted file is valid tar.gz file
                    if os.path.exists(tgz_filename):
                        # exists
                        if tarfile.is_tarfile(tgz_filename):
                            print '%s is a valid tar archive file.' % tgz_filename

                            # ask the version mgr what version *we* are so we can accurately tell what
                            # directory we're running from (even if its through the tmc symlink).
                            vermgr = versioning.GetVersionMgr()

                            # untar
                            try:
                                # gzipped or not does not matter, the module figures it out
                                tar = tarfile.open(tgz_filename)
                                # get version folder name from archive
                                update_dir = tar.next().name
                                # version folder name should look something like this: './v1.9.7'
                                print 'First entry in archive should be a directory name: %s' % update_dir
                                if not update_dir.startswith('./'):
                                    msg = 'Update archive path does not start with ./: %s' & update_dir
                                    print msg
                                    with popupdlg.ok_cancel_popup(None, msg, cancel=False, checkbox=False) as dialog:
                                        pass
                                    tar.close()
                                    # delete the .tgz file
                                    os.unlink(tgz_filename)
                                    return 2

                                # remove leading ./
                                update_dir = update_dir[2:]
                                print 'update_dir: %s' % update_dir

                                # potentially pre-existing ~/v1.x.y/bin/rtapi_app is setuid root so make it writable by any user
                                update_rtapi_app_path = os.path.join(update_dir, 'bin/rtapi_app')
                                if os.path.exists(update_rtapi_app_path):
                                    s_stat = os.stat(update_rtapi_app_path)
                                    print '%s owner: %d, group: %d, mode" %o' % (update_rtapi_app_path, s_stat.st_uid, s_stat.st_gid, s_stat.st_mode)
                                    if s_stat.st_mode != 0666:
                                        # make it r/w by all
                                        cmd = 'sudo chmod 666 %s' % (update_rtapi_app_path)
                                        result = self.run_cmd(cmd)
                                        print result
                                        s_stat = os.stat(update_rtapi_app_path)
                                        print '%s owner: %d, group: %d mode" %o' % (update_rtapi_app_path, s_stat.st_uid, s_stat.st_gid, s_stat.st_mode)

                                # update_dir will be something like v2.0.0
                                running_version = vermgr.get_display_version()
                                print 'running_version: %s' % running_version
                                if update_dir == running_version:
                                    # we're trying to unpack a tarball on top of the running version, seems dicey at best - block it.
                                    msg = 'Update file contains same version that is installed: %s' % running_version
                                    print msg
                                    with popupdlg.ok_cancel_popup(None, msg, cancel=False, checkbox=False) as dialog:
                                        pass
                                    tar.close()
                                    # delete the .tgz file
                                    os.unlink(tgz_filename)
                                    return 2

                                # if the new update directory exists already, blow it away to force a clean extraction.
                                # this avoids any possibility that there are orphan files in the directory that the tarball no longer contains.
                                if os.path.isdir(update_dir):
                                    print "Removing existing update directory %s to eliminate any orphan file possibility." % update_dir
                                    shutil.rmtree(update_dir, ignore_errors=True)

                                tar.extractall()
                                tar.close()
                                # delete the .tgz file
                                os.unlink(tgz_filename)

                            except Exception:
                                print(traceback.format_exc())
                                msg = 'Failed to extract .tgz contents.: %s' % tgz_filename
                                with popupdlg.ok_cancel_popup(None, msg, cancel=False, checkbox=False) as dialog:
                                    pass
                                tar.close()
                                # delete the .tgz file
                                os.unlink(tgz_filename)
                                return 2

                            # verify update directory exists from successful archive extraction
                            if not os.path.exists(update_dir):
                                msg = 'Update path does not exist after extracting files: %s' & update_dir
                                print msg
                                with popupdlg.ok_cancel_popup(None, msg, cancel=False, checkbox=False) as dialog:
                                    pass
                                return 2

                            # read the version that we just unpacked - it might be incompatible with us and
                            # could be old enough that it doesn't have any preinstall.sh version protection logic
                            # so we have to do that here.
                            currentverlist = vermgr.get_version_list()
                            updateverlist = vermgr.parse_legacy_version_file(update_dir)
                            print "Current version: ", currentverlist
                            print "Version user selected to update to: ", updateverlist
                            if updateverlist[0] < currentverlist[0]:
                                # they are trying to revert to an older major version
                                # stop this install
                                print "Blocking install of older major version."
                                with popupdlg.ok_cancel_popup(None,
                                                              "Incompatible software update - installation stopped.\n\nTo go back from PathPilot v%d.%d.%d to v%d.%d.%d requires PathPilot Restore DVD (PN 35246), available from tormach.com.\n\nAs an alternative, you may download the latest v%d.x.x from tormach.com/updates." %
                                                              (currentverlist[0], currentverlist[1], currentverlist[2],
                                                              updateverlist[0], updateverlist[1], updateverlist[2],
                                                              currentverlist[0]),
                                                              cancel=False, checkbox=False) as dialog:
                                    pass
                                # Force necessary window repainting to make sure message dialog is fully removed from screen
                                ui_misc.force_window_painting()

                                # clean up the incompatible older version we just unpacked since we aren't using it.
                                try:
                                    shutil.rmtree(update_dir, ignore_errors=True)
                                except:
                                    pass

                                return 2    # restart the current version of PP

                            # run the new preinstall.sh
                            preinstall_path = os.path.join(update_dir, PREINSTALL_PATH)
                            print 'preinstall script: %s' % preinstall_path
                            pre_command = [preinstall_path]
                            p = subprocess.Popen(pre_command, stdout=subprocess.PIPE, shell=True)
                            exit_code = p.wait()

                            # preinstall may have displayed some UI, make sure our status dialog is
                            # looking good again...
                            ui_misc.force_window_painting()

                            # move the symlink to the new version (but only if the exit_code is 0!)
                            if exit_code == 0:
                                try:
                                    try:
                                        os.symlink(update_dir, TMC_DIR)
                                        print 'created new symlink %s -> %s' % (TMC_DIR, update_dir)
                                    except OSError, e:
                                        if e.errno == errno.EEXIST:
                                            # if ~/tmc is a real directory delete it
                                            if os.path.islink(TMC_DIR):
                                                os.unlink(TMC_DIR)
                                            elif os.path.isdir(TMC_DIR):
                                                # shutil.rmtree will crash on symbolic links
                                                shutil.rmtree(TMC_DIR)
                                            os.symlink(update_dir, TMC_DIR)
                                            print 'moved existing symlink %s -> %s' % (TMC_DIR, update_dir)
                                        else:
                                            raise e
                                except Exception:
                                    msg = traceback.format_exc()
                                    print(traceback.format_exc())
                                    msg = 'Exception updating ~/tmc symlink during installation of update: %s' % tgp_filename
                                    with popupdlg.ok_cancel_popup(None, msg, cancel=False, checkbox=False) as dialog:
                                        pass
                                    return 2   # fail the update and restart the existing version of PP
                                # at this point the update is now pointed to by the symlink at ~/tmc
                                # run the new postinstall.sh
                                postinstall_path = os.path.join(TMC_DIR, POSTINSTALL_PATH)
                                print 'postinstall path: %s' % postinstall_path
                                post_command = [postinstall_path]
                                p = subprocess.Popen(post_command, stdout=subprocess.PIPE, shell=True)
                                exit_code = p.wait()
                                return 1
                            else:
                                # preinstall script failed and signaled to abort the software update
                                # if the user needed to be informed, preinstall.sh already did that UI.
                                print 'preinstall.sh returned exit code %d - aborting softare update to %s.' % (exit_code, tgz_filename)
                                return 2     # fail the update and restart the existing version of PP
                        else:
                            print '%s is not a valid tar archive.' % tgz_filename
                            with popupdlg.ok_cancel_popup(None, 'Update file is not a tar archive: %s' % tgz_filename, cancel=False, checkbox=False) as dialog:
                                pass
                            return 0
                else:
                    # decrypt failed, stop and keep currently installed version
                    print 'gpg exit code: %d' % exit_code
                    print 'Decrypt of tgp file failed'
                    with popupdlg.ok_cancel_popup(None, 'Update file is corrupt.  PathPilot update aborted and version not changed.', cancel=False, checkbox=False) as dialog:
                        pass

            finally:
                statusdlg.destroy()

                # Force necessary window repainting to make sure message dialog is fully removed from screen
                ui_misc.force_window_painting()

        # do update file not found, nothing to do
        return 0


    def get_data_dir_candidates(self):
        finallist = []
        pattern = os.path.join(HOME_DIR, '*_data')
        candidates = glob.glob(pattern)
        for cc in candidates:
            if os.path.isdir(cc):
                finallist.append(cc)
        return finallist


    def check_for_settings_restore(self):
        if os.path.exists(SETTINGS_RESTORE_FILE):
            print 'Found settings restore file: %s\n' % SETTINGS_RESTORE_FILE
            # get file contents
            try:
                with open(SETTINGS_RESTORE_FILE, 'r') as ufile:
                    # only want the first line with no leading or trailing whitespace
                    settings_restore_filename = ufile.readline().strip()
            except Exception as e:
                msg = 'An exception of type {0} occured, errno and description: {1!r}'
                print msg.format(type(e).__name__, e.args)
                self.kill_splash()
                with popupdlg.ok_cancel_popup(None, 'Error reading file: %s' % SETTINGS_RESTORE_FILE, cancel=False, checkbox=False) as dialog:
                    pass
                return

            print "settings restore filename: '%s'" % settings_restore_filename

            # delete SETTINGS_RESTORE_FILE
            os.unlink(SETTINGS_RESTORE_FILE)

            # see if file exists
            if os.path.exists(settings_restore_filename):
                pass
            else:
                self.kill_splash()
                with popupdlg.ok_cancel_popup(None, 'Settings restore file not found: %s' % settings_restore_filename, cancel=False, checkbox=False) as dialog:
                    pass
                return

            # see if it is a .zip file
            if not zipfile.is_zipfile(settings_restore_filename):
                self.kill_splash()
                with popupdlg.ok_cancel_popup(None, 'Settings restore file is not a valid .zip file: %s' % settings_restore_filename, cancel=False, checkbox=False) as dialog:
                    pass
                return

            # unzip it
            try:
                zip = zipfile.ZipFile(settings_restore_filename)

                # before we extract anything which overwrites the working files, run a test to make sure the zip isn't corrupt.
                # otherwise we can end up with a half-extracted zip file before realizing it which is a bad place to be in.
                validfile = False
                try:
                    validfile = (zip.testzip() == None)
                except Exception as e:
                    validfile = False
                    msg = 'Bad restore zip file: an exception of type {0} occured, errno and description: {1!r}'
                    print msg.format(type(e).__name__, e.args)

                if not validfile:
                    path, name = os.path.split(settings_restore_filename)
                    msg = 'Settings retore file {} is corrupt.  Copy the file using a different USB drive and try again.'.format(name)
                    self.kill_splash()
                    with popupdlg.ok_cancel_popup(None, msg, cancel=False, checkbox=False) as dialog:
                        pass
                    print "Giving up on settings restore, no files have been changed."
                    return

                # redis special handling
                # for machine class that is in the zip, it should have a dump.rdb file for sure.
                # it may or may not have an appendonly.aof file (the newer log structured redis persistance file).
                # we have to use whatever redis files are in the zip regardless of mtimes.  They are restoring the settings
                # from the zip so we just use them.
                # but if the zip is 'old' and only has a dump.rdb, it will be ignored by the redis-server in favor of appendonly.aof.
                #
                # the easiest way to handle this is to delete both dump.rdb and appendonly.aof files BEFORE we extract
                # the zip.  then it handles these 3 cases easily:
                #  - zip only has an .rdb file -> a new .aof will get built using the .rdb data
                #  - zip has both an .rdb and .aof -> mtimes between those two restored files will be used to decide which
                #    file should be the truth source
                #  - zip only has an .aof file -> a new .rdb will get built

                namelist = zip.namelist()

                datadirs = self.get_data_dir_candidates()
                for dir in datadirs:
                   if os.path.isfile(os.path.join(dir, 'dump.rdb')) or os.path.isfile(os.path.join(dir, 'appendonly.aof')):
                        # confirmed this dir must be a LCNC machine class data directory.
                        name = os.path.basename(dir)
                        rdbtarget = os.path.join(name, 'dump.rdb')
                        aoftarget = os.path.join(name, 'appendonly.aof')
                        if rdbtarget in namelist or aoftarget in namelist:
                            # ok to delete both since the zip extraction will push us into 1 of the 3 situations explained above.
                            try:
                                target = os.path.join(dir, 'dump.rdb')
                                print "Removing {:s} because settings zip has needed data.".format(target)
                                os.remove(target)
                            except:
                                pass
                            try:
                                target = os.path.join(dir, 'appendonly.aof')
                                print "Removing {:s} because settings zip has needed data.".format(target)
                                os.remove(target)
                            except:
                                pass

                zip.extractall()

                # printing it this way makes it a LOT easier to read...
                for f in zip.namelist():
                    print "\t%s" % f
                zip.close()
            except Exception as e:
                msg = 'An exception of type {0} occured, errno and description: {1!r}'
                print msg.format(type(e).__name__, e.args)
                msg = 'Failed to extract settings restore file contents.: %s' % settings_restore_filename
                self.kill_splash()
                with popupdlg.ok_cancel_popup(None, msg, cancel=False, checkbox=False) as dialog:
                    pass
                return

            # if the etc/timezone file exists in the backup settings, then apply it and run time-admin
            # (but only if it is *different* than the current one)
            if os.path.exists("etc/timezone"):
                diff_cmd = ['diff', 'etc/timezone', '/etc/timezone']
                p = subprocess.Popen(diff_cmd, stdout=subprocess.PIPE)
                exit_code = p.wait()
                if exit_code != 0:
                    print "Timezone file from the settings zip is different than /etc/timezone so installing it."
                    # The timezone file we just unpacked is different so let's install it.
                    cmd = 'sudo mv etc/timezone /etc/timezone;rmdir etc'
                    self.run_cmd(cmd)
                    # now run time-admin so it reads the timezone (which may have just changed)
                    # and applies it to the local clock and makes user more aware of what might have just
                    # happened.
                    cmd = 'sudo time-admin'
                    self.run_cmd(cmd)
                else:
                    print "Timezone file from the settings zip is identical to /etc/timezone so nothing to do."

            # delete the settings zip file as it sits in the home dir and just clutters it up now
            os.remove(settings_restore_filename)

            # Give the user a nice warm fuzzy that everything worked as expected.
            msg = "Settings successfully restored."
            print msg    # one for the log
            self.kill_splash()
            with popupdlg.ok_cancel_popup(None, msg, cancel=False, checkbox=False) as dialog:
                pass

            # Force necessary window repainting to make sure message dialog is fully removed from screen
            ui_misc.force_window_painting()


    def run_config_chooser(self, comm_methods):
        cmdline = os.path.join(PYTHON_DIR, "config_chooser/config_chooser.py")
        if self.sim_mode:
            cmdline += " --sim"

        cmdline += " " + comm_methods

        print "Running %s" % cmdline
        return subprocess.call(cmdline, shell=True)


    def check_eula_acceptance(self):
        ''' Returns True if EULA accepted.  False otherwise. '''

        # The eula.py app looks for a marker file for THIS specific verison of software
        # and if it exists, just returns success with no UI shown.  If the EULA has not
        # been accepted yet, it displays the EULA dialog.  If customer accepts, it creates
        # the marker file.  Exit code of 0 is success.  Anything else means non-acceptance
        # or errors.

        cmdline = os.path.join(PYTHON_DIR, "eula/eula.py") + " " + TMC_DIR
        exitcode = subprocess.call(cmdline, shell=True)
        if exitcode == 0:
            return True
        return False


    def on_ping_timer_expire(self, dialog):
        if self.testing_connectivity:
            dialog.pulse()   # indicate testing connectivity to the user
            if self.try_ping_ip(self.ip_address) is True:
                # success!
                dialog.response = progress_popup.RESPONSE_PINGSUCCESS
                gtk.main_quit()
                return False  # stop further timer callbacks
            return True   # continue timer
        else:
            return False   # stop further timer callbacks


    def display_splash(self):
        splashfullpath = os.path.join(PYTHON_DIR, "splash", "tormach_splash.py")
        self._splash_proc = subprocess.Popen([splashfullpath, "2"])   # argument is how many seconds per image


    def kill_splash(self):
        # kill the splash screen
        if self._splash_proc:
            self._splash_proc.kill()
            self._splash_proc = None


    def calibrate_touchscreen(self):
        # do we have a supported touchscreen?
        rc = subprocess.call('detect_touchscreen.py', shell=True)
        if rc == 0:
            print "Supported touchscreen detected."
            if not os.path.isfile(const.TOUCHSCREEN_CALIBRATION_FILE):
                dlg = popupdlg.ok_cancel_popup(None, 'Touchscreen detected that has not been calibrated.\n\nPress OK to run the calibration utility.', cancel=True, checkbox=False)
                dlg.run()
                dlg.destroy()
                if dlg.response == gtk.RESPONSE_OK:
                    # automatically run calibration to give them a better experience
                    subprocess.call('touchscreen_calibrate.sh', shell=True)

        # regardless of whether a touchscreen is known and tested by us or not, if there is a valid calibration file,
        # apply it.
        if os.path.isfile(const.TOUCHSCREEN_CALIBRATION_FILE):
            print 'Reinstating touchscreen calibration.'
            subprocess.call('xinput_calibrator_pointercal.sh', shell=True)


    def disable_ethernet_irq_coalescing(self):
        print 'Disabling ethernet rx irq coalescing'
        # when rx-usecs is set to 0, rx-frames is used to decide how many frames should be received before generating an interrupt
        cmd = 'sudo ethtool --coalesce eth0 rx-usecs 0 rx-frames 1'
        self.run_cmd(cmd)
        cmd = 'sudo ethtool --show-coalesce eth0'
        self.run_cmd(cmd)


    def log_ethtool_settings(self):
        ethtool_cmd = ['sudo', '/sbin/ethtool', CONTROLLER_INTERFACE]
        p = subprocess.Popen(ethtool_cmd)
        ethtool_retval = p.wait()


    def disable_ethernet_autonegotiation(self):
        #--------------------------------------------------------------------------------------------
        # eth0 is configured and we can ping the ethernet FPGA.  Now that it is stable, turn off
        # auto negotiation for speed and duplex because for some ethernet chipsets and drivers, it causes bugs where it
        # kicks in and drops link over a day or two.

        # first log what we started with before changing anything so we can tell what autonegotiation is doing.
        print "BEFORE disabling autonegotiation for %s:" % CONTROLLER_INTERFACE
        self.log_ethtool_settings()

        # now turn autoneg off
        ethtool_cmd = ['sudo', '/sbin/ethtool', '-s', CONTROLLER_INTERFACE, 'autoneg', 'off']
        p = subprocess.Popen(ethtool_cmd)
        ethtool_retval = p.wait()
        print "ethtool returned %d when turning autoneg off" % ethtool_retval
        if ethtool_retval != 0:
            print "ethtool FAILED turning off autonegotation for %s" % CONTROLLER_INTERFACE

        # let eth0 settle a little before trying to use it right away.
        # otherwise if you try to log an ethtool settings again right away it can't tell what speed and duplex it is using.
        # and the ping test dialog will pop up a little each time which looks a bit alarming.
        time.sleep(2.5)


    def check_for_problematic_wifi_card(self):
        # see if the problematic Realtek pci wifi card with huge bus latencies is installed.
        lspci_output = subprocess.check_output(['/usr/bin/lspci', '-n', '-d', '10ec:b723'])
        if '10ec:b723' in lspci_output:
            msg = 'Realtek RTL8723 based PCI wireless network adapter detected.\n\nThis type of adapter is known to cause issues running PathPilot due to its interaction with the PCI bus.  It should be removed from the controller before running any programs.  Switch to a USB based network adapter (either wifi or ethernet) instead.'
            print msg
            with popupdlg.ok_cancel_popup(None, msg, cancel=False, checkbox=False) as dialog:
                pass


    def upgrade_redis_persistence_format(self):
        cmdline = "{:s} {:s}".format(os.path.join(PYTHON_DIR, 'redis-upgrade.py'), self.ini_file)
        print cmdline
        returncode = subprocess.call(cmdline, shell=True)
        print "redis-upgrade.py returned", returncode


    def handle_possible_build_expiration(self):
        '''
        Returns True if the code should continue running (build NOT expired),
                False if the build is expired and we should exit.
        '''
        if self.launch_test:
            return True   # ok to run PP

        # if this build has or will expire, warn them and give them an explicit opportunity
        # to update the build as a reminder.
        warning_msg = versioning.GetVersionMgr().get_expiration_warning()
        if warning_msg != None:
            self.kill_splash()

            # build has an expiration date at some point.
            # warn the user of this date

            # This is a do-nothing, zero sized window, but it is top level and can serve as the parent
            # window of the MessageDialog below.  This is required so that the window manager "sees" it
            # when using Alt-Tab to switch between windows.  Otherwise the MessageDialog gets "lost" easily
            # in a window stack on a dev box.
            win = gtk.Window(gtk.WINDOW_TOPLEVEL)
            fixed = gtk.Fixed()
            background = gtk.Image()
            imgfilepath = os.path.join(PYTHON_DIR, 'images', 'Tormach-Wallpaper.png')
            if os.path.exists(imgfilepath):
                background.set_from_file(imgfilepath)
                fixed.set_size_request(1024, 768)
            else:
                fixed.set_size_request(0, 0)
            fixed.put(background, 0, 0)
            win.add(fixed)
            win.set_decorated(False)
            win.set_resizable(False)
            win.set_position(gtk.WIN_POS_CENTER)
            win.show_all()
            win.present()  # make sure it is top of z-order stack so user can see it since there's no parent window

            while True:
                is_expired = versioning.GetVersionMgr().is_build_expired()
                if is_expired:
                    msgtype = gtk.MESSAGE_ERROR
                else:
                    msgtype = gtk.MESSAGE_INFO

                md = gtk.MessageDialog(win,
                                       gtk.DIALOG_MODAL,
                                       msgtype,
                                       gtk.BUTTONS_NONE)
                md.set_title("PathPilot Test Warning")
                md.add_button("Correct Clock", gtk.BUTTONS_OK + 2)
                md.add_button("Update Now", gtk.BUTTONS_OK + 1)
                md.add_button("Continue", gtk.BUTTONS_OK)
                if is_expired:
                    md.set_markup('<span weight="bold" font_desc="Roboto Condensed 14" foreground="red">{}</span>'.format(warning_msg))
                    md.set_default_response(gtk.BUTTONS_OK + 1)
                else:
                    md.set_markup('<span weight="bold" font_desc="Roboto Condensed 14">{}</span>'.format(warning_msg))
                    md.set_default_response(gtk.BUTTONS_OK)
                response = md.run()
                md.destroy()

                # Force necessary window repainting to make sure message dialog is fully removed from screen
                ui_misc.force_window_painting()

                if response == (gtk.BUTTONS_OK + 2):
                    # correct controller clock
                    p = subprocess.Popen(['sudo', 'time-admin'])
                    while p.poll() == None:
                        while gtk.events_pending():
                            gtk.main_iteration(False)
                        time.sleep(0.1)

                    # loop around and check again, but use updated msg based on new date
                    warning_msg = versioning.GetVersionMgr().get_expiration_warning()
                else:
                    break

            win.destroy()

            # Force necessary window repainting to make sure message dialog is fully removed from screen
            ui_misc.force_window_painting()

            if response == gtk.BUTTONS_OK + 1:
                # Run the swupdate module.  Don't try to import it - too many conflicts with gtk ImageButtons and
                # this keeps it at arms length.
                p = subprocess.Popen(['swupdate.py'], shell=True)
                exit_code = p.wait()
                if exit_code == 1:
                    # They put a build in place so do not run PP and instead try to use the new build.
                    return False

            return True # ok to run PP

        else:
            # build has no expiration date
           return True  # ok to run PP

    # TODO: this should popup a dialog if in the very unlikely case it fails
    def check_data_directory(self):
        # makes sure that the directory ~/mill_data or ~/lathe_data exists
        # all sorts of things fail if it is missing, tool table, redis, etc.
        cp = SafeConfigParser()
        cp.read(self.ini_file)
        rs274_param_filename = cp.get('RS274NGC', 'PARAMETER_FILE')
        rs274_param_filename = os.path.expanduser(rs274_param_filename )
        path2fname, basename = os.path.split(rs274_param_filename)

        if os.path.isdir(path2fname):
            print 'Data directory %s exists' % (path2fname)
            # might be nice to put a long for directory contents list here
            #cmdline = 'ls -l %s' % path2fname
            #subprocess.call(cmdline, shell=True)
        else:
            if os.path.isfile(path2fname):
               print '%s appears to be a regular file instead of a directory. Will attempt to delete it and create directory.' % (path2fname)
               os.remove(path2fname)
            try:
                print 'Data directory %s does not exist. Creating it now.' % path2fname
                os.makedirs(path2fname)
            except OSError as err:
                print 'Failed to create data directory: %s, OSError: %s' % (path2fname, str(err))
                return

        positionfile = os.path.join(path2fname, 'position.txt')
        if os.path.exists(positionfile) and os.stat(positionfile).st_size == 0:
            print "Deleting zero length file {}".format(positionfile)
            os.remove(positionfile)



    def check_machine_class_data_folder(self):
        # directory for config files (tool.tbl, emc.var, dump.rdb)
        # The name of the folder is always $USER_HOME/'machine_class'_data (e.g. $USER_HOME/mill_data)
        datadir = os.path.join(os.environ['HOME'], self.machine_class + "_data")
        if not os.path.exists(datadir):
            os.makedirs(datadir)

        positionfile = os.path.join(datadir, 'position.txt')
        if os.path.exists(positionfile) and os.stat(positionfile).st_size == 0:
            print "Deleting zero length file {}".format(positionfile)
            os.remove(positionfile)


    def check_machine_tooltable(self, update_256=False):
        # calls to 'check_machine_tool_table.py' used to live in 'start_linuxcnc' bash script
        # this will create a new tool table if the INI tool table file does not exist
        # if it exists and does not contain the correct number tool entries it will add them
        # as well as move the mill probe from T99 P55 to P99 if needed
        #
        # handles data migration to/from 256 and 1000 entry mill tool tables
        #
        # if update_256 is True it means it means we are shutting down
        # and if this is a not a lathe config we need to update old tool table file with first 256 tools
        # from current 1000 entry tool table

        cp = SafeConfigParser()
        cp.read(self.ini_file)
        self.tooltable_filename = cp.get('EMCIO', 'TOOL_TABLE')
        self.tooltable_filename = os.path.expanduser(self.tooltable_filename)

        # if we are a mill, but running in rapidturn mode, then for the purposes of checking the machine tool table
        # we tell the script we are a lathe instead.
        machine_class = self.machine_class
        if self.rapidturn_mode:
            machine_class = 'lathe'

        if update_256:
            # UI exited
            # possibly backport tools 1-256 to old smaller tool table - let the script decide.
            check_tooltable_cmd = ['check_machine_tool_table.py', '%s' % self.tooltable_filename, machine_class, 'update-256' ]
        else:
            check_tooltable_cmd = ['check_machine_tool_table.py', '%s' % self.tooltable_filename, machine_class ]

        print check_tooltable_cmd
        p = subprocess.Popen(check_tooltable_cmd)
        check_tooltable_retval = p.wait()


    def init_atc_firmware(self):
        keep_trying = True
        while keep_trying:
            st = timer.Stopwatch()
            statusdlg = popupdlg.status_popup(None, "Initializing ATC firmware...this can take 2 minutes.\n\nDo not turn off power or E-Stop machine.")
            statusdlg.show_all()

            # Don't just block on init process or the message dialog doesn't paint reliably and
            # looks buggy
            cmd = os.path.join(const.ATCFIRMWARE_PATH, 'atcfwinit.py')
            print cmd
            p = subprocess.Popen(cmd, shell=True)
            while p.poll() == None:
                while gtk.events_pending():   # pump gtk event loop for proper drawing behavior
                    gtk.main_iteration(False)
                time.sleep(0.2)               # don't spin too hard to let update have cpu
            retval = p.wait()

            print 'ATC firmware init returned %d (0 indicates success)' % retval

            # Log how long this took
            print "ATC firmware init process took %s" % str(st)

            statusdlg.destroy()

            # Explicitly give them results with an OK dialog so they KNOW what happened before launching back
            # into PP UI.
            if retval == 0:
                with popupdlg.ok_cancel_popup(None, "Initialization of ATC firmware completed successfully.\n\nPress OK to reboot the controller.", cancel=False) as p:
                    keep_trying = False
            else:
                dlg = popupdlg.yes_no_popup(None, "ATC control board not found.  Initialization failed.\n\nReview the steps in the instructions to confirm that the ATC USB adapter cable is correctly connected to the header.  Then, verify that the machine is on and out of E-stop.\n\nRetry initialization?")
                dlg.run()
                dlg.destroy()
                if dlg.response == gtk.RESPONSE_NO:
                    keep_trying = False

            # Force necessary window repainting to make sure message dialog is fully removed from screen
            ui_misc.force_window_painting()


    def update_atc_firmware(self):
        # Need to update atc firmware which can take awhile so be sure to
        # This takes awhile so let them know what's going on...

        st = timer.Stopwatch()
        statusdlg = popupdlg.status_popup(None, "Updating ATC firmware...this can take 5-10 minutes.\n\nDo not turn off power or E-Stop machine.")
        statusdlg.show_all()

        # Don't just block on firmware process or the message dialog doesn't paint reliably and
        # looks buggy
        cmd = '{} {}'.format(os.path.join(const.ATCFIRMWARE_PATH, 'atcupdate.py'), \
                             os.path.join(const.ATCFIRMWARE_PATH, const.ATCFIRMWARE_FILENAME))
        print cmd
        p = subprocess.Popen(cmd, shell=True)
        while p.poll() == None:
            while gtk.events_pending():   # pump gtk event loop for proper drawing behavior
                gtk.main_iteration(False)
            time.sleep(0.2)               # don't spin too hard to let update have cpu
        retval = p.wait()

        print 'ATC firmware update returned %d (0 indicates success)' % retval

        # Log how long this took
        print "ATC firmware update process took %s" % str(st)

        statusdlg.destroy()

        # Because it takes so long to update the firmware, there is a good chance people walk away and do something
        # else.  Explicitly give them results with an OK dialog so they KNOW what happened before launching back
        # into PP UI.
        if retval == 0:
            with popupdlg.ok_cancel_popup(None, "ATC firmware updated successfully.\n\nPress OK to reboot the controller.", cancel=False) as p:
                pass
        else:
            with popupdlg.ok_cancel_popup(None, "ATC firmware update failed.\n\nPress OK to reboot the controller.", cancel=False) as p:
                pass

        # Force necessary window repainting to make sure message dialog is fully removed from screen
        ui_misc.force_window_painting()


    def verify_and_update_mesa_interface(self):
        '''
        Returns a tuple (boolean indicating if we should continue, exit code if not continuing)
        Examples:
            (True, None) if good to go
            (False, const.EXITCODE_SHUTDOWN) if mesa firmware reflashed and power cycle is needed to get new firmware to load
            (False, const.EXITCODE_CONFIG_CHOOSER) if mesa firmware flash failed and user wants to try a different config
        '''
        #--------------------------------------------------------------------------------------------
        # Torstep does not yet support mesaflash or firmware downloads via Ethernet
        if self.board_type == 'stmc':
            print 'Not checking .bit file for Torstep.'
            return (True, None)
        # verify .bit file
        self.mesaflash = os.path.join(TMC_DIR, 'bin', 'mesaflash')
        if self.is_ethernet:
            mesa_verify = ['sudo', self.mesaflash, '--device', self.board_type,
                           '--addr', self.ip_address, '--verify', self.bit_file]
        else:
            mesa_verify = ['sudo', self.mesaflash, '--device', self.board_type,
                           '--verify', self.bit_file]

        print mesa_verify
        p = subprocess.Popen(mesa_verify)
        mesa_retval = p.wait()
        print "mesaflash returned %d" % mesa_retval
        if mesa_retval == 0:
            print 'FPGA .bit file programming verified as correct.'
            return (True, None)

        else:
            print 'FPGA and .bit file do not match. Reprogramming FPGA.'

            # this might not work if we're trying to reflash a 7i92 with ECM1 or vice-versa.
            # that can happen if the wrong config is chosen.

            self.kill_splash()

            # This takes awhile so let them know what's going on...
            statusdlg = popupdlg.status_popup(None, "Updating Mesa interface firmware...")
            statusdlg.show_all()
            statusdlg.present()  # make sure it is top of z-order stack so user can see it since there's no parent window

            # Force necessary window repainting to make sure message dialog is fully removed from screen
            ui_misc.force_window_painting()

            try:
                # Don't just block on mesa flash process or the message dialog doesn't paint reliably and
                # looks buggy
                if self.is_ethernet:
                    mesa_update = ['sudo', self.mesaflash, '--device', self.board_type, '--addr', self.ip_address, '--write', self.bit_file]
                else:
                    mesa_update = ['sudo', self.mesaflash, '--device', self.board_type, '--write', self.bit_file]
                print mesa_update
                p = subprocess.Popen(mesa_update)
                while p.poll() == None:
                    while gtk.events_pending():
                        gtk.main_iteration(False)
                    time.sleep(0.2)   # don't spin too hard to let mesa update have cpu
                mesa_retval = p.wait()
                print 'Finished programming FPGA flash memory. mesaflash returned %d' % mesa_retval

            finally:
                statusdlg.destroy()
                # Force necessary window repainting to make sure message dialog is fully removed from screen
                ui_misc.force_window_painting()

            if mesa_retval != 0:
                # error - probably the wrong config was chosen...or the ini file is wrong
                self.kill_splash()
                # toss these in the dialog to make phone troubleshooting slightly easier
                basebitfilename = os.path.basename(self.bit_file)
                baseconfigname = os.path.basename(self.ini_file)
                dlg = exit_retry_changeconfig_popup(None,
                                                   'Mesa Interface Error\n\nFirmware failed to update properly on Mesa interface.\n\n[{:s}  {:s}]'.format(baseconfigname, basebitfilename),
                                                   retry_enabled=False)
                dlg.run()
                dlg.destroy()

                # Force necessary window repainting to make sure message dialog is fully removed from screen
                ui_misc.force_window_painting()

                # User may want to try another config.  Can happen easily if they choose an S3 config on an M/MX machine
                # because we'll use a 7i92 config and the flash will fail - easily corrected, but only if they
                # have an easy way of choosing.
                if dlg.response == dlg.RESPONSE_CHANGECONFIG:  # Change Config btn
                    return (False, const.EXITCODE_CONFIG_CHOOSER)

                return (False, const.EXITCODE_SHUTDOWN)

            # now figure out if we can reload the firmware and keep going or if we need to power cycle the board.

            if self.is_ethernet:
                # we concurrently reload the bitfile in the background while displaying the message to the user
                # to make things faster.

                mesa_reload = ['sudo', self.mesaflash, '--device', self.board_type,
                               '--addr', self.ip_address, '--reload']
                print mesa_reload
                p = subprocess.Popen(mesa_reload)

                # don't botther putting up info dialog requiring OK click if we're doing automated launch tests
                if not self.launch_test:
                    with popupdlg.ok_cancel_popup(None,
                                                  "Mesa Interface Updated\n\nFirmware updated on Mesa ethernet interface successfully.",
                                                  cancel=False, checkbox=False) as dlg:
                        pass
                    # Force necessary window repainting to make sure message dialog is fully removed from screen
                    ui_misc.force_window_painting()

                mesa_retval = p.wait()
                print 'Reload Ethernet FPGA flash memory. No need to power cycle. mesaflash returned %d' % mesa_retval
                if mesa_retval != 0:
                    # Odd. We successfully flashed the firmware, but the reload failed?
                    print "Odd why the bitfile reload failed.  Forcing a reboot and hoping that solves it."
                    return (False, const.EXITCODE_SHUTDOWN)

                print 'Pausing to give time for FPGA to reboot.'
                # if this is not done then hm2_eth fails to find the FPGA on the Ethernet
                time.sleep(2.0)
                return (True, None)

            else:
                # PCI based FPGA mesa cards require a power cycle to be absolutely
                # sure the new code loads properly.
                if self.launch_test:
                    # we're running automated launch tests so just try to smack the FPGA to
                    # reload because we know for sure it works with the modern mesa card we use for this testing.
                    mesa_reload = ['sudo', self.mesaflash, '--device', self.board_type, '--reload']
                    print mesa_reload
                    p = subprocess.Popen(mesa_reload)
                    mesa_retval = p.wait()
                    if mesa_retval != 0:
                        print "Odd why the bitfile reload failed.  Forcing a reboot and hoping that solves it."
                        return (False, const.EXITCODE_SHUTDOWN)

                    print 'Pausing to give time for FPGA to reboot.'
                    time.sleep(2.0)
                    return (True, None)

                else:
                    self.kill_splash()
                    with popupdlg.ok_cancel_popup(None,
                                                  "Mesa Interface Updated\n\nFirmware updated on Mesa interface.  After display indicates safe to power down, power off the controller for 10 seconds, then restore power to fully load the new firmware.",
                                                  cancel=False, checkbox=False) as dlg:
                        pass
                    # Force necessary window repainting to make sure message dialog is fully removed from screen
                    ui_misc.force_window_painting()

                    return (False, const.EXITCODE_SHUTDOWN)


    def is_spare_network_interface_available(self):
        '''
        run ifconfig -a -s, throw the first line, ignore lo and eth0
        if there are more, then we have a spare to config
        if skipped, see if date, time, and time zone are correct
        '''
        try:
            cmd = 'ifconfig -a -s'
            result = subprocess.check_output(cmd, shell=True)
            print '%s: %s' % (cmd, result)
            lines = result.splitlines()
            del lines[0]  # toss header line
            for ll in lines:
                ifname = ll.split()[0]
                if ifname not in ('lo'):
                    # Found candidate.  If we're using an interface for machine control
                    # it will already have an IP address.  Or expert user may have already
                    # configured an interface on their own.  Check that it doesn't have an IP yet.
                    if self.get_ip_address(ifname) == '':
                        print "Found spare network interface that does not have an ip address: %s" % ifname
                        return True
        except:
            pass
        return False


    def possible_network_setup_and_timeclock_verify(self):
        # don't bother in virtualized environments
        if self.sim_mode:
            return

        # if we have a spare network interface and are doing first time machine config on this controller
        # than proactively offer to help them configure the network.
        write_needed = False
        with open(PATHPILOTJSON_FILE, 'r') as jsonfile:
            config = json.load(jsonfile)
            if config["fileversion"] != 2:
                return
            # setup defaults as needed
            if "network_setup_skipped" not in config["pathpilot"]:
                config["pathpilot"]["network_setup_skipped"] = False
                write_needed = True
            if "time_of_day_clock_verified" not in config["pathpilot"]:
                config["pathpilot"]["time_of_day_clock_verified"] = False
                write_needed = True

        # if they have ever skipped the network config, don't offer it automatically
        # regardless of what interfaces might now be available.
        if config["pathpilot"]["network_setup_skipped"] == False and self.is_spare_network_interface_available():
            self.kill_splash()

            # This is a do-nothing, zero sized window, but it is top level and can serve as the parent
            # window of the MessageDialog below.  This is required so that the window manager "sees" it
            # when using Alt-Tab to switch between windows.  Otherwise the MessageDialog gets "lost" easily
            # in a window stack on a dev box.
            win = gtk.Window(gtk.WINDOW_TOPLEVEL)
            fixed = gtk.Fixed()
            background = gtk.Image()
            imgfilepath = os.path.join(PYTHON_DIR, 'images', 'Tormach-Wallpaper.png')
            if os.path.exists(imgfilepath):
                background.set_from_file(imgfilepath)
                fixed.set_size_request(1024, 768)
            else:
                fixed.set_size_request(0, 0)
            fixed.put(background, 0, 0)
            win.add(fixed)
            win.set_decorated(False)
            win.set_resizable(False)
            win.set_position(gtk.WIN_POS_CENTER)
            win.show_all()
            win.present()  # make sure it is top of z-order stack so user can see it since there's no parent window

            md = gtk.MessageDialog(win,
                                   gtk.DIALOG_MODAL,
                                   gtk.MESSAGE_QUESTION,
                                   gtk.BUTTONS_NONE)
            md.set_title("Networking")
            md.set_markup('<span weight="bold" font_desc="Roboto Condensed 12">We found an unused network adapter.  Do you want to set it up now?\n\n</span>' +
                          '<span weight="normal" font_desc="Roboto Condensed 11">Once set up, you can:\n\n* Receive notifications for new, free PathPilot features\n* Use Dropbox to synchronize G-code folders\n* Share the controller\'s G-code folder with a computer (Windows or Mac)\n* Transfer G-code files quicker and more conveniently than with a USB drive</span>')
            md.add_button("Skip", gtk.BUTTONS_OK+1)
            md.add_button("Set Up", gtk.BUTTONS_OK)
            md.set_default_response(gtk.BUTTONS_OK)
            md.set_size_request(600, 250)
            vbox = md.get_message_area()
            for child in vbox.get_children():
                child.set_size_request(500, 250)

            response = md.run()
            md.destroy()
            win.destroy()

            # Force necessary window repainting to make sure message dialog is fully removed from screen
            ui_misc.force_window_painting()

            if response == gtk.BUTTONS_OK:  # Set Up
                # run netconfig
                cmdline = os.path.join(PYTHON_DIR, "netconfig/netconfig.py")
                print "Running %s" % cmdline
                subprocess.call(cmdline, shell=True)

            elif response == gtk.BUTTONS_OK+1:  # Skip
                config["pathpilot"]["network_setup_skipped"] = True
                write_needed = True

        # Have them validate the time of day clock and time zone
        '''
        Not quite yet - the dialog is sort of confusing - need more feedback on this one first.
        if config["pathpilot"]["time_of_day_clock_verified"] == False:
            p = subprocess.Popen(['sudo', 'time-admin'])
            while p.poll() == None:
                while gtk.events_pending():
                    gtk.main_iteration(False)
                time.sleep(0.1)
            config["pathpilot"]["time_of_day_clock_verified"] = True
            write_needed = True
        '''

        if write_needed:
            with open(PATHPILOTJSON_FILE, 'w') as jsonfile:
                jsonfile.write("\n")   # make cat'ing the contexts of the file more legible in the shell
                json.dump(config, jsonfile, indent=4, sort_keys=True)
                jsonfile.write("\n")   # make cat'ing the contexts of the file more legible in the shell


    def main_loop(self):
        if self.check_eula_acceptance() == False:
            return const.EXITCODE_SHUTDOWN

        self.display_splash()

        # check PCI bus for Mesa 5i25
        # pay attention to '1' vs. 'i'
        cp_comm_methods = ""
        lspci_output = subprocess.check_output(['/usr/bin/lspci', '-n', '-d', '2718:5125'])
        if '2718:5125' in lspci_output:
            print 'PCI FPGA interface card is installed.'
            cp_comm_methods += "--db25parallel "
        else:
            ifconfig_result = subprocess.call(['/sbin/ifconfig', 'eth0'])
            if ifconfig_result == 0:
                # wired ethernet eth0 interface is present so might be using that for machine control
                print 'eth0 present on machine controller'
                cp_comm_methods += "--ethernet "

        while True:
            print 'top of pathpilotmanager.py while() loop'

            # Force necessary window repainting to make sure message dialog is fully removed from screen
            ui_misc.force_window_painting()

            # before we do anything, check if there is a software update
            # ready to go.  this dramatically helps development because we can just
            # copy a tarball in the right spot, setup the update_file.txt and run operator_login
            # to recover from a situation where PP can't start.
            # or you can just run swupdate.py from the command line to do that for you.
            update_return_code = self.check_for_pathpilot_update()
            if update_return_code == 1:
                # a new version has been installed
                # We used to start the 'new' operator_login script over again and launch into running
                # the new PathPilot.  But on a decent number of controllers in the field
                # the entire OS would hang (have no idea why, maybe a RTAPI kernel bug or something
                # related to timing and re-running it).
                # Under normal operation, re-launching PathPilot never happens. It is always a clean,
                # fresh boot back to a power off.  So now to avoid any customer anxiety about
                # a hang, we always reboot the controller after an update.  Otherwise the hang just
                # causes frustration and a loss of reliability trust in the customer mind,
                # even though we now have things solid on the disk file system flushing issue so
                # at least the controller is not borked on the way back up.
                msg = "Update successfully applied.\n\nRemove any USB drive(s) and press OK to reboot controller."
                print msg
                self.kill_splash()
                with popupdlg.ok_cancel_popup(None, msg, cancel=False, checkbox=False) as dialog:
                    pass
                return const.EXITCODE_REBOOTAFTERUPDATE
            elif update_return_code == 2:
                # no update installed or it failed, rerun what we already had
                print 'something went wrong during update process, trying to use current version of PathPilot'
            else:
                print 'no update file found'


            self.check_rtapi_app_permissions()
            print 'done checking rtapi_app permissions'

            # find/generate the proper linuxcnc INI file
            read_ini_return_code = self.read_pathpilotjson_file()
            if read_ini_return_code != 0:
                if read_ini_return_code in (PATHPILOTJSON_FILE_NOT_FOUND, PATHPILOTJSON_FILE_CORRUPT):
                    # no json file or it was corrupt
                    # run config_chooser to generate a valid one
                    print 'Configuration file %s not found or corrupted.' % PATHPILOTJSON_FILE
                    cpexitcode = self.run_config_chooser(comm_methods=cp_comm_methods)
                    if cpexitcode == CONFIGCHOOSER_EXITCODE_INSTALL_UPDATE:
                        # top of while loop will find the update_file.txt and install the software
                        continue
                    elif cpexitcode != CONFIGCHOOSER_EXITCODE_SUCCESS or not os.path.exists(PATHPILOTJSON_FILE):
                        # config chooser did not select new config
                        # exit
                        print 'No config_chooser selection made or %s does not exist. Exiting' % PATHPILOTJSON_FILE
                        return 0

                    # selection made, try again
                    continue

                elif read_ini_return_code == CONFIG_MAKE_INI_FAILURE:
                    self.kill_splash()

                    # need to display informational dialog indicating INI file not found
                    msg = 'Error generating INI file: %s' % self.ini_file
                    with popupdlg.ok_cancel_popup(None, msg, cancel=False, checkbox=False) as dialog:
                        pass

                    # delete PATHPILOTJSON_FILE to force config_chooser
                    os.unlink(PATHPILOTJSON_FILE)
                    # try again
                    continue

            else:
                print 'configured INI file: %s' % self.ini_file

            # INI file name is known and file exists

            # Drop the marker file down so we can tell if the UI ever fully came up with the configuration that
            # the json file has.
            crashdetection.create_crash_detection_file()

            # If we're in sim mode, make sure we've released the ethernet ports for customer/developer use.
            # We do this by forcing db25parallel communication (which is never really checked or used because of sim)
            # but this releases the ethernet interface.
            if self.sim_mode:
                print "Sim mode forcing communication_method override to db25parallel so we release the ethernet interface if it isn't already."
                self.communication_method = 'db25parallel'

                print "Forcing POSIX non-realtime mode because of sim mode."
                os.environ['PATHPILOT_NONREALTIME_MODE'] = '1'
            else:
                # be sure to set this as we can transition from sim to non-sim if user goes into config chooser and knows the key sequence
                os.environ['PATHPILOT_NONREALTIME_MODE'] = '0'

            # Setting the communication method requires root privs to rewrite
            # some files and restart services so it is partitioned off in
            # a separate process.
            fullpath = os.path.join(PYTHON_DIR, "set_comm_method.py")
            if os.getenv('PATHPILOT_IGNORE_HARDWARE'):
                result = 0
            else:
                result = subprocess.call("sudo python %s %s" % (fullpath, self.communication_method), shell=True)

            if result != 0:
                # failure setting communication method
                print "set_comm_method.py returned %d unexpectedly" % result
                self.kill_splash()
                with popupdlg.ok_cancel_popup(None, "Error setting up machine control communication method %s" % self.communication_method, cancel=False, checkbox=False) as dialog:
                    pass
                if os.path.exists(PATHPILOTJSON_FILE):
                    os.unlink(PATHPILOTJSON_FILE)
                continue   # skip the rest of the giant outside while loop and try all over again at the top with config chooser

            # check INI file .bit file
            ini = SafeConfigParser()
            ini.read(self.ini_file)
            self.bit_file = ''
            self.ip_address = ''         # IP address of the mesa/ECM board
            self.board_type = ''

            if ini.has_section('HOSTMOT2'):
                self.bit_file = ini.get('HOSTMOT2', 'BITFILE0')
                # no bit file is OK as this might be a sim config
                if self.bit_file != '':
                    self.bit_file = os.path.join(TMC_DIR, mgr.bit_file)
                    print '[HOSTMOT2]BITFILE0: %s' % self.bit_file

                    # get board name
                    self.board_type = ini.get('HOSTMOT2', 'BOARD')

                    # Ethernet or PCI FPGA?
                    self.is_ethernet = False
                    self.hm2_driver = ini.get('HOSTMOT2', 'DRIVER')
                    if 'hm2_eth' in self.hm2_driver:
                        # Ethernet FPGA

                        assert self.communication_method == "ethernet"

                        self.is_ethernet = True
                        print 'Ethernet attached FPGA.'
                        # fish the IP address out of [HOSTMOT2]DRIVER_PARAMS
                        # string will look like:
                        # "board_ip=10.10.10.10 config=num_encoders=0 num_pwmgens=1 num_3pwmgens=0 num_stepgens=5"
                        self.driver_params = ini.get('HOSTMOT2', 'DRIVER_PARAMS')
                        print '[HOSTMOT2]DRIVER_PARAMS: %s' % self.driver_params
                        params = self.driver_params.strip()
                        params = self.strip_quote_pair(params)
                        print 'params: %s' % params
                        if params.startswith('board_ip'):
                            self.ip_address = params.split('=')[1]
                            self.ip_address = self.ip_address.split()[0]
                            print 'FPGA IP address: %s' % self.ip_address
                    elif 'hm2_pci' in self.hm2_driver:
                        # PCI FPGA
                        print 'PCI attached FPGA.'
                    else:
                        # Unknown or does not exist
                        print 'Unrecognized [HOSTMOT2]DRIVER: %s' % self.hm2_driver

                    # test for PCI card present
                    if self.board_type == '5i25':
                        # check PCI bus for Mesa 5i25
                        # pay attention to '1' vs. 'i'
                        lspci_output = subprocess.check_output(['/usr/bin/lspci', '-n', '-d', '2718:5125'])
                        if '2718:5125' in lspci_output:
                            print 'Mesa PCI FPGA interface card is installed.'
                        else:
                            print 'Mesa PCI FPGA interface card not detected.'
                            self.kill_splash()
                            with exit_retry_changeconfig_popup(None,
                                                               'Mesa communication PCI interface card not detected.\n\nWith power off and the power cord unplugged from the controller, try reseating the Mesa board in the PCI slot.',
                                                               retry_enabled=False) as dialog:
                                pass
                            # Force necessary window repainting to make sure message dialog is fully removed from screen
                            ui_misc.force_window_painting()

                            if dialog.response == exit_retry_changeconfig_popup.RESPONSE_CHANGECONFIG:
                                # force selection of machine type
                                if os.path.exists(PATHPILOTJSON_FILE):
                                    os.unlink(PATHPILOTJSON_FILE)
                                continue   # skip the rest of the giant outside while loop and try all over again at the top with config chooser

                            # don't put them into config chooser give them the shutdown screen so they can check things out.
                            sys.exit(1)

                    # test for Ethernet interface present and configured as expected
                    if self.hm2_driver == 'hm2_eth':
                        # determine if wired interface exists
                        if self.get_interface_present(CONTROLLER_INTERFACE) == False:
                            msg = 'Controller network interface %s not found.' % (CONTROLLER_INTERFACE)
                            print msg
                            self.kill_splash()
                            with exit_retry_changeconfig_popup(None, msg, retry_enabled=False) as dialog:
                                pass
                            # Force necessary window repainting to make sure message dialog is fully removed from screen
                            ui_misc.force_window_painting()

                            if dialog.response == exit_retry_changeconfig_popup.RESPONSE_CHANGECONFIG:
                                # force selection of machine type
                                if os.path.exists(PATHPILOTJSON_FILE):
                                    os.unlink(PATHPILOTJSON_FILE)
                                continue   # skip the rest of the giant outside while loop and try all over again at the top with config chooser

                            sys.exit(7)

                        # determine if wired Ethernet interface has link status
                        msg = 'No Ethernet link detected.\n\nCheck machine is powered on, then check cabling between controller and machine.'
                        run_cp = False
                        while True:
                            # Force necessary window repainting to make sure message dialog is fully removed from screen
                            ui_misc.force_window_painting()

                            if self.get_link_status(CONTROLLER_INTERFACE) == False:
                                self.kill_splash()

                                with exit_retry_changeconfig_popup(None, msg, retry_enabled=True) as dialog:
                                    if dialog.response == exit_retry_changeconfig_popup.RESPONSE_RETRY:
                                        # check for link again
                                        print 'pressed retry'
                                        continue
                                    elif dialog.response == exit_retry_changeconfig_popup.RESPONSE_CHANGECONFIG:
                                        print 'pressed change config'
                                        run_cp = True
                                        break
                                    else:
                                        # giving up
                                        print 'pressed exit'
                                        sys.exit(6)
                            else:
                                break

                        if run_cp:
                            # force selection of machine type
                            if os.path.exists(PATHPILOTJSON_FILE):
                                os.unlink(PATHPILOTJSON_FILE)
                            continue   # skip the rest of the giant outside while loop and try all over again at the top with config chooser


                        # determine if wired Ethernet interface is on same IP network
                        current_ip_address = self.get_ip_address(CONTROLLER_INTERFACE)
                        if current_ip_address != CONTROLLER_IP:
                            # interface not configured to correct IP address
                            # current_ip_address can be <null> under error conditions
                            if current_ip_address == '':
                                current_ip_address = "NULL"
                            msg = "Warning: IP address of controller ethernet port %s should be %s, not \"%s\". Attempting to fix." % (CONTROLLER_INTERFACE, CONTROLLER_IP, current_ip_address)
                            print msg
                            self.kill_splash()
                            with popupdlg.ok_cancel_popup(None, msg, cancel=False, checkbox=False) as dialog:
                                pass
                            # Force necessary window repainting to make sure message dialog is fully removed from screen
                            ui_misc.force_window_painting()

                            # attempt to set it correctly
                            self.set_ip_address(CONTROLLER_INTERFACE, CONTROLLER_IP)
                            if self.get_ip_address(CONTROLLER_INTERFACE) != CONTROLLER_IP:
                                msg = 'Failed to set IP address to %s.' % CONTROLLER_IP
                                print msg
                                self.kill_splash()
                                with exit_retry_changeconfig_popup(None, msg, retry_enabled=False) as dialog:
                                    pass

                                # Force necessary window repainting to make sure message dialog is fully removed from screen
                                ui_misc.force_window_painting()

                                if dialog.response == exit_retry_changeconfig_popup.RESPONSE_CHANGECONFIG:
                                    # force selection of machine type
                                    if os.path.exists(PATHPILOTJSON_FILE):
                                        os.unlink(PATHPILOTJSON_FILE)
                                    continue   # skip the rest of the giant outside while loop and try all over again at the top with config chooser

                                sys.exit(8)

                        # due to bugs in drivers and ethernet chipsets, we need to disable speed and duplex negotiation.
                        # we do it here so that we take advantage of the autoneg up to this point and then disable it once it
                        # knows what it wants to use.  Turning off autoneg can cause eth0 to not work for a few seconds though
                        # so we want to do this before we try the ping stuff so that we know by the time we get through ping
                        # that we're ready to rock.
                        self.disable_ethernet_autonegotiation()

                        # ping it and wait for up to 500 milliseconds for answer before falling into further communication check loop
                        self.testing_connectivity = True

                        # pokes the eth0 interface a little without having any downside.  it seems a little sleepy for a few seconds
                        # after we turn off auto negotiation.  trying to avoid the flash up/down of the ping dialog below unless we
                        # really need it.
                        self.try_ping_ip(self.ip_address, 0)

                        if not self.try_ping_ip(self.ip_address, 0.500):
                            # loop watching for the ECM board to respond successfully.
                            # dialog will automatically dismiss upon success or user can choose to change the machine config or
                            # exit (which leads to power down)
                            print 'Ethernet FPGA not found at IP address %s' % self.ip_address
                            msg = 'Attempting communication with %s machine, check machine power and cabling to controller.' % self.machine_class

                            dialog = progress_popup(None, msg)

                            # start a timer to check background pinging
                            # each ping attempt that fails has a minimum timeout of 1 full second.  we run this timeout
                            # at a higher frequency as it simply checks for success or failure and kicks off a further background ping as necessary
                            glib.timeout_add(100, self.on_ping_timer_expire, dialog)

                            self.kill_splash()

                            dialog.run()
                            dialog.destroy()
                            # Force necessary window repainting to make sure message dialog is fully removed from screen
                            ui_misc.force_window_painting()

                            # trigger the timeout callback to give up since there isn't any way to cancel the timer that I can find
                            # if the user clicked a button to dismiss the dialog, the timer is still running...
                            self.testing_connectivity = False

                            # force selection of machine type
                            if dialog.response == progress_popup.RESPONSE_CHANGECONFIG:
                                if os.path.exists(PATHPILOTJSON_FILE):
                                    os.unlink(PATHPILOTJSON_FILE)
                                continue   # skip the rest of the giant outside while loop and try all over again at the top with config chooser

                            elif dialog.response == gtk.RESPONSE_CANCEL:
                                # user gave up for the moment.
                                sys.exit(9)

                            elif dialog.response == progress_popup.RESPONSE_PINGSUCCESS:
                                pass   # nice recovery by the user!

                            else:
                                assert False, "Unexpected dialog response"

                        print 'Ethernet FPGA found at IP %s' % self.ip_address

                        print "FINAL settings for interface %s:" % CONTROLLER_INTERFACE
                        self.log_ethtool_settings()


                    #--------------------------------------------------------------------------------------------
                    # verify .bit file and flash it as needed
                    success, code = self.verify_and_update_mesa_interface()
                    if not success:
                        if code == const.EXITCODE_CONFIG_CHOOSER:
                            # force selection of machine type
                            if os.path.exists(PATHPILOTJSON_FILE):
                                os.unlink(PATHPILOTJSON_FILE)
                            continue   # skip the rest of the giant outside while loop and try all over again at the top with config chooser
                        else:
                            # need to power cycle
                            return const.EXITCODE_SHUTDOWN
                else:
                    print 'No .bit file in INI file. Possible sim config?'
            else:
                print 'No HOSTMOT2 section found in INI file.'


            self.possible_network_setup_and_timeclock_verify()
            self.check_data_directory()
            self.check_machine_tooltable()
            self.upgrade_redis_persistence_format()

            # whoa - lets see if the gate came down.
            if self.handle_possible_build_expiration():
                # build NOT expired so light it up
                # run LinuxCNC
                try:
                    print 'About to run scripts/start_linuxcnc.'
                    p = subprocess.Popen(['start_linuxcnc', mgr.ini_file])
                    linuxcnc_retval = p.wait()
                    print 'Return code from linuxcnc script: %d' % linuxcnc_retval
                    self.check_machine_tooltable(update_256=True)
                except OSError:
                    print 'Failed to run linuxcnc script.'
                    return 4

                # Does the marker file exist?  The UI deletes the marker file right away once it gets through
                # its full init.  If the marker file exists it means something died between the start_linuxcnc script kick off
                # and the UI fully up.  Lots of odd ways that might happen, but choosing the wrong config or moving
                # controllers between machines is one way (hal all misconfigured).
                # Warn them and then toss them into config chooser without deleting the current pathpilot.json file.
                # They can try to choose a config that will work or just exit config chooser leaving the file intact and powering
                # off the controller.
                if crashdetection.crash_detection_file_exists():
                    # Are we running automated launch tests?
                    if self.launch_test:
                        # Yes.
                        return linuxcnc_retval
                    else:
                        print 'crash detection file unexpectedly exists - sending into config chooser.'
                        self.kill_splash()
                        with popupdlg.ok_cancel_popup(None,
                                                      "Error Starting PathPilot\n\nIt appears that PathPilot was not able to start successfully. Sometimes this can be caused by an incorrect machine configuration. After clicking OK, the machine configuration will appear and provide an opportunity to make changes if necessary.",
                                                      cancel=False, checkbox=False) as dialog:
                            pass
                        # Force necessary window repainting to make sure message dialog is fully removed from screen
                        ui_misc.force_window_painting()

                        retcode = self.run_config_chooser(comm_methods=cp_comm_methods)
                        # if they just clicked exit right away without changing the config, then power down.
                        if retcode == CONFIGCHOOSER_EXITCODE_NOCONFIGSELECTED:
                            break

                        continue
            else:
                # the file system may be setup perfectly for the software update that is checked below.
                linuxcnc_retval = const.EXITCODE_SHUTDOWN

            # process return code from LinuxCNC
            if linuxcnc_retval == const.EXITCODE_SHUTDOWN:
                # 0 normal exit
                print 'linuxcnc script exited normally.'
                # check for software update
                update_return_code = self.check_for_pathpilot_update()
                if update_return_code == 1:
                    # a new version has been installed
                    # We used to start the 'new' operator_login script over again and launch into running
                    # the new PathPilot.  But on a decent number of controllers in the field
                    # the entire OS would hang (have no idea why, maybe a RTAPI kernel bug or something
                    # related to timing and re-running it).
                    # Under normal operation, re-launching PathPilot never happens. It is always a clean,
                    # fresh boot back to a power off.  So now to avoid any customer anxiety about
                    # a hang, we always reboot the controller after an update.  Otherwise the hang just
                    # causes frustration and a loss of reliability trust in the customer mind,
                    # even though we now have things solid on the disk file system flushing issue so
                    # at least the controller is not borked on the way back up.
                    msg = "Update successfully applied.\n\nRemove any USB drive(s) and press OK to reboot controller."
                    print msg
                    self.kill_splash()
                    with popupdlg.ok_cancel_popup(None, msg, cancel=False, checkbox=False) as dialog:
                        pass
                    return const.EXITCODE_REBOOTAFTERUPDATE
                elif update_return_code == 2:
                    # no update installed or it failed, rerun what we already had
                    print 'something went wrong during update process, restarting current version of PathPilot'
                    continue
                else:
                    # expand the partition and/or file system for /dev/sda3 as needed.
                    # this is done here so that one can image a controller from the .rdr
                    # and then know that after the first power up and down, it will have the file system
                    # grown.  on graceful power down seems better than on power up.
                    p = subprocess.Popen(["/usr/bin/env", "python", os.path.join(SCRIPTS_DIR, 'expand_partition_as_needed.py')])
                    p.wait()

                    print 'no update file found, exiting normally'
                    return 0
            elif linuxcnc_retval == const.EXITCODE_PROCESS_WAS_KILLED:
                # 137 UI process killed
                print 'linuxcnc script exited normally.'
                # exit
                return 0
            elif linuxcnc_retval == const.EXITCODE_CONFIG_CHOOSER:
                # 11 run config_chooser (user did an "admin config" in the MDI line)
                cpexitcode = self.run_config_chooser(comm_methods=cp_comm_methods)
                # in any condition we want to try to send them back into the mill or lathe UI code because
                # they already had config before running config_chooser in this situation. Either they chose a new config
                # and want to try it right away or they got scared and hit exit and the existing config file
                # is still there.
                # and if something is corrupt about it the top of the while loop will check all that anyway.
                continue
            elif linuxcnc_retval == const.EXITCODE_CONFIG_FAILED:
                with popupdlg.ok_cancel_popup(None, 'Loading the selected configuration failed. Returning to configuration chooser.', cancel=False, checkbox=False) as dialog:
                    pass
                # 17 LinuxCNC HALCMD failed to load the chosen config. Send the user back to config chooser, and shut down if they click exit
                cpexitcode = self.run_config_chooser(comm_methods=cp_comm_methods)
                if cpexitcode == CONFIGCHOOSER_EXITCODE_INSTALL_UPDATE:
                    continue
                elif cpexitcode != CONFIGCHOOSER_EXITCODE_SUCCESS or not os.path.exists(PATHPILOTJSON_FILE):
                    # config chooser did not select new config
                    # exit
                    print 'No config_chooser selection made after HALCMD load failure or %s does not exist. Exiting' % PATHPILOTJSON_FILE
                    return 0
                continue
            elif linuxcnc_retval == const.EXITCODE_MILL2RAPIDTURN:
                print 'Switching from mill to rapidturn'
                # 12 switch from mill to rapidturn
                # the sleep() is to avoid a nasty race where USB I/O hasn't shutdown
                time.sleep(2)
                continue
            elif linuxcnc_retval == const.EXITCODE_RAPIDTURN2MILL:
                print 'Switching from rapidturn to mill'
                # 13 switch from rapidturn to mill
                # the sleep() is to avoid a nasty race where USB I/O hasn't shutdown
                time.sleep(2)
                continue
            elif linuxcnc_retval == const.EXITCODE_SETTINGSRESTORE:
                # 14 MDI ADMIN SETTINGS RESTORE
                # the sleep() is to avoid a nasty race where USB I/O hasn't shutdown
                print 'linuxcnc exit code means ADMIN SETTINGS RESTORE is needed.'
                time.sleep(2)
                self.check_for_settings_restore()
                continue
            elif linuxcnc_retval == const.EXITCODE_UPDATE_ATC_FIRMWARE:
                # the atc hal user comp and the atc UI code worked together to figure out
                # the firmware should be updated.
                print 'linuxcnc exit code means ATC firmware needs updating.'

                # the sleep() is to avoid a nasty race where USB I/O hasn't shutdown
                time.sleep(2)
                self.update_atc_firmware()
                return const.EXITCODE_REBOOTAFTERUPDATE
            elif linuxcnc_retval == const.EXITCODE_ATC_FIRMWARE_INIT:
                print 'linuxcnc exit code means ATC firmware initializtion needs to be performed with special USB adapter cable.'

                # the sleep() is to avoid a nasty race where USB I/O hasn't shutdown
                time.sleep(2)
                self.init_atc_firmware()
                return const.EXITCODE_REBOOTAFTERUPDATE
            else:
                # anything else is unknown
                break

        # while
        return 0


class exit_retry_changeconfig_popup(popupdlg.popup):

    RESPONSE_CHANGECONFIG = "ResponseChangeConfig"
    RESPONSE_RETRY        = "ResponseRetry"

    def __init__(self, parentwindow, message, retry_enabled):
        popupdlg.popup.__init__(self, parentwindow, message,
                                touchscreen_enabled=False,
                                checkbox_enabled=False,
                                entry_enabled=False)

        self.changeconfig_button = btn.ImageButton('button_change_configuration.png', 'popup-changeconfig-button')
        self.exit_button = btn.ImageButton('button_job_exit.png', 'popup-exit-button')

        self.changeconfig_button.connect('button-release-event', self.on_changeconfig_button_release)
        self.exit_button.connect('button-release-event', self.on_exit_button_release)

        # order of the list is important, its left to right in button layout logic
        self.buttonlist = [ self.exit_button, self.changeconfig_button ]

        if retry_enabled:
            self.retry_button = btn.ImageButton('button_retry.png', 'popup-retry-button')
            self.retry_button.connect('button-release-event', self.on_retry_button_release)
            self.buttonlist.append(self.retry_button)

        self._perform_layout()

    def on_changeconfig_button_release(self, widget, data=None):
        self.response = exit_retry_changeconfig_popup.RESPONSE_CHANGECONFIG
        gtk.main_quit()

    def on_exit_button_release(self, widget, data=None):
        self.response = gtk.RESPONSE_CANCEL
        gtk.main_quit()

    def on_retry_button_release(self, widget, data=None):
        self.response = exit_retry_changeconfig_popup.RESPONSE_RETRY
        gtk.main_quit()


class progress_fixed(gtk.Fixed):

    def __init__(self):
        gtk.Fixed.__init__(self)

        self._progressbar = gtk.ProgressBar()
        self._progressbar.set_orientation(gtk.PROGRESS_LEFT_TO_RIGHT)
        self._progressbar.set_size_request(450, 30)
        self._progressbar.set_pulse_step(0.05)   # 5% of the length of the bar

        self.put(self._progressbar, 0, 0)
        self.set_size_request(450, 30)


    def pulse(self):
        self._progressbar.pulse()



class progress_popup(popupdlg.popup):

    RESPONSE_CHANGECONFIG = "ResponseChangeConfig"
    RESPONSE_PINGSUCCESS = "ResponsePingSuccess"


    def __init__(self, parentwindow, message):

        popupdlg.popup.__init__(self, parentwindow, message,
                                touchscreen_enabled=False,
                                checkbox_enabled=False,
                                entry_enabled=False)

        # create the gtk.Fixed object that contains a child progress bar widget and let the popup dialog
        # know about it so that the automatic layout and sizing works.
        self._pbfixed = progress_fixed()
        self._add_optional_fixed_child(self._pbfixed)

        self.changeconfig_button = btn.ImageButton('button_change_configuration.png', 'popup-changeconfig-button')
        self.exit_button = btn.ImageButton('button_job_exit.png', 'popup-exit-button')

        self.changeconfig_button.connect('button-release-event', self.on_changeconfig_button_release)
        self.exit_button.connect('button-release-event', self.on_exit_button_release)

        # order of the list is important, its left to right in button layout logic
        self.buttonlist = [ self.exit_button, self.changeconfig_button ]

        self._perform_layout()


    def pulse(self):
        self._pbfixed.pulse()


    def on_changeconfig_button_release(self, widget, data=None):
        self.response = progress_popup.RESPONSE_CHANGECONFIG
        gtk.main_quit()


    def on_exit_button_release(self, widget, data=None):
        self.response = gtk.RESPONSE_CANCEL
        gtk.main_quit()


if __name__ == "__main__":

    try:
        del _

        # unbuffer stdout so print() shows up in sync with other output
        # the pipe from the redirect in operator_login causes buffering
        sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

        gobject.threads_init()

        init_localization('en_US.UTF8')     # ISO standardized ways of identifying locale
        print _('msg_hello')                # Localization test

        # starting
        mgr = manager()

        vm = vmcheck.vmcheck()
        mgr.set_environment(vm)

        # constants.py cannot be imported until the environment has been prepared
        #
        # this style of import makes clear where the constants used come from
        import constants as const
        from config_chooser import CONFIGCHOOSER_EXITCODE_SUCCESS
        from config_chooser import CONFIGCHOOSER_EXITCODE_NOCONFIGSELECTED
        from config_chooser import CONFIGCHOOSER_EXITCODE_INSTALL_UPDATE

        if mgr.set_monitor_resolution(1024, 768) is True:
            # we just changed monitor resolution
            # we have to restart pathpilotmanager.py so that GTK gets the proper monitor
            # resolution so its screen centering math is correct.
            sys.exit(const.EXITCODE_RESOLUTIONCHANGE)

        mgr.check_debs()
        mgr.check_grub(vm)
        mgr.check_samba()

        totalmb = memory.get_total_ram_mb()
        print "Total RAM: %d MB" % totalmb

        mgr.check_window_manager()
        mgr.start_drop_caches()
        mgr.set_monitor_power_saving(False)
        mgr.set_screensaver_enabled(False)
        mgr.start_dropbox()
        mgr.calibrate_touchscreen()
        mgr.disable_ethernet_irq_coalescing()
        mgr.check_for_problematic_wifi_card()

        # this code cannot run until constants.py has been imported
        # if we not running on Lucid/10.04 and const.USB_MEDIA_MOUNT_POINT does not exist then create it
        # and make its permissions correct with regard to access control list
        # code in the UI (file_util) depends upon it existing
        print 'USB mount point: %s' % const.USB_MEDIA_MOUNT_POINT
        if const.DEBIAN_VERSION != 'squeeze/sid' and (not os.path.isdir(const.USB_MEDIA_MOUNT_POINT)):
            print 'creating directory: %s' % const.USB_MEDIA_MOUNT_POINT
            # need to make it
            cmd = 'sudo mkdir %s' % const.USB_MEDIA_MOUNT_POINT
            result = mgr.run_cmd(cmd)
            # fix permissions
            cmd = 'sudo chmod 700 %s' % const.USB_MEDIA_MOUNT_POINT
            # set extended access control needed
            # getfacl /media/operator
            # file: operator/
            # owner: root
            # group: root
            # user::rwx
            # user:operator:r-x
            # group::---
            # mask::r-x
            # other::---
            result = mgr.run_cmd(cmd)
            cmd = 'sudo setfacl -m u:%s:rx %s' % (os.getenv('USER'), const.USB_MEDIA_MOUNT_POINT)
            result = mgr.run_cmd(cmd)

        # RAM in this box might have changed so update the control group definitions just in case.
        cmd = 'sudo python %s' % os.path.join(SCRIPTS_DIR, 'update-cgconfig.py')
        mgr.run_cmd(cmd)

        ret_val = mgr.main_loop()

    except Exception:
        ex = sys.exc_info()
        traceback_txt = "".join(traceback.format_exception(*ex))
        print 'pathpilotmanager exception: {}'.format(traceback_txt)

        # wrap this just in case something dies trying to display the popup and that hides the root cause exception...
        try:
            mgr.kill_splash()
            with popupdlg.ok_cancel_popup(None, 'Fatal exception starting PathPilot, shutting down controller.  Exception: {}'.format(traceback_txt), cancel=False, checkbox=False) as dialog:
                pass
        except:
            pass

        # Re-raising the exception this way preserves the original call stack so things are logged perfectly
        # with the root cause of the exception easily logged vs. the line number of this raise.
        raise ex[0], ex[1], ex[2]

    sys.exit(ret_val)
