import requests
import json
import hashlib

# ========== 설정 ==========
# KIS Developers에서 발급받은 정보를 입력하세요
APP_KEY = "PSVP4uaIGfmv9oviIqOjn58WIV3coGzjAEqu"
APP_SECRET = "NYuz2xS/ZFfTnLBa15UsPnU/iFaGMMAQiv/RoB4Xxi2yHOCCY1Zq9IgJARubfjWXzoFUbun4wlG7xhDQyWXIvSaWkK27RkFz8k4TBYpOtNzcRCeW17eBpQ1GULQkqP3AUultGWtcycBDkL/KHcPAga53hK37kM4YcSEsjoZgncVb6yO2DOc="
ACCOUNT_NO = "50154524"
ACCOUNT_PRODUCT_CD = "01"  # 계좌번호 뒤 2자리 (종합계좌: 01)

# API URL
BASE_URL = "https://openapivts.koreainvestment.com:29443"  # 모의투자 서버
# 실전투자 시: "https://openapi.koreainvestment.com:9443"

# ========== 1. 접근 토큰 발급 ==========
def get_access_token():
    """
    OAuth 인증을 통해 접근 토큰을 발급받습니다.
    """
    url = f"{BASE_URL}/oauth2/tokenP"
    
    headers = {
        "content-type": "application/json"
    }
    
    data = {
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET
    }
    
    response = requests.post(url, headers=headers, data=json.dumps(data))
    
    if response.status_code == 200:
        access_token = response.json()["access_token"]
        print(f"✅ 접근 토큰 발급 성공")
        return access_token
    else:
        print(f"❌ 접근 토큰 발급 실패: {response.text}")
        return None


# ========== 2. 해시키 생성 (POST 요청 시 필요) ==========
def get_hashkey(data):
    """
    POST 요청 시 필요한 해시키를 생성합니다.
    """
    url = f"{BASE_URL}/uapi/hashkey"
    
    headers = {
        "content-type": "application/json",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET
    }
    
    response = requests.post(url, headers=headers, data=json.dumps(data))
    
    if response.status_code == 200:
        hashkey = response.json()["HASH"]
        return hashkey
    else:
        print(f"❌ 해시키 생성 실패: {response.text}")
        return None


# ========== 3. 현재가 조회 ==========
def get_current_price(access_token, stock_code="102780"):
    """
    종목의 현재가를 조회합니다.
    """
    url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price"
    
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {access_token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "FHKST01010100"  # 주식현재가 시세 조회
    }
    
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",  # 시장 구분 (J: 주식)
        "FID_INPUT_ISCD": stock_code
    }
    
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        data = response.json()
        if data["rt_cd"] == "0":
            current_price = data["output"]["stck_prpr"]  # 현재가
            print(f"📊 {stock_code} 현재가: {current_price}원")
            return current_price
        else:
            print(f"❌ 현재가 조회 실패: {data['msg1']}")
            return None
    else:
        print(f"❌ API 호출 실패: {response.text}")
        return None


# ========== 4. 매수 가능 금액 조회 ==========
def get_buyable_cash(access_token):
    """
    매수 가능한 현금 잔고를 조회합니다.
    """
    url = f"{BASE_URL}/uapi/domestic-stock/v1/trading/inquire-psbl-order"
    
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {access_token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "VTTC8908R",  # 모의투자 매수가능조회
        "custtype": "P"  # 개인: P, 법인: B
    }
    
    params = {
        "CANO": ACCOUNT_NO,
        "ACNT_PRDT_CD": ACCOUNT_PRODUCT_CD,
        "PDNO": "102780",
        "ORD_UNPR": "0",
        "ORD_DVSN": "01",  # 시장가
        "CMA_EVLU_AMT_ICLD_YN": "N",
        "OVRS_ICLD_YN": "N"
    }
    
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        data = response.json()
        if data["rt_cd"] == "0":
            cash = data["output"]["ord_psbl_cash"]
            print(f"💰 매수 가능 금액: {cash}원")
            return int(cash)
        else:
            print(f"❌ 매수가능금액 조회 실패: {data['msg1']}")
            return None
    else:
        print(f"❌ API 호출 실패: {response.text}")
        return None


# ========== 5. 주식 매수 주문 ==========
def buy_stock(access_token, stock_code="102780", quantity=1, price=0, order_type="01"):
    """
    주식 매수 주문을 실행합니다.
    
    Args:
        access_token: 접근 토큰
        stock_code: 종목코드 (기본: KODEX 삼성그룹)
        quantity: 주문 수량
        price: 주문 단가 (0: 시장가, 그 외: 지정가)
        order_type: 주문 구분
            - "00": 지정가
            - "01": 시장가
            - "02": 조건부지정가
            - "03": 최유리지정가
            - "04": 최우선지정가
            - "05": 장전 시간외
            - "06": 장후 시간외
    """
    url = f"{BASE_URL}/uapi/domestic-stock/v1/trading/order-cash"
    
    # POST 요청 데이터
    data = {
        "CANO": ACCOUNT_NO,
        "ACNT_PRDT_CD": ACCOUNT_PRODUCT_CD,
        "PDNO": stock_code,
        "ORD_DVSN": order_type,
        "ORD_QTY": str(quantity),
        "ORD_UNPR": str(price)
    }
    
    # 해시키 생성
    hashkey = get_hashkey(data)
    
    if not hashkey:
        print("❌ 해시키 생성 실패")
        return None
    
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {access_token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "VTTC0802U",  # 모의투자 매수 주문
        "custtype": "P",  # 개인: P
        "hashkey": hashkey
    }
    
    response = requests.post(url, headers=headers, data=json.dumps(data))
    
    if response.status_code == 200:
        result = response.json()
        if result["rt_cd"] == "0":
            print(f"✅ 매수 주문 성공!")
            print(f"   주문번호: {result['output']['ODNO']}")
            print(f"   주문시간: {result['output']['ORD_TMD']}")
            return result
        else:
            print(f"❌ 매수 주문 실패: {result['msg1']}")
            return None
    else:
        print(f"❌ API 호출 실패: {response.text}")
        return None


# ========== 메인 실행 ==========
def main():
    """
    KODEX 삼성그룹 ETF를 모의투자 계좌에서 매수합니다.
    """
    print("=" * 50)
    print("KODEX 삼성그룹 ETF 모의투자 매수 프로그램")
    print("=" * 50)
    
    # 1. 접근 토큰 발급
    access_token = get_access_token()
    if not access_token:
        return
    
    print()
    
    # 2. 현재가 조회
    stock_code = "102780"  # KODEX 삼성그룹
    # current_price = get_current_price(access_token, stock_code)
    
    print()
    
    # 3. 매수 가능 금액 조회
    # buyable_cash = get_buyable_cash(access_token)
    
    print()
    
    # 4. 매수 주문 실행
    # 예시: 시장가로 1주 매수
    quantity = 1
    order_type = "01"  # 시장가
    price = 0  # 시장가는 0
    
    print(f"🛒 {stock_code} {quantity}주 매수 주문 시작...")
    result = buy_stock(
        access_token=access_token,
        stock_code=stock_code,
        quantity=quantity,
        price=price,
        order_type=order_type
    )
    
    print()
    print("=" * 50)
    
    # 지정가 매수 예시 (주석 처리됨)
    # print("\n📌 지정가 매수 예시:")
    # buy_stock(
    #     access_token=access_token,
    #     stock_code="102780",
    #     quantity=1,
    #     price=15000,  # 원하는 가격 입력
    #     order_type="00"  # 지정가
    # )


if __name__ == "__main__":
    main()