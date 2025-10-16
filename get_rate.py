import websockets
import json
import asyncio
import requests
from typing import Dict

# 한국투자증권 API 설정
APP_KEY = "PSVP4uaIGfmv9oviIqOjn58WIV3coGzjAEqu"
APP_SECRET = "NYuz2xS/ZFfTnLBa15UsPnU/iFaGMMAQiv/RoB4Xxi2yHOCCY1Zq9IgJARubfjWXzoFUbun4wlG7xhDQyWXIvSaWkK27RkFz8k4TBYpOtNzcRCeW17eBpQ1GULQkqP3AUultGWtcycBDkL/KHcPAga53hK37kM4YcSEsjoZgncVb6yO2DOc="
ACCOUNT_NO = "50154524"
ACCOUNT_PRODUCT_CD = "01"

# 실전/모의투자 선택
USE_REAL = False  # True: 실전투자, False: 모의투자

if USE_REAL:
    BASE_URL = "https://openapi.koreainvestment.com:9443"
    WS_URL = "ws://ops.koreainvestment.com:21000"
else:
    BASE_URL = "https://openapivts.koreainvestment.com:29443"
    WS_URL = "ws://ops.koreainvestment.com:31000"

# ETF 구성 종목 및 수량
ETF_COMPOSITION = {
    "삼성전자": {"quantity": 3845, "code": "005930"},
    "삼성바이오로직스": {"quantity": 119, "code": "207940"},
    "삼성물산": {"quantity": 601, "code": "028260"},
    "삼성화재": {"quantity": 202, "code": "000810"},
    "삼성중공업": {"quantity": 4341, "code": "010140"},
    "삼성생명": {"quantity": 560, "code": "032830"},
    "삼성SDI": {"quantity": 391, "code": "006400"},
    "삼성전기": {"quantity": 363, "code": "009150"},
    "삼성에스디에스": {"quantity": 253, "code": "018260"},
    "삼성증권": {"quantity": 405, "code": "016360"},
    "삼성E&A": {"quantity": 1006, "code": "028050"},
    "에스원": {"quantity": 160, "code": "012750"},
    "호텔신라": {"quantity": 201, "code": "008770"},
    "제일기획": {"quantity": 452, "code": "030000"},
    "삼성카드": {"quantity": 154, "code": "029780"}
}

# 현재가 저장용 딕셔너리
current_prices: Dict[str, float] = {}


def get_access_token():
    """접근 토큰 발급"""
    url = f"{BASE_URL}/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    data = {
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET
    }
    
    response = requests.post(url, headers=headers, data=json.dumps(data))
    result = response.json()
    return result["access_token"]


def get_approval_key(access_token):
    """웹소켓 접속키 발급"""
    url = f"{BASE_URL}/oauth2/Approval"
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {access_token}"
    }
    data = {
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "secretkey": APP_SECRET
    }
    
    response = requests.post(url, headers=headers, data=json.dumps(data))
    result = response.json()
    return result["approval_key"]


async def subscribe_stock(websocket, stock_code, tr_key="1"):
    """종목 실시간 시세 구독"""
    subscribe_data = {
        "header": {
            "approval_key": approval_key,
            "custtype": "P",
            "tr_type": tr_key,  # 1: 등록, 2: 해제
            "content-type": "utf-8"
        },
        "body": {
            "input": {
                "tr_id": "H0STCNT0",  # 주식 현재가 실시간
                "tr_key": stock_code
            }
        }
    }
    
    await websocket.send(json.dumps(subscribe_data))
    print(f"✓ {stock_code} 구독 요청 완료")


def parse_stock_data(data):
    """실시간 데이터 파싱"""
    try:
        # 데이터 형식: "0|H0STCNT0|stock_code|data..."
        parts = data.split("|")
        
        if len(parts) < 4:
            return None
        
        stock_code = parts[2]
        data_parts = parts[3].split("^")
        
        if len(data_parts) < 3:
            return None
        
        # 현재가는 세 번째 필드
        current_price = int(data_parts[2])
        
        return stock_code, current_price
    
    except Exception as e:
        print(f"데이터 파싱 오류: {e}")
        return None


def display_etf_value():
    """ETF 구성 종목의 현재 가치 표시"""
    print("\n" + "="*80)
    print("Kodex 삼성그룹 ETF 구성 종목 실시간 평가")
    print("="*80)
    
    total_value = 0
    
    for name, info in ETF_COMPOSITION.items():
        code = info["code"]
        quantity = info["quantity"]
        price = current_prices.get(code, 0)
        value = price * quantity
        total_value += value
        
        print(f"{name:15s} | 종목코드: {code} | 현재가: {price:>8,}원 | "
              f"수량: {quantity:>5,}주 | 평가금액: {value:>12,}원")
    
    print("="*80)
    print(f"ETF 1주당 총 평가금액: {total_value:>12,}원")
    print("="*80 + "\n")


async def receive_data(websocket):
    """실시간 데이터 수신"""
    while True:
        try:
            data = await websocket.recv()
            
            # PINGPONG 처리
            if data == "PINGPONG":
                await websocket.pong()
                continue
            
            # 데이터 파싱
            result = parse_stock_data(data)
            
            if result:
                stock_code, current_price = result
                current_prices[stock_code] = current_price
                
                # 종목명 찾기
                stock_name = None
                for name, info in ETF_COMPOSITION.items():
                    if info["code"] == stock_code:
                        stock_name = name
                        break
                
                if stock_name:
                    quantity = ETF_COMPOSITION[stock_name]["quantity"]
                    value = current_price * quantity
                    print(f"[업데이트] {stock_name}: {current_price:,}원 → 평가금액: {value:,}원")
                    
                    # 모든 종목의 가격이 수신되면 전체 평가 표시
                    if len(current_prices) == len(ETF_COMPOSITION):
                        display_etf_value()
        
        except websockets.exceptions.ConnectionClosed:
            print("WebSocket 연결이 종료되었습니다.")
            break
        except Exception as e:
            print(f"오류 발생: {e}")


async def main():
    """메인 함수"""
    global approval_key
    
    print("한국투자증권 API 인증 중...")
    access_token = get_access_token()
    print("✓ Access Token 발급 완료")
    
    approval_key = get_approval_key(access_token)
    print("✓ Approval Key 발급 완료")
    
    print(f"\nWebSocket 연결 중: {WS_URL}")
    
    async with websockets.connect(WS_URL, ping_interval=None) as websocket:
        print("✓ WebSocket 연결 완료\n")
        
        # 모든 종목 구독
        print("ETF 구성 종목 구독 중...")
        for name, info in ETF_COMPOSITION.items():
            await subscribe_stock(websocket, info["code"])
            await asyncio.sleep(0.1)  # API 호출 제한 방지
        
        print("\n실시간 데이터 수신 시작...\n")
        
        # 데이터 수신
        await receive_data(websocket)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다.")