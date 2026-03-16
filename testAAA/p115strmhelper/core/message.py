from random import choice
from typing import Optional
from base64 import b64decode


from app.core.config import settings
from app.schemas import Notification, NotificationType, MessageChannel

from ..core.config import configer
from ..core.i18n import i18n
from ..core.plunins import PluginChian


def post_message(
    channel: MessageChannel = None,
    mtype: NotificationType = None,
    title: Optional[str] = None,
    text: Optional[str] = None,
    image: Optional[str] = None,
    link: Optional[str] = None,
    userid: Optional[str] = None,
    username: Optional[str] = None,
    **kwargs,
):
    """
    发送消息
    """
    chain = PluginChian()
    if not link:
        link = settings.MP_DOMAIN(
            f"#/plugins?tab=installed&id={configer.get_config('PLUSIN_NAME')}"
        )
    if configer.get_config("language") == "zh_CN_catgirl":
        message = b64decode(choice(i18n.get("fuck")).encode("utf-8")).decode(
            "utf-8"
        )
        if text:
            if text.endswith("\n"):
                text += f"\n{message}\n"
            else:
                text += f"\n{message}"
        else:
            text = f"\n{message}\n"
    chain.post_message(
        Notification(
            channel=channel,
            mtype=mtype,
            title=title,
            text=text,
            image=image,
            link=link,
            userid=userid,
            username=username,
            **kwargs,
        )
    )
