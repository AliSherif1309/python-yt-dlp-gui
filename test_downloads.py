import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import yt_downloader_gui as app


class DownloadTests(unittest.TestCase):
    def make_app(self):
        obj = app.YouTubeDownloaderApp.__new__(app.YouTubeDownloaderApp)
        obj.root = SimpleNamespace(after=lambda delay, callback: callback())
        obj.progress_var = Mock()
        obj.update_status = Mock()
        obj.update_overall_progress = Mock()
        obj.reset_ui_after_download = lambda: setattr(obj, 'cancelled', False)
        return obj

    def test_cancellation_survives_reset(self):
        obj = self.make_app()
        def cancel(urls):
            obj.cancelled = True
            raise app.yt_dlp.utils.DownloadCancelled('cancelled')
        downloader = Mock()
        downloader.download.side_effect = cancel
        with patch.object(app.yt_dlp, 'YoutubeDL', return_value=downloader) as factory, patch.object(app, 'messagebox') as dialogs:
            obj.download_content(['https://example.org/video'], '.', 'video', False, 'mp4')
        dialogs.showwarning.assert_called_once()
        self.assertEqual(dialogs.showwarning.call_args.args[0], 'Cancelled')
        dialogs.showinfo.assert_not_called()
        self.assertFalse(factory.call_args.args[0]['nocheckcertificate'])

    def test_nonzero_exit_is_failure(self):
        obj = self.make_app()
        downloader = Mock()
        downloader.download.return_value = 1
        with patch.object(app.yt_dlp, 'YoutubeDL', return_value=downloader), patch.object(app, 'messagebox') as dialogs:
            obj.download_content(['https://example.org/video'], '.', 'video', False, 'mp4')
        self.assertEqual(dialogs.showwarning.call_args.args[0], 'Finished with Errors')

    def test_success_is_reported(self):
        obj = self.make_app()
        downloader = Mock()
        downloader.download.return_value = 0
        with patch.object(app.yt_dlp, 'YoutubeDL', return_value=downloader), patch.object(app, 'messagebox') as dialogs:
            obj.download_content(['https://example.org/video'], '.', 'audio', False, None)
        dialogs.showinfo.assert_called_once()


if __name__ == '__main__':
    unittest.main()
