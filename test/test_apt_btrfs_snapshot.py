#!/usr/bin/python

try:
    from StringIO import StringIO
    StringIO  # pyflakes
except ImportError:
    from io import StringIO
import datetime
import mock
import os
import sys
import unittest

from apt_btrfs_snapshot import (
    AptBtrfsSnapshot,
)

sys.path.insert(0, "..")
sys.path.insert(0, ".")


class TestFstab(unittest.TestCase):

    def setUp(self):
        self.testdir = os.path.dirname(os.path.abspath(__file__))

    @mock.patch('apt_btrfs_snapshot.find_executable')
    def test_fstab_detect_snapshot(self, mock_commands):
        # Using python-mock 0.7 style, for precise compatibility
        mock_commands.side_effect = lambda f: f == 'btrfs'
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab"))
        self.assertTrue(apt_btrfs.snapshots_supported())
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab.no-btrfs"))
        self.assertFalse(apt_btrfs.snapshots_supported())
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab.bug806065"))
        self.assertFalse(apt_btrfs.snapshots_supported())
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab.bug872145"))
        self.assertTrue(apt_btrfs.snapshots_supported())

    def test_fstab_get_uuid(self):
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab"))
        self.assertEqual(apt_btrfs._uuid_for_mountpoint("/"),
                         "UUID=fe63f598-1906-478e-acc7-f74740e78d1f")

    @mock.patch('apt_btrfs_snapshot.LowLevelCommands')
    def test_mount_btrfs_root_volume(self, mock_commands):
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab"))
        mock_commands.mount.return_value = True
        mock_commands.umount.return_value = True
        mp = apt_btrfs.mount_btrfs_root_volume()
        self.assertTrue("apt-btrfs-snapshot-mp-" in mp)
        self.assertTrue(apt_btrfs.umount_btrfs_root_volume())
        self.assertFalse(os.path.exists(mp))

    @mock.patch('apt_btrfs_snapshot.LowLevelCommands')
    def test_btrfs_create_snapshot(self, mock_commands):
        # setup mock
        mock_commands.btrfs_subvolume_snapshot.return_value = True
        mock_commands.mount.return_value = True
        mock_commands.umount.return_value = True
        # do it
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab"))
        res = apt_btrfs.create_btrfs_root_snapshot()
        # check results
        self.assertTrue(apt_btrfs.commands.mount.called)
        self.assertTrue(apt_btrfs.commands.umount.called)
        self.assertTrue(res)
        self.assertTrue(apt_btrfs.commands.btrfs_subvolume_snapshot.called)
        (args, kwargs) = apt_btrfs.commands.btrfs_subvolume_snapshot.call_args
        self.assertTrue(len(args), 2)
        self.assertTrue(args[0].endswith("@"))
        self.assertTrue("@apt-snapshot-" in args[1])
        # again with a additional prefix for the snapshot
        res = apt_btrfs.create_btrfs_root_snapshot("release-upgrade-natty-")
        (args, kwargs) = apt_btrfs.commands.btrfs_subvolume_snapshot.call_args
        self.assertTrue("@apt-snapshot-release-upgrade-natty-" in args[1])

    @mock.patch('apt_btrfs_snapshot.LowLevelCommands')
    def test_btrfs_delete_snapshot(self, mock_commands):
        # setup mock
        mock_commands.btrfs_delete_snapshot.return_value = True
        mock_commands.mount.return_value = True
        mock_commands.umount.return_value = True
        # do it
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab"))
        res = apt_btrfs.delete_snapshot("lala")
        self.assertTrue(res)
        self.assertTrue(apt_btrfs.commands.mount.called)
        self.assertTrue(apt_btrfs.commands.umount.called)
        self.assertTrue(apt_btrfs.commands.btrfs_delete_snapshot.called)
        (args, kwargs) = apt_btrfs.commands.btrfs_delete_snapshot.call_args
        self.assertTrue(args[0].endswith("/lala"))

    def test_parser_older_than_to_datetime(self):
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab"))
        t = apt_btrfs._parse_older_than_to_datetime("5d")
        self.assertTrue(t <= datetime.datetime.now()-datetime.timedelta(5))

    def test_parser_snapshot_to_datetime(self):
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab"))
        e = "@apt-snapshot-2017-12-15_11:26:24"
        t_parsed = apt_btrfs._parse_snapshot_to_datetime(e)
        t_expected = datetime.datetime(2017, 12, 15, 11, 26, 24)
        self.assertEqual(t_parsed, t_expected)


if __name__ == "__main__":
    unittest.main()
