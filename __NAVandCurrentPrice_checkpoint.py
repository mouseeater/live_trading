import websocket
import json
import time
import threading
from datetime import datetime

# 한국투자증권 웹소켓 설정
WS_URL = "ws://ops.koreainvestment.com:21000"  # 실전투자
APPROVAL_KEY = "a34f9329-c5ef-47b6-8030-30b9adb7f40c"  # 발급받은 접속키
APP_KEY = "PSAsNVY3hSJlNja9Syj4Q2JPAVQVBS6gfmGF"  # 본인의 APP KEY 입력
APP_SECRET = "IKYQPBpDdEOAMXJnbpcXViuQVAYz5/08dY/hDMayaOpQ1at0MogvxPmQct6q9wGTI8xELisqCVLJSp9SFM9QO2vYmDkkDlyuC5TTqywqA52mUyJzyxKA0uzHntRxCqq5g+6R884aKHexSWDflQhNgigiI7c/Dzvco2RSccHcEwDCRPK81fY="  # 본인의 APP SECRET 입력

# 종목 정보
STOCK_CODE = "102780"  # KODEX 삼성그룹

# 실시간 데이터 저장
realtime_data = {
    "nav": None,
    "current_price": None,
    "nav_time": None,
    "price_time": None
}

def on_message(ws, message):
    """웹소켓 메시지 수신 처리 (수정된 버전)"""
    global realtime_data  # 👈 1. 전역 변수 realtime_data를 사용하겠다고 선언!

    try:
        # PING/PONG 처리 (API 서버와의 연결 유지를 위해 필요)
        if message == "PINGPONG":
            ws.pong(message)
            return

        # 암호화되지 않은 일반 메시지만 처리
        if message.startswith('0|') or message.startswith('1|'):
            parts = message.split('|')
            tr_id = parts[1]
            data_str = parts[3]

            # 실시간 ETF NAV (H0STNAV0)
            if tr_id == "H0STNAV0":
                fields = data_str.split('^')
                if len(fields) > 1:
                    # 👈 2. NAV 값은 두 번째 필드(인덱스 1)에 있습니다.
                    nav_value = fields[1]
                    realtime_data["nav"] = float(nav_value)
                    realtime_data["nav_time"] = datetime.now().strftime("%H:%M:%S")

            # 실시간 주식 체결가 (H0STCNT0)
            elif tr_id == "H0STCNT0":
                fields = data_str.split('^')
                if len(fields) > 2:
                    current_price = fields[2]  # 현재가는 3번째 필드 (인덱스 2) - 올바름
                    realtime_data["current_price"] = int(current_price)
                    realtime_data["price_time"] = datetime.now().strftime("%H:%M:%S")

        # JSON 형태의 응답 메시지 (구독 성공/실패 등)
        elif message.startswith('{'):
            try:
                msg_json = json.loads(message)
                if msg_json.get('header', {}).get('tr_id'):
                    print(f"[응답] {msg_json['header']['tr_id']} - {msg_json['msg1']}")
            except json.JSONDecodeError:
                print(f"[시스템] 수신 메시지 (JSON 아님): {message}")

    except Exception as e:
        print(f"메시지 처리 오류: {e} | 원본 메시지: {message}")

def on_error(ws, error):
    """에러 처리"""
    print(f"[오류] {error}")

def on_close(ws, close_status_code, close_msg):
    """연결 종료 처리"""
    print("[연결 종료]")

def on_open(ws):
    """웹소켓 연결 시 구독 요청"""
    print("[웹소켓 연결 성공]")
    
    # NAV 구독 요청
    nav_subscribe = {
        "header": {
            "approval_key": APPROVAL_KEY,
            "custtype": "P",
            "tr_type": "1",
            "content-type": "utf-8"
        },
        "body": {
            "input": {
                "tr_id": "H0STNAV0",
                "tr_key": STOCK_CODE
            }
        }
    }
    
    # 현재가 구독 요청
    price_subscribe = {
        "header": {
            "approval_key": APPROVAL_KEY,
            "custtype": "P",
            "tr_type": "1",
            "content-type": "utf-8"
        },
        "body": {
            "input": {
                "tr_id": "H0STCNT0",
                "tr_key": STOCK_CODE
            }
        }
    }
    
    # NAV 구독
    ws.send(json.dumps(nav_subscribe))
    print(f"[구독 요청] NAV (H0STNAV0) - {STOCK_CODE}")
    time.sleep(0.5)
    
    # 현재가 구독
    ws.send(json.dumps(price_subscribe))
    print(f"[구독 요청] 현재가 (H0STCNT0) - {STOCK_CODE}")

def print_data():
    """1초마다 데이터 출력"""
    while True:
        time.sleep(1)
        nav = realtime_data.get("nav", "N/A")
        price = realtime_data.get("current_price", "N/A")
        nav_time = realtime_data.get("nav_time", "-")
        price_time = realtime_data.get("price_time", "-")
        
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] KODEX 삼성그룹 (102780)")
        print(f"  NAV: {nav} (수신: {nav_time})")
        print(f"  현재가: {price} (수신: {price_time})")
        print("-" * 50)

def main():
    """메인 실행 함수"""
    # 데이터 출력 스레드 시작
    print_thread = threading.Thread(target=print_data, daemon=True)
    print_thread.start()
    
    # 웹소켓 연결
    ws = websocket.WebSocketApp(
        WS_URL,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open
    )
    
    print("=" * 50)
    print("KODEX 삼성그룹 실시간 NAV & 현재가 수신 시작")
    print("=" * 50)
    
    # 웹소켓 실행
    ws.run_forever()

if __name__ == "__main__":
    main()