import unittest

from youtube_mp3 import quality_to_yt_dlp, validate_youtube_url


class ValidationTests(unittest.TestCase):
    def test_accepts_common_youtube_urls(self):
        urls = (
            "https://www.youtube.com/watch?v=abc123",
            "https://youtu.be/abc123",
            "https://music.youtube.com/watch?v=abc123",
        )
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(validate_youtube_url(url), url)

    def test_rejects_non_youtube_urls(self):
        for url in ("", "not a url", "https://example.com/video", "file:///tmp/test"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    validate_youtube_url(url)

    def test_quality_mapping(self):
        self.assertEqual(quality_to_yt_dlp("320 kbps"), "320")
        self.assertEqual(quality_to_yt_dlp("128 kbps"), "128")


if __name__ == "__main__":
    unittest.main()
