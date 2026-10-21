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
        self.assertNotIn("prepare-do", source)


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

