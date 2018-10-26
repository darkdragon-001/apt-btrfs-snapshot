# Copyright (C) 2011 Canonical
#
# Author:
#  Michael Vogt
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; version 3.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

from __future__ import print_function, unicode_literals

import datetime
import os
import subprocess
import tempfile

from distutils.spawn import find_executable

from gettext import gettext as _


class AptBtrfsSnapshotError(Exception):
    pass


class AptBtrfsNotSupportedError(AptBtrfsSnapshotError):
    pass


class FstabEntry(object):
    """ a single fstab entry line """
    @classmethod
    def from_line(cls, line):
        # split up
        args = line.partition("#")[0].split()
        # use only the first 7 args and ignore anything after them, mount
        # seems to do the same, see bug #873411 comment #7
        return FstabEntry(*args[0:6])

    def __init__(self, fs_spec, mountpoint, fstype, options, dump=0, passno=0):
        # uuid or device
        self.fs_spec = fs_spec
        self.mountpoint = mountpoint
        self.fstype = fstype
        self.options = options
        self.dump = dump
        self.passno = passno

    def __repr__(self):
        return "<FstabEntry '%s' '%s' '%s' '%s' '%s' '%s'>" % (
            self.fs_spec, self.mountpoint, self.fstype,
            self.options, self.dump, self.passno)


class Fstab(list):
    """ a list of FstabEntry items """
    def __init__(self, fstab="/etc/fstab"):
        super(Fstab, self).__init__()

        with open(fstab) as fstab_file:
            for line in (l.strip() for l in fstab_file):
                if line == "" or line.startswith("#"):
                    continue
                try:
                    entry = FstabEntry.from_line(line)
                except ValueError:
                    continue
                self.append(entry)


class LowLevelCommands(object):
    """ lowlevel commands invoked to perform various tasks like
        interact with mount and btrfs tools
    """
    def mount(self, fs_spec, mountpoint):
        ret = subprocess.call(["mount", fs_spec, mountpoint])
        return ret == 0

    def umount(self, mountpoint):
        ret = subprocess.call(["umount", mountpoint])
        return ret == 0

    def btrfs_subvolume_snapshot(self, source, dest):
        ret = subprocess.call(["btrfs", "subvolume", "snapshot", "-r",
                               source, dest])
        return ret == 0

    def btrfs_delete_snapshot(self, snapshot):
        ret = subprocess.call(["btrfs", "subvolume", "delete", snapshot])
        return ret == 0


class AptBtrfsSnapshot(object):
    """ the high level object that interacts with the snapshot system """

    # normal snapshot
    SNAP_PREFIX = "@apt-snapshot-"
    # backname when changing
    BACKUP_PREFIX = SNAP_PREFIX + "old-root-"

    def __init__(self, fstab="/etc/fstab"):
        self.fstab = Fstab(fstab)
        self.commands = LowLevelCommands()
        self._btrfs_root_mountpoint = None

    def snapshots_supported(self):
        """ verify that the system supports apt btrfs snapshots
            by checking if the right fs layout is used etc
        """
        if not (find_executable("btrfs")):
            return False
        # check the fstab
        entry = self._get_supported_btrfs_root_fstab_entry()
        return entry is not None

    def _get_supported_btrfs_root_fstab_entry(self):
        """ return the supported btrfs root FstabEntry or None """
        for entry in self.fstab:
            if (
                    entry.mountpoint == "/" and
                    entry.fstype == "btrfs" and
                    "subvol=@" in entry.options):
                return entry
        return None

    def _uuid_for_mountpoint(self, mountpoint):
        """ return the device or UUID for the given mountpoint """
        for entry in self.fstab:
            if entry.mountpoint == mountpoint:
                return entry.fs_spec
        return None

    def mount_btrfs_root_volume(self):
        uuid = self._uuid_for_mountpoint("/")
        mountpoint = tempfile.mkdtemp(prefix="apt-btrfs-snapshot-mp-")
        if not self.commands.mount(uuid, mountpoint):
            return None
        self._btrfs_root_mountpoint = mountpoint
        return self._btrfs_root_mountpoint

    def umount_btrfs_root_volume(self):
        res = self.commands.umount(self._btrfs_root_mountpoint)
        os.rmdir(self._btrfs_root_mountpoint)
        self._btrfs_root_mountpoint = None
        return res

    def _get_now_str(self):
        return datetime.datetime.now().replace(microsecond=0).isoformat(
            str('_'))

    def create_btrfs_root_snapshot(self, additional_prefix=""):
        mp = self.mount_btrfs_root_volume()
        snap_id = self._get_now_str()
        source = os.path.join(mp, "@")
        target = os.path.join(mp, self.SNAP_PREFIX + additional_prefix +
                              snap_id)

        if os.path.exists(target):
            print(_("INFO: snapshot directory '%s' already exists, "
                    "not creating duplicate") % (target,))
            return True
        else:
            res = self.commands.btrfs_subvolume_snapshot(source, target)
            self.umount_btrfs_root_volume()
            return res

    def _parse_snapshot_to_datetime(self, snapshot):
        """ extract creation time from snapshot name
        """
        if not snapshot.startswith(self.SNAP_PREFIX):
            raise Exception("Invalid snapshot")

        # get date substring
        if len(snapshot) < (len(self.SNAP_PREFIX)+19):
            raise Exception("Invalid snapshot")
        timestamp = snapshot[-19:]  # timestamp is suffix

        # parse date
        try:
            format = '%Y-%m-%d_%H:%M:%S'
            timestamp = datetime.datetime.strptime(timestamp, format)
        except ValueError as err:
            raise Exception("Invalid snapshot: "+str(err))

        return timestamp

    def get_btrfs_root_snapshots_list(self, older_than=None):
        """ get the list of available snapshot
            Only includes snapshots older than older_than (datetime object)
        """
        snapshots = []
        # if there is no older than, interpret that as "now"
        if older_than is None:
            older_than = datetime.datetime.now()
        mp = self.mount_btrfs_root_volume()
        for e in os.listdir(mp):
            if e.startswith(self.SNAP_PREFIX):
                ctime = self._parse_snapshot_to_datetime(e)
                if ctime < older_than:
                    snapshots.append(e)
        self.umount_btrfs_root_volume()
        return snapshots

    def print_btrfs_root_snapshots(self):
        print("Available snapshots:")
        print("  \n".join(self.get_btrfs_root_snapshots_list()))
        return True

    def _parse_older_than_to_datetime(self, timefmt):
        now = datetime.datetime.now()
        if not timefmt.endswith("d"):
            raise Exception("Please specify time in days (e.g. 10d)")
        days = int(timefmt[:-1])
        return now - datetime.timedelta(days=days)

    def print_btrfs_root_snapshots_older_than(self, timefmt):
        older_than_datetime = self._parse_older_than_to_datetime(timefmt)
        print("Available snapshots older than '%s':" % timefmt)
        print("  \n".join(self.get_btrfs_root_snapshots_list(
            older_than=older_than_datetime)))
        return True

    def clean_btrfs_root_snapshots_older_than(self, timefmt):
        res = True
        older_than_datetime = self._parse_older_than_to_datetime(timefmt)
        for snap in self.get_btrfs_root_snapshots_list(
                older_than=older_than_datetime):
            res &= self.delete_snapshot(snap)
        return res

    def command_set_default(self, snapshot_name):
        res = self.set_default(snapshot_name)
        return res

    def set_default(self, snapshot_name, backup=True):
        """ set new default """
        mp = self.mount_btrfs_root_volume()
        new_root = os.path.join(mp, snapshot_name)
        if (
                os.path.isdir(new_root) and
                snapshot_name.startswith(self.SNAP_PREFIX)):
            default_root = os.path.join(mp, "@")
            backup = os.path.join(mp, self.BACKUP_PREFIX + self._get_now_str())
            os.rename(default_root, backup)
            os.rename(new_root, default_root)
            print("Default changed to %s, please reboot for changes to take "
                  "effect." % snapshot_name)
        else:
            print("You have selected an invalid snapshot. Please make sure "
                  "that it exists, and that it is not \"@\".")
        self.umount_btrfs_root_volume()
        return True

    def delete_snapshot(self, snapshot_name):
        mp = self.mount_btrfs_root_volume()
        res = self.commands.btrfs_delete_snapshot(
            os.path.join(mp, snapshot_name))
        self.umount_btrfs_root_volume()
        return res
