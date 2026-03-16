__all__ = ["MathUtils"]


from typing import List

from numpy import mean as np_mean, std as np_std, isclose as np_isclose

from app.log import logger


class MathUtils:
    """
    标准数学计算方法工具类
    """

    @staticmethod
    def is_stable_cv(data_points: List[float | int], threshold: float = 0.05) -> bool:
        """
        使用变异系数 (CV) 判断一组三个数字是否稳定

        :param data_points: 一个包含三个数字的列表或元组
        :param threshold: 稳定性的阈值。默认值为 0.05，代表波动不超过 5%
                          例如，0.01 表示 1%，0.02 表示 2%

        :return bool: 如果数据的变异系数小于或等于阈值，则返回 True (稳定)，否则返回 False (不稳定)
        """
        if len(data_points) != 3:
            raise ValueError("输入的数据点列表必须恰好包含 3 个元素。")

        mean: float = float(np_mean(data_points))
        std_dev: float = float(np_std(data_points))

        if np_isclose(mean, 0):
            return np_isclose(std_dev, 0)

        coefficient_of_variation = std_dev / mean

        logger.debug(
            f"数据: {data_points}；平均值: {mean:.2f}；标准差: {std_dev:.2f}；"
        )
        logger.debug(
            f"变异系数 (CV): {coefficient_of_variation:.4f} (即 {coefficient_of_variation:.2%})"
        )
        logger.debug(f"阈值: {threshold:.4f} (即 {threshold:.2%})")

        return coefficient_of_variation <= threshold
