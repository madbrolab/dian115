__all__ = [
    "StrmUrlTemplateResolver",
    "StrmFilenameTemplateResolver",
    "StrmUrlGetter",
    "StrmGenerater",
]


from pathlib import Path
from typing import Optional, Dict, Any, Union
from urllib.parse import quote

from app.log import logger

from ahocorasick import Automaton
from p115pickcode import to_id
from jinja2 import Template, Environment, select_autoescape
from jinja2.exceptions import TemplateError

from ..core.config import configer
from ..schemas.size import CompareMinSize


class StrmUrlTemplateResolver:
    """
    基于 Jinja2 的 STRM URL 模板解析器
    """

    def __init__(
        self,
        base_template: Optional[str] = None,
        custom_rules: Optional[str] = None,
        auto_escape: bool = False,
    ):
        """
        初始化模板解析器

        :param base_template: 基础 Jinja2 模板字符串
        :param custom_rules: 扩展名特定模板规则，格式：ext1,ext2 => template
        :param auto_escape: 是否自动转义
        """
        self.env = Environment(
            autoescape=select_autoescape(["html", "xml"]) if auto_escape else False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

        self._register_filters()

        self.base_template = None
        if base_template:
            try:
                self.base_template = self.env.from_string(base_template)
            except TemplateError as e:
                logger.error(f"【STRM URL 模板】基础模板解析失败: {e}")
                raise

        self.extension_templates: Dict[str, Template] = {}
        if custom_rules:
            self._parse_custom_rules(custom_rules)

    def _register_filters(self):
        """
        注册自定义过滤器
        """

        def urlencode_filter(value: str) -> str:
            """
            URL 编码过滤器
            """
            if not value:
                return ""
            return quote(str(value), safe="")

        def path_encode_filter(value: str) -> str:
            """
            路径编码过滤器（保留斜杠）
            """
            if not value:
                return ""
            return quote(str(value), safe="/")

        def upper_filter(value: str) -> str:
            """
            转大写
            """
            return str(value).upper() if value else ""

        def lower_filter(value: str) -> str:
            """
            转小写
            """
            return str(value).lower() if value else ""

        self.env.filters["urlencode"] = urlencode_filter
        self.env.filters["path_encode"] = path_encode_filter
        self.env.filters["upper"] = upper_filter
        self.env.filters["lower"] = lower_filter

    def _parse_custom_rules(self, config_str: str):
        """
        解析扩展名特定模板规则

        :param config_str: 规则字符串，格式：ext1,ext2 => template（每行一个）
        """
        for rule in config_str.strip().split("\n"):
            rule = rule.strip()
            if not rule or "=>" not in rule:
                continue

            try:
                extensions_part, template_str = rule.split("=>", 1)
                extensions = [ext.strip().lower() for ext in extensions_part.split(",")]
                template_str = template_str.strip()

                if not template_str:
                    logger.warning(f"【STRM URL 模板】规则模板为空，跳过: {rule}")
                    continue

                # 解析模板
                try:
                    template = self.env.from_string(template_str)
                except TemplateError as e:
                    logger.error(
                        f"【STRM URL 模板】扩展名模板解析失败: {rule}, 错误: {e}"
                    )
                    continue

                # 为每个扩展名注册模板
                for ext in extensions:
                    if not ext:
                        continue
                    if not ext.startswith("."):
                        ext = "." + ext
                    self.extension_templates[ext] = template
                    logger.debug(
                        f"【STRM URL 模板】注册扩展名模板: {ext} => {template_str[:50]}..."
                    )

            except Exception as e:
                logger.error(f"【STRM URL 模板】解析规则失败: {rule}, 错误: {e}")
                continue

    def get_template_for_file(self, file_name: str) -> Optional[Template]:
        """
        根据文件名获取对应的模板

        :param file_name: 文件名

        :return: 匹配的模板，如果没有匹配则返回基础模板，如果都没有则返回 None
        """
        extension = Path(file_name).suffix.lower()

        if extension in self.extension_templates:
            return self.extension_templates[extension]

        return self.base_template

    def render(
        self,
        file_name: str,
        base_url: str,
        pickcode: Optional[str] = None,
        share_code: Optional[str] = None,
        receive_code: Optional[str] = None,
        file_id: Optional[str] = None,
        file_path: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional[str]:
        """
        渲染 URL 模板

        :param file_name: 文件名
        :param base_url: 基础 URL
        :param pickcode: 文件 pickcode
        :param share_code: 分享码
        :param receive_code: 提取码
        :param file_id: 文件 ID
        :param file_path: 文件网盘路径

        :return: 渲染后的 URL 字符串，如果没有可用模板则返回 None
        """
        template = self.get_template_for_file(file_name)

        if not template:
            return None

        context = {
            "base_url": base_url.rstrip("/"),
            "pickcode": pickcode or "",
            "share_code": share_code or "",
            "receive_code": receive_code or "",
            "file_id": file_id or "",
            "file_name": file_name or "",
            "file_path": file_path or "",
            **kwargs,
        }

        try:
            return template.render(**context)
        except TemplateError as e:
            logger.error(f"【STRM URL 模板】模板渲染失败: {e}, 上下文: {context}")
            raise
        except Exception as e:
            logger.error(f"【STRM URL 模板】渲染时发生未知错误: {e}")
            raise


class StrmFilenameTemplateResolver:
    """
    基于 Jinja2 的 STRM 文件名模板解析器
    """

    def __init__(
        self,
        base_template: Optional[str] = None,
        custom_rules: Optional[str] = None,
    ):
        """
        初始化模板解析器

        :param base_template: 基础 Jinja2 模板字符串
        :param custom_rules: 扩展名特定模板规则，格式：ext1,ext2 => template
        """
        self.env = Environment(
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

        self._register_filters()

        self.base_template = None
        if base_template:
            try:
                self.base_template = self.env.from_string(base_template)
            except TemplateError as e:
                logger.error(f"【STRM 文件名模板】基础模板解析失败: {e}")
                raise

        self.extension_templates: Dict[str, Template] = {}
        if custom_rules:
            self._parse_custom_rules(custom_rules)

    def _register_filters(self):
        """
        注册自定义过滤器
        """

        def upper_filter(value: str) -> str:
            """
            转大写
            """
            return str(value).upper() if value else ""

        def lower_filter(value: str) -> str:
            """
            转小写
            """
            return str(value).lower() if value else ""

        def sanitize_filter(value: str) -> str:
            """
            文件名清理过滤器（移除或替换不合法字符）
            """
            if not value:
                return ""
            invalid_chars = '<>:"/\\|?*'
            result = str(value)
            for char in invalid_chars:
                result = result.replace(char, "_")
            return result

        self.env.filters["upper"] = upper_filter
        self.env.filters["lower"] = lower_filter
        self.env.filters["sanitize"] = sanitize_filter

    def _parse_custom_rules(self, config_str: str):
        """
        解析扩展名特定模板规则

        :param config_str: 规则字符串，格式：ext1,ext2 => template（每行一个）
        """
        for rule in config_str.strip().split("\n"):
            rule = rule.strip()
            if not rule or "=>" not in rule:
                continue

            try:
                extensions_part, template_str = rule.split("=>", 1)
                extensions = [ext.strip().lower() for ext in extensions_part.split(",")]
                template_str = template_str.strip()

                if not template_str:
                    logger.warning(f"【STRM 文件名模板】规则模板为空，跳过: {rule}")
                    continue

                try:
                    template = self.env.from_string(template_str)
                except TemplateError as e:
                    logger.error(
                        f"【STRM 文件名模板】扩展名模板解析失败: {rule}, 错误: {e}"
                    )
                    continue

                for ext in extensions:
                    if not ext:
                        continue
                    if not ext.startswith("."):
                        ext = "." + ext
                    self.extension_templates[ext] = template
                    logger.debug(
                        f"【STRM 文件名模板】注册扩展名模板: {ext} => {template_str[:50]}..."
                    )

            except Exception as e:
                logger.error(f"【STRM 文件名模板】解析规则失败: {rule}, 错误: {e}")
                continue

    def get_template_for_file(self, file_name: str) -> Optional[Template]:
        """
        根据文件名获取对应的模板

        :param file_name: 文件名

        :return: 匹配的模板，如果没有匹配则返回基础模板，如果都没有则返回 None
        """
        extension = Path(file_name).suffix.lower()

        if extension in self.extension_templates:
            return self.extension_templates[extension]

        return self.base_template

    def render(
        self,
        file_name: str,
        file_path: Optional[str] = None,
        file_stem: Optional[str] = None,
        file_suffix: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional[str]:
        """
        渲染文件名模板

        :param file_name: 文件名（包含扩展名）
        :param file_path: 文件路径
        :param file_stem: 文件名（不含扩展名）
        :param file_suffix: 文件扩展名（包含点号）

        :return: 渲染后的文件名字符串，如果没有可用模板则返回 None
        """
        template = self.get_template_for_file(file_name)

        if not template:
            return None

        if file_stem is None:
            file_stem = Path(file_name).stem
        if file_suffix is None:
            file_suffix = Path(file_name).suffix

        context = {
            "file_name": file_name or "",
            "file_stem": file_stem or "",
            "file_suffix": file_suffix or "",
            "file_path": file_path or "",
            **kwargs,
        }

        try:
            result = template.render(**context)
            invalid_chars = '<>:"/\\|?*'
            for char in invalid_chars:
                result = result.replace(char, "_")
            return result
        except TemplateError as e:
            logger.error(f"【STRM 文件名模板】模板渲染失败: {e}, 上下文: {context}")
            raise
        except Exception as e:
            logger.error(f"【STRM 文件名模板】渲染时发生未知错误: {e}")
            raise


class StrmUrlGetter:
    """
    获取 Strm URL
    """

    def __init__(self):
        self.strm_url_encode = configer.strm_url_encode

        self.base_url_cache = f"{configer.moviepilot_address.rstrip('/')}/api/v1/plugin/P115StrmHelper/redirect_url"

        self.url_template_resolver = None
        if configer.strm_url_template_enabled:
            try:
                self.url_template_resolver = StrmUrlTemplateResolver(
                    base_template=configer.strm_url_template,
                    custom_rules=configer.strm_url_template_custom,
                )
            except Exception as e:
                logger.error(f"【STRM URL 模板】初始化失败: {e}")
                self.url_template_resolver = None

    def get_strm_url(self, pickcode: str, file_name: str, file_path: str) -> str:
        """
        获取普通 STRM URL

        :param: pickcode: 文件 pickcode
        :param: file_name: 文件名称
        :param: file_path: 文件网盘路径
        """
        if self.url_template_resolver:
            try:
                result = self.url_template_resolver.render(
                    file_name=file_name,
                    base_url=self.base_url_cache,
                    pickcode=pickcode,
                    file_path=file_path,
                    file_id=str(to_id(pickcode)),
                )
                if result:
                    return result
            except Exception as e:
                logger.error(f"【STRM URL 模板】渲染失败，使用默认格式: {e}")

        if configer.fuse_strm_takeover_enabled:
            try:
                from ..helper.strm.mount import match_fuse_strm_takeover

                fuse_strm_content = match_fuse_strm_takeover(
                    file_name=file_name, file_path=file_path
                )
                if fuse_strm_content:
                    return fuse_strm_content
            except Exception as e:
                logger.error(f"【FUSE STRM 接管】处理失败: {e}", exc_info=True)

        strm_url = f"{self.base_url_cache}?pickcode={pickcode}"
        if configer.strm_url_format == "pickname":
            if self.strm_url_encode:
                file_name = quote(file_name)
            strm_url += f"&file_name={file_name}"

        return strm_url

    def get_share_strm_url(
        self,
        share_code: str,
        receive_code: str,
        file_id: str,
        file_name: str,
        file_path: str,
    ) -> str:
        """
        获取分享 STRM URL

        :param share_code: 分享码
        :param receive_code: 提取码
        :param file_id: 文件 ID
        :param file_name: 文件名称
        :param file_path: 文件网盘路径
        """
        if self.url_template_resolver:
            try:
                result = self.url_template_resolver.render(
                    file_name=file_name,
                    base_url=self.base_url_cache,
                    share_code=share_code,
                    receive_code=receive_code,
                    file_id=file_id,
                    file_path=file_path,
                )
                if result:
                    return result
            except Exception as e:
                logger.error(f"【STRM URL 模板】渲染失败，使用默认格式: {e}")

        strm_url = f"{self.base_url_cache}?share_code={share_code}&receive_code={receive_code}&id={file_id}"
        if configer.strm_url_format == "pickname":
            strm_url += f"&file_name={file_name}"

        return strm_url


class StrmGenerater:
    """
    STRM 文件生成工具类
    """

    _filename_template_resolver: Optional[Union[StrmFilenameTemplateResolver, bool]] = (
        None
    )

    @staticmethod
    def _get_filename_template_resolver() -> Optional[StrmFilenameTemplateResolver]:
        """
        获取文件名模板解析器
        """
        resolver = StrmGenerater._filename_template_resolver

        if isinstance(resolver, StrmFilenameTemplateResolver):
            return resolver

        if resolver is False:
            return None

        if not configer.strm_filename_template_enabled:
            StrmGenerater._filename_template_resolver = False
            return None

        try:
            resolver = StrmFilenameTemplateResolver(
                base_template=configer.strm_filename_template,
                custom_rules=configer.strm_filename_template_custom,
            )
            StrmGenerater._filename_template_resolver = resolver
            return resolver
        except Exception as e:
            logger.error(f"【STRM 文件名模板】初始化失败: {e}")
            StrmGenerater._filename_template_resolver = False
            return None

    @staticmethod
    def _reset_filename_template_resolver():
        """
        重置文件名模板解析器
        """
        StrmGenerater._filename_template_resolver = None

    @staticmethod
    def should_generate_strm(
        filename: str,
        mode: str,
        filesize: Optional[int] | CompareMinSize = None,
        blacklist_automaton: Optional[Automaton] = None,
    ) -> tuple[str, bool]:
        """
        判断文件是否能生成总规则
        """
        # 1. 判断是否在黑名单
        if blacklist_automaton:
            blacklist_msg, blacklist_status = StrmGenerater.not_blacklist_key_automaton(
                filename, blacklist_automaton
            )
        else:
            blacklist_msg, blacklist_status = StrmGenerater.not_blacklist_key(filename)
        if not blacklist_status:
            return blacklist_msg, blacklist_status

        # 2. 判断大小是否低于最低限制
        minsize_msg, minsize_status = StrmGenerater.not_min_limit(mode, filesize)
        if not minsize_status:
            return minsize_msg, minsize_status

        return "", True

    @staticmethod
    def not_blacklist_key_automaton(
        filename, blacklist_automaton: Automaton
    ) -> tuple[str, bool]:
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
    def not_blacklist_key(filename) -> tuple[str, bool]:
        """
        判断文件名是否包含黑名单中的任何关键词
        """
        blacklist = configer.strm_generate_blacklist

        if not blacklist:
            return "", True
        lower_filename = filename.lower()
        for keyword in blacklist:  # pylint: disable=E1133
            if keyword.lower() in lower_filename:
                return f"匹配到黑名单关键词 {keyword}", False
        return "", True

    @staticmethod
    def not_min_limit(
        mode: str, filesize: Optional[int] | CompareMinSize = None
    ) -> tuple[str, bool]:
        """
        判断文件大小是否低于最低限制
        """
        min_size = None
        if isinstance(filesize, CompareMinSize):
            min_size = filesize.min_size
            filesize = filesize.file_size
        if mode == "full":
            min_size = configer.full_sync_min_file_size
        elif mode == "life":
            min_size = configer.monitor_life_min_file_size
        elif mode == "increment":
            min_size = configer.increment_sync_min_file_size

        if not min_size or min_size == 0:
            return "", True

        if not filesize:
            return "", True

        if filesize < min_size:
            return "小于最小文件大小", False

        return "", True

    @staticmethod
    def get_strm_filename(
        file_path: Path,
        file_name: Optional[str] = None,
        file_path_str: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """
        根据原始文件路径生成 STRM 文件名

        :param file_path: 原始文件路径（Path 对象）
        :param file_name: 文件名（可选，如果不提供则从file_path提取）
        :param file_path_str: 文件路径字符串（可选，用于模板渲染）
        :param kwargs: 其他上下文信息（用于模板渲染）

        :return: STRM 文件名（如 "movie.iso.strm" 或 "movie.strm"）
        """
        if StrmGenerater._filename_template_resolver is False:
            suffix = file_path.suffix.lower()
            stem = file_path.stem
            if suffix == ".iso":
                return f"{stem}.iso.strm"
            return f"{stem}.strm"

        template_resolver = StrmGenerater._get_filename_template_resolver()
        if template_resolver:
            try:
                suffix = file_path.suffix
                stem = file_path.stem

                if file_name is None:
                    file_name = file_path.name

                result = template_resolver.render(
                    file_name=file_name,
                    file_path=file_path_str or str(file_path),
                    file_stem=stem,
                    file_suffix=suffix,
                    **kwargs,
                )
                if result:
                    return result
            except Exception as e:
                logger.error(f"【STRM 文件名模板】渲染失败，使用默认格式: {e}")

        suffix = file_path.suffix.lower()
        stem = file_path.stem
        if suffix == ".iso":
            return f"{stem}.iso.strm"
        return f"{stem}.strm"
