from random import randint, choice

from p115client import P115Client, check_response

from app.core.cache import cached


class UserAgentUtils:
    """
    User-Agent 生成工具
    """

    @staticmethod
    @cached(
        region="p115strmhelper_util_user_agent_u115_ios", ttl=60 * 60, skip_none=True
    )
    def generate_u115_ios() -> str:
        """
        各段含义与生成规则：

        - iOS 版本：iPhone OS {major}_{minor}，从常见版本中随机（如 15_0～18_1）
        - Build：Mobile/{build}，Apple 风格 build 号（数字+字母+3 位数字，如 15E148、21A258）
        - AppleWebKit：与 iOS 大版本对应的 WebKit 版本（如 605.1.15）

        :return: 完整的 User-Agent 字符串
        """
        try:
            resp = P115Client.app_version_list2()
            check_response(resp)
            udown_version = resp["data"]["iOS-iPhone"]["version_code"]
            wangpan_version = resp["data"]["115wangpan_iOS"]["version_code"]
        except Exception:
            udown_version = "37.0.7"
            wangpan_version = "36.2.20"
        ios_versions = [
            "15_0",
            "15_1",
            "15_2",
            "15_3",
            "15_4",
            "15_5",
            "15_6",
            "15_7",
            "15_8",
            "16_0",
            "16_1",
            "16_2",
            "16_3",
            "16_4",
            "16_5",
            "16_6",
            "16_7",
            "17_0",
            "17_1",
            "17_2",
            "17_3",
            "17_4",
            "17_5",
            "18_0",
            "18_1",
        ]
        build_num = randint(15, 21)
        build_letter = choice("ABCDE")
        build_tail = randint(100, 999)
        build = f"{build_num}{build_letter}{build_tail}"
        webkit = "605.1.15"
        os_ver = choice(ios_versions)
        client = choice(
            [
                f"115wangpan_ios/{wangpan_version}",
                f"UDown/{udown_version}",
            ]
        )
        return (
            f"Mozilla/5.0 (iPhone; CPU iPhone OS {os_ver} like Mac OS X) "
            f"AppleWebKit/{webkit} (KHTML, like Gecko) Mobile/{build} {client}"
        )
