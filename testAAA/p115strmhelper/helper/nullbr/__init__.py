from nullbr import NullbrSDK

from ...core.config import configer
from ...utils.sentry import sentry_manager


@sentry_manager.capture_all_class_exceptions
class NullbrHelper:
    """
    Nullbr 资源搜索
    """

    def __init__(self):
        self.client = NullbrSDK(
            app_id=configer.get_config("nullbr_app_id"),
            api_key=configer.get_config("nullbr_api_key"),
        )

    def get_media_list(self, name: str):
        """
        获取信息列表
        """
        search_results = self.client.search(name, page=1)
        return search_results.items

    def search_resource(self, tmdb_id: int, media_type: str):
        """
        搜索资源
        """
        if media_type not in ["movie", "tv", "collection"]:
            return []

        try:
            get_media_func = getattr(self.client, f"get_{media_type}")
            get_media_115_func = getattr(self.client, f"get_{media_type}_115")
        except AttributeError:
            return []

        result = get_media_func(tmdb_id)
        if result and result.has_115:
            result_115 = get_media_115_func(tmdb_id)
            if result_115 and result_115.items:
                return [
                    {"taskname": "【Nullbr】" + item.title, "shareurl": item.share_link}
                    for item in result_115.items
                ]

        return []
