import websocket
import requests
import json
import time
import threading
from datetime import datetime
from trading_function import buy_etf, sell_etf, get_hashkey
# ==============================================================================
# ========== 통합 설정 (Configuration) ==========
# ==============================================================================
# --- KIS Developers API Key (매매 및 시세조회용) ---
APP_KEY = "PSVP4uaIGfmv9oviIqOjn58WIV3coGzjAEqu"  # 👈 본인의 APP KEY 입력
APP_SECRET = "NYuz2xS/ZFfTnLBa15UsPnU/iFaGMMAQiv/RoB4Xxi2yHOCCY1Zq9IgJARubfjWXzoFUbun4wlG7xhDQyWXIvSaWkK27RkFz8k4TBYpOtNzcRCeW17eBpQ1GULQkqP3AUultGWtcycBDkL/KHcPAga53hK37kM4YcSEsjoZgncVb6yO2DOc="  # 👈 본인의 APP SECRET 입력
ACCOUNT_NO = "50154524-01"  # 👈 본인의 계좌번호-상품코드 (예: "50154524-01")

# --- KIS Websocket Key (실시간 시세용) ---
# 실시간 시세 이용을 위해서는 별도의 웹소켓 접속키를 발급받아야 합니다.
# KIS Developers > 실시간 (웹소켓) > 접속키 발급
APPROVAL_KEY = "a34f9329-c5ef-47b6-8030-30b9adb7f40c"  # 👈 본인의 웹소켓 접속키 입력

# --- API & Websocket URL ---
BASE_URL = "https://openapivts.koreainvestment.com:29443"  # 모의투자 서버
WS_URL = "ws://ops.koreainvestment.com:21000"  # 모의투자 웹소켓 서버
# 실전투자 시 URL을 변경해야 합니다.

# --- 매매 대상 종목 정보 ---
STOCK_CODE = "102780"  # KODEX 삼성그룹
STOCK_NAME = "KODEX 삼성그룹"

# ==============================================================================
# ========== 전역 변수 (Global Variables) ==========
# ==============================================================================
# 실시간 시세 데이터를 저장할 딕셔너리
realtime_data = {
    "nav": None,
    "current_price": None,
    "nav_time": None,
    "price_time": None
}

# 현재 포지션 상태 ("none": 미보유, "holding": 보유)
# 스크립트 시작 시 보유 잔고를 조회하여 초기화됩니다.
position = "none"

# API 접근 토큰
ACCESS_TOKEN = None

# ==============================================================================
# ========== 1. 한국투자증권 REST API (매매 및 조회) ==========
# ==============================================================================
def get_access_token():
    """OAuth 인증을 통해 접근 토큰을 발급받습니다."""
    global ACCESS_TOKEN
    url = f"{BASE_URL}/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    data = {
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET
    }
    response = requests.post(url, headers=headers, data=json.dumps(data))
    if response.status_code == 200:
        ACCESS_TOKEN = response.json()["access_token"]
        print("✅ 접근 토큰 발급 성공")
        return True
    else:
        print(f"❌ 접근 토큰 발급 실패: {response.text}")
        return False

def run_trading_logic():
    """1초마다 NAV와 현재가를 비교하여 매매 조건을 확인하고 실행하는 함수"""
    global position
    
    while True:
        time.sleep(1) # 1초 대기
        
        nav = realtime_data.get("nav")
        price = realtime_data.get("current_price")
        
        # 현재 상태 출력
        now_str = datetime.now().strftime('%H:%M:%S')
        print(f"\n[{now_str}] 현재 포지션: {position.upper()}")
        print(f"  - NAV      : {nav if nav is not None else '수신 대기 중...'}")
        print(f"  - 현재가   : {price if price is not None else '수신 대기 중...'}")
        
        # NAV와 현재가 데이터가 모두 수신된 경우에만 로직 실행
        if nav is not None and price is not None:
            diff = nav - price
            print(f"  - 괴리율   : {diff:+.2f} 원")

            # --- 매수 조건 ---
            if diff >= 15 and position == "none":
                print("  >> 매수 신호 발생 (NAV - 현재가 >= 15)")
                # 변경: trading__funtrading_function.buy_etf 사용 (인자 전달)
                result = buy_etf(
                    ACCESS_TOKEN, BASE_URL, APP_KEY, APP_SECRET, ACCOUNT_NO,
                    STOCK_CODE, 1, STOCK_NAME
                )
                if result and result.get("rt_cd") == "0":
                    position = "holding"

            # --- 매도 조건 ---
            elif diff < 0 and position == "holding":
                print("  >> 매도 신호 발생 (NAV - 현재가 < 0)")
                result = sell_etf(
                    ACCESS_TOKEN, BASE_URL, APP_KEY, APP_SECRET, ACCOUNT_NO,
                    STOCK_CODE, 1, STOCK_NAME
                )
                if result and result.get("rt_cd") == "0":
                    position = "none"

def get_initial_balance(stock_code):
    """스크립트 시작 시 보유 잔고를 확인하여 포지션 상태를 설정합니다."""
    global position
    print("--- 초기 보유 잔고 확인 중... ---")
    path = "/uapi/domestic-stock/v1/trading/inquire-balance"
    url = f"{BASE_URL}{path}"
    
    cano, acnt_prdt_cd = ACCOUNT_NO.split('-')

    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {ACCESS_TOKEN}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "VTTC8434R",  # 모의투자 잔고조회
    }
    params = {
        "CANO": cano,
        "ACNT_PRDT_CD": acnt_prdt_cd,
        "AFHR_FLPR_YN": "N",
        "OFL_YN": "",
        "INQR_DVSN": "02",
        "UNPR_DVSN": "01",
        "FUND_STTL_ICLD_YN": "N",
        "FNCG_AMT_AUTO_RDPT_YN": "N",
        "PRCS_DVSN": "01",
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": ""
    }
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        data = response.json()
        if data["rt_cd"] == "0":
            stocks = data["output1"]
            found = False
            for stock in stocks:
                if stock["pdno"] == stock_code:
                    quantity = int(stock["hldg_qty"])
                    if quantity > 0:
                        position = "holding"
                        print(f"✅ 초기 잔고 확인: {STOCK_NAME} {quantity}주 보유 중. (포지션: holding)")
                    found = True
                    break
            if not found:
                position = "none"
                print(f"✅ 초기 잔고 확인: {STOCK_NAME} 미보유. (포지션: none)")
        else:
            print(f"❌ 잔고 조회 실패: {data['msg1']}")
    else:
        print(f"❌ 잔고 조회 API 호출 실패: {response.text}")


# ==============================================================================
# ========== 2. 한국투자증권 Websocket (실시간 시세) ==========
# ==============================================================================
def on_message(ws, message):
    """웹소켓 메시지 수신 시 호출되는 함수"""
    global realtime_data
    try:
        if message == "PINGPONG":
            ws.pong(message)
            return

        if message.startswith('0|') or message.startswith('1|'):
            parts = message.split('|')
            tr_id = parts[1]
            data_str = parts[3]

            if tr_id == "H0STNAV0":  # 실시간 ETF NAV
                fields = data_str.split('^')
                if len(fields) > 1:
                    realtime_data["nav"] = float(fields[1])
                    realtime_data["nav_time"] = datetime.now().strftime("%H:%M:%S")

            elif tr_id == "H0STCNT0":  # 실시간 주식 체결가
                fields = data_str.split('^')
                if len(fields) > 2:
                    realtime_data["current_price"] = int(fields[2])
                    realtime_data["price_time"] = datetime.now().strftime("%H:%M:%S")

        elif message.startswith('{'):
            msg_json = json.loads(message)
            if msg_json.get('header', {}).get('tr_id'):
                print(f"[응답] {msg_json['header']['tr_id']} - {msg_json['msg1']}")

    except Exception as e:
        print(f"메시지 처리 오류: {e} | 원본 메시지: {message}")

def on_error(ws, error):
    print(f"[오류] {error}")

def on_close(ws, close_status_code, close_msg):
    print("[웹소켓 연결 종료]")

def on_open(ws):
    """웹소켓 연결 성공 시, 실시간 데이터 구독 요청"""
    print("[웹소켓 연결 성공] 실시간 시세 구독을 요청합니다.")
    # NAV 구독 요청
    nav_subscribe = {
        "header": {"approval_key": APPROVAL_KEY, "custtype": "P", "tr_type": "1", "content-type": "utf-8"},
        "body": {"input": {"tr_id": "H0STNAV0", "tr_key": STOCK_CODE}}
    }
    # 현재가 구독 요청
    price_subscribe = {
        "header": {"approval_key": APPROVAL_KEY, "custtype": "P", "tr_type": "1", "content-type": "utf-8"},
        "body": {"input": {"tr_id": "H0STCNT0", "tr_key": STOCK_CODE}}
    }
    ws.send(json.dumps(nav_subscribe))
    time.sleep(0.5)
    ws.send(json.dumps(price_subscribe))

# ==============================================================================
# ========== 3. 매매 로직 실행 (Trading Logic) ==========
# ==============================================================================
def run_trading_logic():
    """1초마다 NAV와 현재가를 비교하여 매매 조건을 확인하고 실행하는 함수"""
    global position
    
    while True:
        time.sleep(1) # 1초 대기
        
        nav = realtime_data.get("nav")
        price = realtime_data.get("current_price")
        
        # 현재 상태 출력
        now_str = datetime.now().strftime('%H:%M:%S')
        print(f"\n[{now_str}] 현재 포지션: {position.upper()}")
        print(f"  - NAV      : {nav if nav is not None else '수신 대기 중...'}")
        print(f"  - 현재가   : {price if price is not None else '수신 대기 중...'}")
        
        # NAV와 현재가 데이터가 모두 수신된 경우에만 로직 실행
        if nav is not None and price is not None:
            diff = nav - price
            print(f"  - 괴리율   : {diff:+.2f} 원")

            # --- 매수 조건 ---
            # 조건: NAV가 현재가보다 15원 이상 높고, 현재 보유하고 있지 않을 때
            if diff >= 15 and position == "none":
                print("  >> 매수 신호 발생 (NAV - 현재가 >= 100)")
                result = buy_etf(stock_code=STOCK_CODE, quantity=1)
                # 매수 주문 성공 시 포지션 상태 변경
                if result and result.get("rt_cd") == "0":
                    position = "holding"

            # --- 매도 조건 ---
            # 조건: NAV가 현재가보다 낮고 (괴리율 음수), 현재 보유하고 있을 때
            elif diff < 0 and position == "holding":
                print("  >> 매도 신호 발생 (NAV - 현재가 < 0)")
                result = sell_etf(stock_code=STOCK_CODE, quantity=1)
                # 매도 주문 성공 시 포지션 상태 변경
                if result and result.get("rt_cd") == "0":
                    position = "none"

# ==============================================================================
# ========== 4. 메인 프로그램 실행 (Main Execution) ==========
# ==============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("=== 자동 ETF 괴리율 매매 프로그램을 시작합니다 ===")
    print(f"=== 대상 종목: {STOCK_NAME} ({STOCK_CODE}) ===")
    print("=" * 60)
    
    # 1. API 접근 토큰 발급
    if not get_access_token():
        exit() # 토큰 발급 실패 시 프로그램 종료
        
    # 2. 초기 보유 잔고 확인 및 포지션 설정
    get_initial_balance(STOCK_CODE)
    
    # 3. 매매 로직을 별도의 스레드에서 실행
    trading_thread = threading.Thread(target=run_trading_logic, daemon=True)
    trading_thread.start()
    
    # 4. 메인 스레드에서 웹소켓 실행
    ws = websocket.WebSocketApp(
        WS_URL,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open
    )
    ws.run_forever()