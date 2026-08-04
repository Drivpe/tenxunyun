import json
from urllib.parse import quote

from playwright.sync_api import sync_playwright


ACTIVITY_URL = "https://cloud.tencent.com/act/pro/featured-202607#MS"
LOGIN_URL = f"https://cloud.tencent.com/login?s_url={quote(ACTIVITY_URL, safe='')}"


def refresh_cookies():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(LOGIN_URL)

        print("Please scan the QR code to sign in to Tencent Cloud...")
        page.wait_for_url(
            lambda url: "cloud.tencent.com/act/pro/featured-202607" in url,
            timeout=0,
        )

        # Give Tencent Cloud time to finish setting post-login session cookies.
        page.wait_for_timeout(8000)
        cookies = context.cookies()
        cookie_names = {cookie["name"] for cookie in cookies}
        if "uin" not in cookie_names or not ({"skey", "p_skey"} & cookie_names):
            raise RuntimeError("Login cookies are incomplete; please run this script again.")

        with open("cookies.json", "w", encoding="utf-8") as cookie_file:
            json.dump(cookies, cookie_file, ensure_ascii=False, indent=2)

        print(f"Login succeeded. Saved {len(cookies)} cookies to cookies.json.")
        browser.close()


if __name__ == "__main__":
    refresh_cookies()
