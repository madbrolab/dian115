import json
import sys
import unittest
from pathlib import Path

utils_dir = Path(__file__).resolve().parent.parent / "utils"
sys.path.insert(0, str(utils_dir))

from webhook import WebhookUtils


class TestParseItemPaths(unittest.TestCase):
    """
    测试 WebhookUtils.parse_item_paths_from_description
    """

    def test_parse_single_item_path(self):
        """测试解析单个 Item Path"""
        description = """Item Name:
狂怒沙暴

Item Path:
/data2/test/狂怒沙暴 (2023)/狂怒沙暴 (2023) - 1080p.strm

Mount Paths:
http://192.168.31.99:23000/api/v1/plugin/P115StrmHelper/redirect_url?pickcode=cg04ctinkn3aidbzc"""

        result = WebhookUtils.parse_item_paths_from_description(description)
        expected = ["/data2/test/狂怒沙暴 (2023)/狂怒沙暴 (2023) - 1080p.strm"]
        self.assertEqual(result, expected)

    def test_parse_multiple_item_paths(self):
        """测试解析多个 Item Path（多版本剧集）"""
        description = """Item Name:
狂怒沙暴

Item Path:
/data2/test/狂怒沙暴 (2023)/狂怒沙暴 (2023) - 1080p.strm
/data2/test/狂怒沙暴 (2023)/狂怒沙暴 (2023) - 720p.strm

Mount Paths:
http://192.168.31.99:23000/api/v1/plugin/P115StrmHelper/redirect_url?pickcode=cg04ctinkn3aidbzc"""

        result = WebhookUtils.parse_item_paths_from_description(description)
        expected = [
            "/data2/test/狂怒沙暴 (2023)/狂怒沙暴 (2023) - 1080p.strm",
            "/data2/test/狂怒沙暴 (2023)/狂怒沙暴 (2023) - 720p.strm",
        ]
        self.assertEqual(result, expected)

    def test_parse_item_path_on_same_line(self):
        """测试 Item Path 在同一行的情况"""
        description = """Item Name: 狂怒沙暴
Item Path: /data2/test/狂怒沙暴 (2023)/狂怒沙暴 (2023) - 1080p.strm
Mount Paths: http://example.com"""

        result = WebhookUtils.parse_item_paths_from_description(description)
        expected = ["/data2/test/狂怒沙暴 (2023)/狂怒沙暴 (2023) - 1080p.strm"]
        self.assertEqual(result, expected)

    def test_parse_empty_description(self):
        """测试空 Description"""
        result = WebhookUtils.parse_item_paths_from_description("")
        self.assertEqual(result, [])

    def test_parse_no_item_path(self):
        """测试没有 Item Path 的情况"""
        description = """Item Name: 狂怒沙暴
Mount Paths: http://example.com"""

        result = WebhookUtils.parse_item_paths_from_description(description)
        self.assertEqual(result, [])

    def test_parse_with_windows_path(self):
        """测试 Windows 路径格式"""
        description = """Item Path:
C:\\data\\test\\movie.strm
D:\\data\\test\\movie2.strm"""

        result = WebhookUtils.parse_item_paths_from_description(description)
        expected = ["C:\\data\\test\\movie.strm", "D:\\data\\test\\movie2.strm"]
        self.assertEqual(result, expected)

    def test_parse_with_relative_path(self):
        """测试相对路径"""
        description = """Item Path:
./data/test/movie.strm
../data/test/movie2.strm"""

        result = WebhookUtils.parse_item_paths_from_description(description)
        expected = ["./data/test/movie.strm", "../data/test/movie2.strm"]
        self.assertEqual(result, expected)

    def test_parse_ignore_urls(self):
        """测试忽略 URL"""
        description = """Item Path:
/data2/test/movie.strm
http://example.com/path/to/file
https://example.com/path/to/file
/data2/test/movie2.strm"""

        result = WebhookUtils.parse_item_paths_from_description(description)
        expected = ["/data2/test/movie.strm", "/data2/test/movie2.strm"]
        self.assertEqual(result, expected)

    def test_parse_with_extra_whitespace(self):
        """测试包含额外空白字符的情况"""
        description = """Item Path:
    /data2/test/movie.strm

    /data2/test/movie2.strm
    """

        result = WebhookUtils.parse_item_paths_from_description(description)
        expected = ["/data2/test/movie.strm", "/data2/test/movie2.strm"]
        self.assertEqual(result, expected)

    def test_parse_complex_description(self):
        """测试复杂的 Description 格式"""
        description = """Item Name:
狂怒沙暴

Item Path:
/data2/test/狂怒沙暴 (2023)/狂怒沙暴 (2023) - 1080p.strm
/data2/test/狂怒沙暴 (2023)/狂怒沙暴 (2023) - 720p.strm
/data2/test/狂怒沙暴 (2023)/狂怒沙暴 (2023) - 4K.strm

Mount Paths:
http://192.168.31.99:23000/api/v1/plugin/P115StrmHelper/redirect_url?pickcode=cg04ctinkn3aidbzc

Other Info:
Some other information here"""

        result = WebhookUtils.parse_item_paths_from_description(description)
        expected = [
            "/data2/test/狂怒沙暴 (2023)/狂怒沙暴 (2023) - 1080p.strm",
            "/data2/test/狂怒沙暴 (2023)/狂怒沙暴 (2023) - 720p.strm",
            "/data2/test/狂怒沙暴 (2023)/狂怒沙暴 (2023) - 4K.strm",
        ]
        self.assertEqual(result, expected)

    def test_parse_with_real_json_data(self):
        """使用真实的 webhook_delete.json 数据测试"""
        json_file = (
            Path(__file__).resolve().parent.parent.parent.parent
            / "dev"
            / "p115strmhelper"
            / "webhook_delete.json"
        )

        if not json_file.exists():
            self.skipTest(f"测试文件不存在: {json_file}")

        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        description = data.get("Description", "")
        result = WebhookUtils.parse_item_paths_from_description(description)

        expected = [
            "/data2/test/狂怒沙暴 (2023)/狂怒沙暴 (2023) - 1080p.strm",
            "/data2/test/狂怒沙暴 (2023)/狂怒沙暴 (2023) - 720p.strm",
        ]

        self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
