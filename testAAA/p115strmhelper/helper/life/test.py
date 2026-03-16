from datetime import datetime, timezone
from time import time

from p115client import check_response, P115AuthenticationError
from p115client.tool.life import iter_life_behavior_once, life_show

from ...core.config import configer


class MonitorLifeTest:
    """
    生活事件测试类
    """

    @staticmethod
    def test_life_event_status(client):
        """
        测试生活事件开启状态

        :param client: P115Client实例

        :return: tuple (success: bool, debug_info: List[str], error_message: Optional[str])
        """
        debug_info = []
        try:
            resp = life_show(client, timeout=10, **configer.get_ios_ua_app(app=False))
            check_response(resp)
            if resp.get("state"):
                debug_info.append("   生活事件开启: 是")
                return True, debug_info, None
            else:
                debug_info.append("   生活事件开启: 否")
                debug_info.append(f"   错误信息: {resp}")
                return False, debug_info, "生活事件未开启"
        except Exception as e:
            debug_info.append(f"   生活事件检查异常: {str(e)}")
            return False, debug_info, f"生活事件检查异常: {str(e)}"

    @staticmethod
    def test_life_event_pull(client):
        """
        测试拉取生活事件数据

        :param client: P115Client实例

        :return: tuple (success: bool, debug_info: List[str], error_messages: List[str])
        """
        debug_info = []
        error_messages = []
        success = True

        try:
            events_iterator = iter_life_behavior_once(
                client=client,
                from_time=int(time()),
                from_id=0,
                cooldown=4,
                **configer.get_ios_ua_app(),
            )
            try:
                first_event = next(events_iterator)
                debug_info.append("   拉取测试: 成功")
                debug_info.append("   获取到事件: 是")
                debug_info.append(f"   事件类型: {first_event.get('type', '未知')}")
                debug_info.append(f"   事件ID: {first_event.get('id', '未知')}")
                event_count = 1
                for _ in range(9):
                    try:
                        next(events_iterator)
                        event_count += 1
                    except StopIteration:
                        break
                debug_info.append(f"   拉取到事件数: {event_count}个")
            except StopIteration:
                debug_info.append("   拉取测试: 成功")
                debug_info.append("   获取到事件: 否（无新事件，正常情况）")
            except P115AuthenticationError:
                debug_info.append("   拉取测试: 失败")
                debug_info.append("   错误: 登入失效，请重新扫码登入")
                success = False
                error_messages.append("115登入失效")
            except Exception as e:
                debug_info.append("   拉取测试: 失败")
                debug_info.append(f"   错误: {str(e)}")
                success = False
                error_messages.append(f"拉取数据失败: {str(e)}")
        except Exception as e:
            debug_info.append("   拉取测试: 异常")
            debug_info.append(f"   异常信息: {str(e)}")
            success = False
            error_messages.append(f"拉取数据异常: {str(e)}")

        return success, debug_info, error_messages

    @staticmethod
    def test_life_event_pull_from_time(client, from_time: int):
        """
        拉取指定开始时间以来的全部生活事件数据，统计数量并逐条输出到调试信息。

        :param client: P115Client 实例
        :param from_time: 开始时间（Unix 时间戳，秒，含）

        :return: tuple (success: bool, debug_info: List[str], error_messages: List[str])
        """
        debug_info = []
        error_messages = []
        success = True
        try:
            dt_str = datetime.fromtimestamp(from_time, tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S UTC"
            )
            debug_info.append(f"   指定开始时间: {dt_str} ({from_time})")
            events_iterator = iter_life_behavior_once(
                client=client,
                from_time=from_time,
                from_id=0,
                cooldown=4,
                **configer.get_ios_ua_app(),
            )
            events_list = list(events_iterator)
            event_count = len(events_list)
            debug_info.append("   拉取指定时间数据: 成功")
            debug_info.append(f"   拉取到事件总数: {event_count} 个")
            if events_list:
                debug_info.append("   ---------- 事件明细 ----------")
                for i, event in enumerate(events_list, 1):
                    ev_type = event.get("type", "")
                    type_name = event.get("event_name", "")
                    ut = event.get("update_time")
                    ut_str = (
                        datetime.fromtimestamp(int(ut), tz=timezone.utc).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                        if ut is not None
                        else ""
                    )
                    debug_info.append(
                        f"   [{i}] {type_name} id={event.get('id')} type={ev_type} "
                        f"update_time={ut_str}"
                    )
                    debug_info.append(
                        f"        file_name: {event.get('file_name', '')}"
                    )
                    debug_info.append(f"        pickcode: {event.get('pick_code', '')}")
            if events_list:
                debug_info.append("   ---------- 明细结束 ----------")
        except P115AuthenticationError:
            debug_info.append("   拉取指定时间数据: 失败")
            debug_info.append("   错误: 登入失效，请重新扫码登入")
            success = False
            error_messages.append("拉取指定时间数据时登入失效")
        except Exception as e:
            debug_info.append("   拉取指定时间数据: 失败")
            debug_info.append(f"   错误: {str(e)}")
            success = False
            error_messages.append(f"拉取指定时间数据失败: {str(e)}")
        return success, debug_info, error_messages
