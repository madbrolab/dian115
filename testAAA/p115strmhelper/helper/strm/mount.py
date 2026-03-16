from pathlib import Path
from typing import Optional, Dict, Any, List, Set

from app.log import logger

from ...core.config import configer


class ProcessedRule:
    """
    预处理后的规则，用于高效匹配
    """

    def __init__(self, rule: Dict[str, Any]):
        extensions = rule.get("extensions", [])
        if extensions:
            self.extensions: Set[str] = {
                ext.lstrip(".").lower() for ext in extensions if ext
            }
        else:
            self.extensions: Set[str] = set()

        names = rule.get("names", [])
        if names:
            self.names: List[str] = [name.lower() for name in names if name]
        else:
            self.names: List[str] = []

        paths = rule.get("paths", [])
        if paths:
            self.paths: List[str] = [
                path.replace("\\", "/").strip("/") for path in paths if path
            ]
        else:
            self.paths: List[str] = []

        self.is_valid = bool(self.extensions or self.names or self.paths)


class FuseStrmTakeoverMatcher:
    """
    FUSE 挂载模式下的 STRM 内容接管匹配器
    """

    def __init__(self):
        self.mount_dir: Optional[str] = None
        self.mount_dir_rstrip: str = ""
        self.processed_rules: List[ProcessedRule] = []
        self._reload_config()

    def _reload_config(self):
        """
        重新加载配置并预处理规则
        """
        self.mount_dir = configer.fuse_strm_mount_dir
        rules = configer.fuse_strm_takeover_rules or []

        if self.mount_dir:
            self.mount_dir_rstrip = self.mount_dir.rstrip("/")
        else:
            self.mount_dir_rstrip = ""

        self.processed_rules = [ProcessedRule(rule) for rule in rules]
        self.processed_rules = [rule for rule in self.processed_rules if rule.is_valid]

    def match(
        self, file_name: str, file_path: str, file_ext: Optional[str] = None
    ) -> Optional[str]:
        """
        匹配文件是否应该被接管，如果匹配则返回生成的 STRM 内容

        :param file_name: 文件名称
        :param file_path: 文件网盘路径
        :param file_ext: 文件后缀（可选，如果不提供则从 file_name 提取）

        :return: 如果匹配则返回 STRM 内容路径，否则返回 None
        """
        if not self.processed_rules:
            return None

        if not self.mount_dir_rstrip:
            return None

        if file_ext is None:
            file_ext = Path(file_name).suffix.lstrip(".").lower()
        else:
            file_ext = file_ext.lstrip(".").lower()

        file_name_lower = file_name.lower()

        normalized_file_path = file_path.replace("\\", "/")

        for processed_rule in self.processed_rules:
            if self._match_processed_rule(
                processed_rule, file_name_lower, normalized_file_path, file_ext
            ):
                return self._generate_strm_content_fast(normalized_file_path)

        return None

    @staticmethod
    def _match_processed_rule(
        rule: ProcessedRule,
        file_name_lower: str,
        normalized_file_path: str,
        file_ext: str,
    ) -> bool:
        """
        匹配预处理后的规则

        :param rule: 预处理后的规则
        :param file_name_lower: 小写的文件名称
        :param normalized_file_path: 标准化后的文件路径
        :param file_ext: 小写的文件后缀

        :return: 是否匹配
        """
        if rule.extensions:
            if file_ext not in rule.extensions:
                return False

        if rule.names:
            if not any(name in file_name_lower for name in rule.names):
                return False

        if rule.paths:
            if not any(path in normalized_file_path for path in rule.paths):
                return False

        return True

    def _generate_strm_content_fast(self, normalized_file_path: str) -> str:
        """
        快速生成 STRM 内容

        :param normalized_file_path: 已标准化的文件路径

        :return: STRM 内容路径
        """
        path_stripped = normalized_file_path.strip("/")
        return f"{self.mount_dir_rstrip}/{path_stripped}"


_fuse_strm_takeover_matcher: Optional[FuseStrmTakeoverMatcher] = None
_config_version: int = 0


def get_fuse_strm_takeover_matcher() -> Optional[FuseStrmTakeoverMatcher]:
    """
    获取 FUSE STRM 接管匹配器实例

    :return: 匹配器实例，如果未启用则返回 None
    """
    global _fuse_strm_takeover_matcher, _config_version

    if not configer.fuse_strm_takeover_enabled:
        _fuse_strm_takeover_matcher = None
        return None

    current_config_hash = hash(
        (
            configer.fuse_strm_mount_dir,
            tuple(
                tuple(rule.get("extensions", []))
                + tuple(rule.get("names", []))
                + tuple(rule.get("paths", []))
                for rule in (configer.fuse_strm_takeover_rules or [])
            ),
        )
    )

    if _fuse_strm_takeover_matcher is None or current_config_hash != _config_version:
        _fuse_strm_takeover_matcher = FuseStrmTakeoverMatcher()
        _config_version = current_config_hash

    return _fuse_strm_takeover_matcher


def match_fuse_strm_takeover(
    file_name: str, file_path: str, file_ext: Optional[str] = None
) -> Optional[str]:
    """
    匹配文件是否应该被 FUSE STRM 接管

    :param file_name: 文件名称
    :param file_path: 文件网盘路径
    :param file_ext: 文件后缀（可选）
    :return: 如果匹配则返回 STRM 内容路径，否则返回 None
    """
    if not configer.fuse_strm_takeover_enabled:
        return None

    matcher = get_fuse_strm_takeover_matcher()
    if matcher is None:
        return None

    try:
        return matcher.match(file_name, file_path, file_ext)
    except Exception as e:
        logger.error(f"【FUSE STRM 接管】匹配失败: {e}", exc_info=True)
        return None
