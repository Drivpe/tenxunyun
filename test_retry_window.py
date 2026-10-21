import unittest

import snap_up_server


class RetryWindowTest(unittest.TestCase):
    def test_region_names_match_activity_page(self):
        self.assertEqual(
            snap_up_server.REGION_NAMES,
            {1: "广州", 4: "上海", 8: "北京"},
        )

    def test_retries_until_success_within_retry_window(self):
        calls = []
        current_time = [0.0]

        def fake_buy(region_ids):
            calls.append(tuple(region_ids))
            if len(calls) < 3:
                return {"code": 1101001, "msg": "not started"}
            return {"code": 0, "msg": "ok"}

        def fake_time():
            return current_time[0]

        def fake_sleep(seconds):
            current_time[0] += seconds

        result = snap_up_server.buy_now_with_retry(
            [1, 4, 8],
            duration_seconds=60,
            interval_seconds=0.5,
            buy_func=fake_buy,
            time_func=fake_time,
            sleep_func=fake_sleep,
        )

        self.assertEqual(result["code"], 0)
        self.assertEqual(len(calls), 3)


# 真实活动页中最小一个场次块（字段顺序与线上页面一致）
MARKER = '"activity_id":164461404341040,"channel_tag"'
GOODS_PREFIX = '"sales":[{"act_id":%s,"goods_name":"轻量应用服务器 4核4G3M"'
SESSION_1500 = (
    '}],"seckill_type":"block","short_url":"","start_date":"2026-10-21",'
    '"start_time":"15:00:00","status":1,"startTime":1792566000000,'
    '"endTime":1792576800000,"nowTime":1792562769107}'
)
SESSION_1000 = (
    '}],"seckill_type":"block","short_url":"","start_date":"2026-10-21",'
    '"start_time":"10:00:00","status":1,"startTime":1792548000000,'
    '"endTime":1792555200000,"nowTime":1792562769107}'
)
TARGET = snap_up_server.SERVER_ACT_ID
OTHER = 1897655787435011


class SeckillSessionTest(unittest.TestCase):
    @staticmethod
    def build_html(*items):
        """items: (act_id, session_body)"""
        return "".join(MARKER + GOODS_PREFIX % act_id + body for act_id, body in items)

    def test_parses_session_start_ms(self):
        html = self.build_html((TARGET, SESSION_1500))
        sessions = snap_up_server.parse_seckill_sessions(html)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["start_ms"], 1792566000000)
        self.assertEqual(sessions[0]["start_text"], "2026-10-21 15:00:00")

    def test_ignores_sessions_without_target_goods(self):
        html = self.build_html((OTHER, SESSION_1500))
        self.assertEqual(snap_up_server.parse_seckill_sessions(html), [])

    def test_sessions_sorted_by_start_time(self):
        html = self.build_html((TARGET, SESSION_1500), (TARGET, SESSION_1000))
        sessions = snap_up_server.parse_seckill_sessions(html)
        self.assertEqual([s["start_ms"] for s in sessions], [1792548000000, 1792566000000])

    def test_picks_in_progress_session_instead_of_waiting_tomorrow(self):
        sessions = [
            {"start_ms": 1792548000000, "end_ms": 1792555200000, "start_text": "10:00"},
            {"start_ms": 1792566000000, "end_ms": 1792576800000, "start_text": "15:00"},
        ]
        # 14:00 左右：10:00 场已结束，应选 15:00
        self.assertEqual(snap_up_server.pick_next_session(sessions, 1792562769107)["start_text"], "15:00")
        # 11:00 左右：10:00 场仍在进行，应立即抢该场而不是拖到 15:00
        self.assertEqual(snap_up_server.pick_next_session(sessions, 1792551600000)["start_text"], "10:00")

    def test_returns_none_when_all_sessions_ended(self):
        sessions = [{"start_ms": 1, "end_ms": 2, "start_text": "old"}]
        self.assertIsNone(snap_up_server.pick_next_session(sessions, 10))

    def test_manual_time_is_absolute_beijing_time(self):
        # 手工指定必须与页面 startTime 对齐，且不受本机时区影响
        self.assertEqual(
            snap_up_server.select_seckill_timestamp("2026-10-21 15:00:00"),
            1792566000000,
        )

    def test_select_returns_none_without_sessions(self):
        original = snap_up_server.fetch_seckill_sessions
        snap_up_server.fetch_seckill_sessions = lambda *a, **k: []
        try:
            self.assertIsNone(snap_up_server.select_seckill_timestamp(""))
        finally:
            snap_up_server.fetch_seckill_sessions = original


class CsrfTokenTest(unittest.TestCase):
    def setUp(self):
        self._saved_cookies = snap_up_server.cookies
        self._saved_headers = dict(snap_up_server.headers)

    def tearDown(self):
        snap_up_server.cookies = self._saved_cookies
        snap_up_server.headers.clear()
        snap_up_server.headers.update(self._saved_headers)

    def _expected(self, skey):
        acc = 5381
        for ch in skey:
            acc += (acc << 5) + ord(ch)
        return str(acc & 0x7fffffff)

    def test_token_derives_from_skey(self):
        snap_up_server.cookies = [{"name": "skey", "value": "abc123"}]
        self.assertEqual(snap_up_server.get_csrf_token(), self._expected("abc123"))

    def test_token_falls_back_to_p_skey(self):
        snap_up_server.cookies = [{"name": "p_skey", "value": "xyz"}]
        self.assertEqual(snap_up_server.get_csrf_token(), self._expected("xyz"))

    def test_empty_cookies_yield_empty_token(self):
        snap_up_server.cookies = []
        self.assertEqual(snap_up_server.get_csrf_token(), "")

    def test_refresh_headers_updates_token(self):
        snap_up_server.cookies = [{"name": "skey", "value": "xyz"}]
        token = snap_up_server.refresh_csrf_headers()
        self.assertEqual(snap_up_server.headers["x-csrf-token"], token)
        self.assertEqual(snap_up_server.headers["X-CSRF-TOKEN"], token)


class DeadCodeTest(unittest.TestCase):
    def test_prepare_do_dead_block_removed(self):
        import inspect
        source = inspect.getsource(snap_up_server)
        # prepare-do 现在必须是可执行代码，而不是 return 之后的死块
        self.assertTrue(hasattr(snap_up_server, "prepare_eligibility_check"))
        self.assertIn("prepare-do", source)


class ResultClassificationTest(unittest.TestCase):
    """现场事故：限流与资格硬错误都被当作普通失败高频重试"""

    def test_success(self):
        self.assertEqual(snap_up_server.classify_result({"code": 0}), "success")

    def test_rate_limit(self):
        self.assertEqual(
            snap_up_server.classify_result({"code": 408, "msg": "系统访问频率过快，请稍后再试"}),
            "rate_limited",
        )

    def test_fatal_eligibility_codes(self):
        # 1100106 未激活 / 1100507 获取用户信息失败，重试无效
        self.assertEqual(snap_up_server.classify_result({"code": 1100106}), "fatal")
        self.assertEqual(snap_up_server.classify_result({"code": 1100507}), "fatal")

    def test_seckill_not_started_is_retryable(self):
        self.assertEqual(snap_up_server.classify_result({"code": 1101001}), "retryable")

    def test_sold_out_classified_separately(self):
        # 1100136 是库存问题，不是资格问题：不得归入 fatal 停止，
        # 也不得按 0.5 秒硬撞（只会换来 408）
        self.assertEqual(
            snap_up_server.classify_result({"code": 1100136, "msg": "抱歉，当前商品已售罄"}),
            "sold_out",
        )

    def test_none_and_unknown_are_retryable(self):
        self.assertEqual(snap_up_server.classify_result(None), "retryable")
        self.assertEqual(snap_up_server.classify_result({"code": 9999}), "retryable")


class FatalStopsRetryTest(unittest.TestCase):
    def test_stops_immediately_on_fatal(self):
        calls = []
        clock = [0.0]

        def fake_buy(region_ids):
            calls.append(1)
            return {"code": 1100507, "msg": "获取用户信息失败"}

        result = snap_up_server.buy_now_with_retry(
            [1, 4, 8],
            duration_seconds=60,
            interval_seconds=0.5,
            buy_func=fake_buy,
            time_func=lambda: clock[0],
            sleep_func=lambda sec: clock.__setitem__(0, clock[0] + sec),
        )

        # 修复前会打满 60 秒窗口（约 80+ 轮），现在必须只调用一次
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["code"], 1100507)
        self.assertEqual(clock[0], 0.0)


class RateLimitBackoffTest(unittest.TestCase):
    def test_backoff_grows_instead_of_fixed_interval(self):
        slept = []
        clock = [0.0]

        def fake_buy(region_ids):
            return {"code": 408, "msg": "系统访问频率过快"}

        snap_up_server.buy_now_with_retry(
            [1, 4, 8],
            duration_seconds=60,
            interval_seconds=0.5,
            buy_func=fake_buy,
            time_func=lambda: clock[0],
            sleep_func=lambda sec: (slept.append(sec), clock.__setitem__(0, clock[0] + sec)),
            max_backoff_seconds=8.0,
        )

        # 修复前恒为 0.5 秒；现在应逐轮拉大并封顶
        self.assertGreater(len(slept), 2)
        self.assertEqual(slept[0], 1.0)
        self.assertGreater(slept[1], slept[0])
        self.assertLessEqual(max(slept), 8.0)
        self.assertGreater(slept[1], 0.5, "限流时不得沿用 0.5 秒高频节奏")

    def test_sold_out_waits_gently_instead_of_hard_hitting(self):
        # 修复前：1100136 归入 retryable，按 0.5 秒硬撞换回 408
        slept = []
        clock = [0.0]
        codes = [{"code": 1100136, "msg": "抱歉，当前商品已售罄"}] * 3 + [{"code": 0}]

        def fake_buy(region_ids):
            return codes.pop(0)

        result = snap_up_server.buy_now_with_retry(
            [1, 4, 8],
            duration_seconds=60,
            interval_seconds=0.5,
            sold_out_interval_seconds=3.0,
            buy_func=fake_buy,
            time_func=lambda: clock[0],
            sleep_func=lambda sec: (slept.append(sec), clock.__setitem__(0, clock[0] + sec)),
        )

        self.assertEqual(result["code"], 0)
        self.assertEqual(slept[:3], [3.0, 3.0, 3.0])
        self.assertTrue(all(sec > 0.5 for sec in slept[:3]))

    def test_returns_to_base_interval_after_retryable(self):
        slept = []
        clock = [0.0]
        codes = [{"code": 408}, {"code": 1101001}, {"code": 408}, {"code": 0}]

        def fake_buy(region_ids):
            return codes.pop(0)

        result = snap_up_server.buy_now_with_retry(
            [1, 4, 8],
            duration_seconds=60,
            interval_seconds=0.5,
            buy_func=fake_buy,
            time_func=lambda: clock[0],
            sleep_func=lambda sec: (slept.append(sec), clock.__setitem__(0, clock[0] + sec)),
        )

        self.assertEqual(result["code"], 0)
        self.assertEqual(slept[0], 1.0)      # 408 -> 退避
        self.assertEqual(slept[1], 0.5)      # 尚未开始 -> 回到基准节奏


class PrepareEligibilityTest(unittest.TestCase):
    def setUp(self):
        self._original = snap_up_server.session
        snap_up_server.session = None  # 强制走 except 分支前先替换

    def tearDown(self):
        snap_up_server.session = self._original

    def test_blocked_when_act_condition_unmet(self):
        class Resp:
            def json(self):
                return {
                    "code": 1100106,
                    "msg": "抱歉，当前活动仅针对已激活账号开放，欢迎了解其他活动。",
                    "data": {"detail": {"act_condition": {
                        "activated": 0, "real_name": 0, "registered": 1, "available": 0}}},
                }

        class FakeSession:
            def post(self, *a, **k):
                return Resp()

        snap_up_server.session = FakeSession()
        self.assertEqual(snap_up_server.prepare_eligibility_check(), "blocked")

    def test_sold_out_is_not_blocked(self):
        # 1100136 说明账号资格已通过（prepare-do 先查资格再查商品），
        # 主流程必须继续而不是退出
        class Resp:
            def json(self):
                return {"code": 1100136, "msg": "抱歉，当前商品已售罄，欢迎选择其他商品"}

        class FakeSession:
            def post(self, *a, **k):
                return Resp()

        snap_up_server.session = FakeSession()
        self.assertEqual(snap_up_server.prepare_eligibility_check(), "sold_out")

    def test_passed_on_code_zero(self):
        class Resp:
            def json(self):
                return {"code": 0, "msg": "ok"}

        class FakeSession:
            def post(self, *a, **k):
                return Resp()

        snap_up_server.session = FakeSession()
        self.assertEqual(snap_up_server.prepare_eligibility_check(), "passed")

    def test_unknown_for_other_codes(self):
        class Resp:
            def json(self):
                return {"code": 1101001, "msg": "抱歉，秒杀尚未开始"}

        class FakeSession:
            def post(self, *a, **k):
                return Resp()

        snap_up_server.session = FakeSession()
        self.assertEqual(snap_up_server.prepare_eligibility_check(), "unknown")

    def test_unknown_on_exception(self):
        class FakeSession:
            def post(self, *a, **k):
                raise RuntimeError("timeout")

        snap_up_server.session = FakeSession()
        self.assertEqual(snap_up_server.prepare_eligibility_check(), "unknown")


class WatchStockTest(unittest.TestCase):
    """回流看守：用只读接口轮询，见货才下单，不硬撞购买接口"""

    def test_buys_when_stock_reappears(self):
        clock = [1000.0]
        checks = iter([None, None, 4])
        bought = []

        def fake_check():
            return next(checks)

        def fake_buy(region_ids):
            bought.append(list(region_ids))
            return {"code": 0}

        result = snap_up_server.watch_stock_and_buy(
            [1, 4, 8],
            end_ms=10_000.0,
            poll_seconds=5.0,
            check_func=fake_check,
            buy_func=fake_buy,
            time_func=lambda: clock[0],
            sleep_func=lambda sec: clock.__setitem__(0, clock[0] + sec),
        )

        self.assertEqual(result["code"], 0)
        self.assertEqual(bought, [[4]], "应只对检测到库存的地域下单")

    def test_stops_when_session_ended(self):
        clock = [1000.0]
        calls = []

        def fake_check():
            calls.append(1)
            return None

        result = snap_up_server.watch_stock_and_buy(
            [1, 4, 8],
            end_ms=3000.0,
            poll_seconds=1000.0,
            check_func=fake_check,
            buy_func=lambda ids: None,
            time_func=lambda: clock[0],
            sleep_func=lambda sec: clock.__setitem__(0, clock[0] + sec),
        )

        self.assertIsNone(result)
        self.assertEqual(len(calls), 2, "到期前查两次，到期后必须停")

    def test_fatal_during_watch_stops_watch(self):
        clock = [1000.0]

        result = snap_up_server.watch_stock_and_buy(
            [1, 4, 8],
            end_ms=None,
            max_attempts=5,
            check_func=lambda: 4,
            buy_func=lambda ids: {"code": 1100507},
            time_func=lambda: clock[0],
            sleep_func=lambda sec: clock.__setitem__(0, clock[0] + sec),
        )

        self.assertIsNone(result)

    def test_manual_time_without_cap_is_refused(self):
        # 手工指定时间没有场次边界，必须拒绝无限轮询
        self.assertIsNone(snap_up_server.watch_stock_and_buy(
            [1, 4, 8], end_ms=None, max_attempts=None,
            check_func=lambda: None, buy_func=lambda ids: None,
            sleep_func=lambda sec: None,
        ))


class BuyNowConcurrentTest(unittest.TestCase):
    """buy_now 返回 None 时不得崩溃（历史缺陷）"""

    def test_handles_none_result_without_crashing(self):
        original = snap_up_server.buy_now
        snap_up_server.buy_now = lambda region_id: None
        try:
            self.assertIsNone(snap_up_server.buy_now_concurrent([1, 4, 8]))
        finally:
            snap_up_server.buy_now = original

    def test_returns_first_success(self):
        original = snap_up_server.buy_now
        snap_up_server.buy_now = lambda region_id: {"code": 0} if region_id == 4 else None
        try:
            self.assertEqual(snap_up_server.buy_now_concurrent([1, 4, 8]), {"code": 0})
        finally:
            snap_up_server.buy_now = original


if __name__ == "__main__":
    unittest.main()

