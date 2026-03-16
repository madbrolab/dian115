from typing import List, Optional, TypedDict


class ResourceItem(TypedDict):
    """
    资源项
    """

    message_id: Optional[str]
    title: Optional[str]
    pub_date: Optional[str]
    content: Optional[str]
    image: Optional[str]
    cloud_links: List[str]
    tags: List[str]
    cloud_type: Optional[str]
    channel_id: Optional[str]
