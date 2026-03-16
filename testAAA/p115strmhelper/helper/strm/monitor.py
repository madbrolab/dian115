from pathlib import Path

from app.log import logger
from app.schemas import FileItem

from ...utils.sentry import sentry_manager
from ...utils.strm import StrmGenerater, StrmUrlGetter


class MonitorStrmHelper:
    """
    目录上传 STRM
    """

    @staticmethod
    def generate_strm_after_upload(
        uploaded_file_item: FileItem,
        dest_strm: str,
        mon_path: str,
        local_file_path: Path,
    ) -> bool:
        """
        上传网盘成功后，在本地 STRM 输出目录生成对应 .strm 文件

        :param uploaded_file_item: 上传成功后返回的文件信息
        :param dest_strm: 本地 STRM 输出目录
        :param mon_path: 监控目录
        :param local_file_path: 本地源文件路径

        :return: 是否生成成功
        """
        dest_strm = (dest_strm or "").strip()
        if not dest_strm:
            return False

        try:
            if not uploaded_file_item or not getattr(
                uploaded_file_item, "pickcode", None
            ):
                logger.warn(
                    "【目录上传】上传返回的文件信息中无 pickcode，跳过生成 STRM"
                )
                return False

            pickcode = uploaded_file_item.pickcode
            if not (len(pickcode) == 17 and str(pickcode).isalnum()):
                logger.warn(f"【目录上传】无效 pickcode: {pickcode}，跳过生成 STRM")
                return False

            url_getter = StrmUrlGetter()
            strm_url = url_getter.get_strm_url(
                pickcode=pickcode,
                file_name=uploaded_file_item.name,
                file_path=uploaded_file_item.path,
            )

            rel = local_file_path.relative_to(mon_path)
            out_dir = Path(dest_strm) / rel.parent
            out_dir.mkdir(parents=True, exist_ok=True)
            strm_name = StrmGenerater.get_strm_filename(Path(uploaded_file_item.name))
            strm_path = out_dir / strm_name

            with open(strm_path, "w", encoding="utf-8") as f:
                f.write(strm_url)

            logger.info(f"【目录上传】生成 STRM 成功: {strm_path}")
            return True

        except Exception as e:
            sentry_manager.sentry_hub.capture_exception(e)
            logger.error(
                f"【目录上传】生成 STRM 失败: {uploaded_file_item.path if uploaded_file_item else 'unknown'}，错误: {e}"
            )
            return False
