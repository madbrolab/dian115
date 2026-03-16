__all__ = ["WebhookUtils"]


from typing import List


class WebhookUtils:
    """
    Webhook 事件处理工具类
    """

    @staticmethod
    def parse_item_paths_from_description(description: str) -> List[str]:
        """
        从Description字段解析Item Path列表

        :param description: Description字段内容

        :return: Item Path列表
        """
        if not description:
            return []

        item_paths = []
        lines = description.split("\n")
        in_item_path_section = False

        for line in lines:
            line = line.strip()

            if "Item Path:" in line:
                in_item_path_section = True
                if ":" in line:
                    path_part = line.split(":", 1)[1].strip()
                    if path_part:
                        item_paths.append(path_part)
                continue

            if in_item_path_section:
                if any(
                    marker in line
                    for marker in [
                        "Mount Paths:",
                        "Item Name:",
                        "Description:",
                        "Other Info:",
                    ]
                ):
                    in_item_path_section = False
                    continue

                if line:
                    if line.startswith("http://") or line.startswith("https://"):  # noqa
                        continue
                    if (
                        line.startswith("/")
                        or line.startswith("\\")
                        or line.startswith("./")
                        or line.startswith("../")
                        or (len(line) > 2 and line[1] == ":" and line[2] in "/\\")
                        or ("/" in line and "://" not in line)
                    ):
                        item_paths.append(line)

        item_paths = list(
            filter(None, [path.strip() for path in item_paths if path.strip()])
        )
        return item_paths
