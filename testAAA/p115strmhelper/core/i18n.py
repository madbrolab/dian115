from typing import Any, Dict, Optional
from string import Formatter

from orjson import loads, JSONDecodeError

from app.core.config import settings

from ..core.config import configer


class NestedFormatter(Formatter):
    """
    支持嵌套字典的字符串格式化器
    """

    def get_value(self, key: str, args: Any, kwargs: Dict[str, Any]) -> Any:
        if "." in key:
            keys = key.split(".")
            value = kwargs
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return f"{{{key}}}"
            return value
        return super().get_value(key, args, kwargs)


class I18N:
    """
    国际化处理类
    """

    def __init__(self):
        self.translations: Dict[str, str] = {}
        self.default_translations: Dict[str, str] = {}
        self.formatter = NestedFormatter()

    def load_translations(self) -> None:
        """
        加载语言文件
        """
        locales_dir = settings.ROOT_PATH / "app/plugins" / "p115strmhelper" / "locales"
        lang = configer.get_config("language") or "zh_CN"
        default_lang = "zh_CN"

        lang_file = locales_dir / f"{lang}.json"

        try:
            with open(lang_file, "rb") as f:
                self.translations = loads(f.read())
        except (FileNotFoundError, JSONDecodeError):
            self.translations = {}

        if lang == default_lang:
            self.default_translations = self.translations
        else:
            default_lang_file = locales_dir / f"{default_lang}.json"
            try:
                with open(default_lang_file, "rb") as f:
                    self.default_translations = loads(f.read())
            except (FileNotFoundError, JSONDecodeError):
                self.default_translations = {}

    def translate(self, key: str, default: Optional[str] = None, **kwargs: Any) -> str:
        """
        获取翻译文本并格式化

        Args:
            key: 翻译键名
            default: 如果所有语言包都找不到键时返回的默认值
            **kwargs: 格式化参数

        Returns:
            格式化后的字符串
        """
        template = self.translations.get(key)

        if template is None:
            template = self.default_translations.get(key)

        if template is None:
            template = default or key

        if not template:
            return key

        try:
            return self.formatter.format(template, **kwargs)
        except (KeyError, AttributeError):
            return template

    def get(self, key: str):
        """
        直接获取键的值
        """
        return self.translations.get(key)


i18n = I18N()
