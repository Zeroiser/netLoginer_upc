#!/usr/bin/env python3
import requests
from urllib.parse import urlparse

# ===============================================================
# 请修改为你的学号和密码
USERNAME = "230701xxxx"  # 在这里填你的学号
PASSWORD = "xxxx"  # 在这里填你的密码
# 运营商（移动 cmcc，联通 unicom, ctcc 电信），需要修改这里
SERVICE = "unicom"
# ===============================================================

# 登录接口 URL
LOGIN_URL = "http://wlan.upc.edu.cn/eportal/InterFace.do?method=login"

# 用于触发重定向到登录页的测试 URL
REDIRECT_TEST_URL = "http://detectportal.firefox.com/success.txt"

# 模拟浏览器的请求头
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Connection": "keep-alive",
}

def get_query_string():
    try:
        print("正在检查网络状态并获取登录参数...")
        # 访问测试网址，但不自动处理重定向，以便我们能检查响应头
        response = requests.get(REDIRECT_TEST_URL, headers=HEADERS, timeout=10, allow_redirects=False)
        if response.is_redirect:
            # 从 'Location' 响应头中获取登录页面的URL
            redirect_url = response.headers.get('Location')

            # print("\n--- DEBUG INFO ---")
            # print(f"Redirect response status code: {response.status_code}")
            # print(f"Redirect response headers: {response.headers}")
            # print(f"Extracted Location header: {redirect_url}")
            # print("--- DEBUG INFO END ---\n")

            if redirect_url and ".upc.edu.cn" in redirect_url:
                # 解析URL，提取查询字符串部分和主机地址
                parsed_url = urlparse(redirect_url)
                query_string = parsed_url.query
                login_host = f"{parsed_url.scheme}://{parsed_url.netloc}"
                print(f"成功获取登录主机: {login_host}")
                print(f"成功获取queryString: {query_string[:50]}...") # 打印部分queryString
                return query_string, login_host
            else:
                print("收到了一个非预期的重定向，无法继续。")
                return None, None
        
        # 如果状态码是 200 OK，说明已经联网
        elif response.status_code == 200:
            print("网络连接正常，无需登录。")
            return None, None
        
        else:
            print(f"收到非预期的响应状态码: {response.status_code}")
            return None, None

    except requests.exceptions.RequestException as e:
        print(f"网络请求失败，可能未连接到Wi-Fi或网络异常: {e}")
        return None, None

def login(query_string, login_host):
    """
    使用获取到的queryString和你的账号密码执行登录操作。
    """
    # 根据获取到的主机动态构造登录URL
    login_url = f"{login_host}/eportal/InterFace.do?method=login"

    # 构造POST请求的数据
    payload = {
        'userId': USERNAME,
        'password': PASSWORD,
        'service': SERVICE,
        'queryString': query_string,
        'operatorPwd': '',
        'operatorUserId': '',
        'validcode': '',
        'passwordEncrypt': 'false'
    }

    try:
        print(f"正在向 {login_url} 使用账号 '{USERNAME}' 进行登录...")
        response = requests.post(login_url, data=payload, headers=HEADERS, timeout=10)
        response.encoding = 'utf-8' # 设置正确的编码以防乱码
        
        # 对返回结果进行判断
        # 根据经验，成功信息通常包含 "success" 或 "成功"
        if '"result":"success"' in response.text:
            print("✅ 登录成功！现在你可以上网了。")
        else:
            # 尝试从返回的JSON中解析错误信息，如果失败则直接显示文本
            try:
                error_msg = response.json().get("message", "未知错误")
            except requests.exceptions.JSONDecodeError:
                error_msg = response.text.strip()
            print(f"❌ 登录失败: {error_msg}")

    except requests.exceptions.RequestException as e:
        print(f"登录请求失败: {e}")

if __name__ == "__main__":
    qs, host = get_query_string()
    if qs and host:
        login(qs, host)