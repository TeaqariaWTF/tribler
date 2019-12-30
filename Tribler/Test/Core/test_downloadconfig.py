
from configobj import ConfigObjError

from nose.tools import raises

from Tribler.Core.Config.download_config import DownloadConfig, get_default_dest_dir
from Tribler.Core.Utilities import path_util
from Tribler.Core.Utilities.path_util import Path
from Tribler.Core.simpledefs import DLMODE_VOD
from Tribler.Test.Core.base_test import TriblerCoreTest


class TestConfigParser(TriblerCoreTest):

    CONFIG_FILES_DIR = Path(__file__).parent / "data" / "config_files"

    def test_downloadconfig(self):
        dlcfg = DownloadConfig()

        self.assertIsInstance(dlcfg.get_dest_dir(), path_util.Path)
        dlcfg.set_dest_dir(self.session_base_dir)
        self.assertEqual(dlcfg.get_dest_dir(), self.session_base_dir)

        dlcfg.set_mode(1)
        self.assertEqual(dlcfg.get_mode(), 1)

        dlcfg.set_hops(4)
        self.assertEqual(dlcfg.get_hops(), 4)

        dlcfg.set_safe_seeding(False)
        self.assertFalse(dlcfg.get_safe_seeding())

        dlcfg.set_selected_files([1])
        self.assertEqual(dlcfg.get_selected_files(), [1])

        dlcfg.set_channel_download(True)
        self.assertTrue(dlcfg.get_channel_download())

        dlcfg.set_add_to_channel(True)
        self.assertTrue(dlcfg.get_add_to_channel())

        dlcfg.set_bootstrap_download(True)
        self.assertTrue(dlcfg.get_bootstrap_download())

    @raises(ValueError)
    def test_downloadconfig_set_vod_multiple_files(self):
        dlcfg = DownloadConfig()
        dlcfg.set_mode(DLMODE_VOD)
        dlcfg.set_selected_files(["foo.txt", "bar.txt"])


    def test_downloadconfig_copy(self):
        dlcfg = DownloadConfig()
        dlcfg_copy = dlcfg.copy()

        self.assertEqual(dlcfg_copy.get_hops(), 0)

    def test_download_save_load(self):
        dlcfg = DownloadConfig()
        file_path = self.session_base_dir / "downloadconfig.conf"
        dlcfg.write(file_path)
        dlcfg.load(file_path)

    @raises(ConfigObjError)
    def test_download_load_corrupt(self):
        dlcfg = DownloadConfig()
        dlcfg.load(self.CONFIG_FILES_DIR / "corrupt_download_config.conf")

    def test_get_default_dest_dir(self):
        self.assertIsInstance(get_default_dest_dir(), path_util.Path)

    def test_default_download_config_load(self):
        with open(self.session_base_dir / "dlconfig.conf", 'wb') as conf_file:
            conf_file.write(b"[Tribler]\nabc=def")

        dcfg = DownloadConfig.load(self.session_base_dir / "dlconfig.conf")
        self.assertEqual(dcfg.config['Tribler']['abc'], 'def')

    def test_user_stopped(self):
        dlcfg = DownloadConfig()
        dlcfg.set_user_stopped(False)
        self.assertFalse(dlcfg.get_user_stopped())

        dlcfg.set_user_stopped(True)
        self.assertTrue(dlcfg.get_user_stopped())
