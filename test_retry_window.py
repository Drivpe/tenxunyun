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


if __name__ == "__main__":
    unittest.main()
