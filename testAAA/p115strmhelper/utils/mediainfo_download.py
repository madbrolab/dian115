__all__ = ["MediainfoDownloadMiddleware"]


from ahocorasick import Automaton


class MediainfoDownloadMiddleware:
    """
    媒体信息黑白名单处理
    """

    @staticmethod
    def should_download(
        filename: str,
        blacklist_automaton: Automaton,
        whitelist_automaton: Automaton,
    ) -> tuple[str, bool]:
        """
        判断文件是否能下载总规则
        """
        # 1. 判断是否在白名单
        whitelist_msg, whitelist_status = MediainfoDownloadMiddleware.not_whitelist_key(
            filename, whitelist_automaton
        )
        if not whitelist_status:
            return whitelist_msg, whitelist_status

        # 1. 判断是否在黑名单
        blacklist_msg, blacklist_status = MediainfoDownloadMiddleware.not_blacklist_key(
            filename, blacklist_automaton
        )
        if not blacklist_status:
            return blacklist_msg, blacklist_status

        return "", True

    @staticmethod
    def not_blacklist_key(filename, blacklist_automaton: Automaton) -> tuple[str, bool]:
        """
        使用 Aho-Corasick 自动机判断文件名是否包含黑名单中的任何关键词
        """
        if not blacklist_automaton:
            return "", True
        lower_filename = filename.lower()
        try:
            _, (original_keyword, _) = next(blacklist_automaton.iter(lower_filename))
            return f"匹配到黑名单关键词 {original_keyword}", False
        except StopIteration:
            return "", True

    @staticmethod
    def not_whitelist_key(filename, whitelist_automaton: Automaton) -> tuple[str, bool]:
        """
        使用 Aho-Corasick 自动机判断文件名是否包含白名单中的任何关键词
        """
        if not whitelist_automaton:
            return "", True
        lower_filename = filename.lower()
        try:
            _, (original_keyword, _) = next(whitelist_automaton.iter(lower_filename))
            return f"匹配到白名单关键词 {original_keyword}", True
        except StopIteration:
            return f"{filename} 不在生成白名单内", False
