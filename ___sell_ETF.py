import requests
import json
import time

# ========== 설정 ==========
# KIS Developers에서 발급받은 정보를 입력하세요
APP_KEY = "PSVP4uaIGfmv9oviIqOjn58WIV3coGzjAEqu"
APP_SECRET = "NYuz2xS/ZFfTnLBa15UsPnU/iFaGMMAQiv/RoB4Xxi2yHOCCY1Zq9IgJARubfjWXzoFUbun4wlG7xhDQyWXIvSaWkK27RkFz8k4TBYpOtNzcRCeW17eBpQ1GULQkqP3AUultGWtcycBDkL/KHcPAga53hK37kM4YcSEsjoZgncVb6yO2DOc="
ACCOUNT_NO = "50154524"
ACCOUNT_PRODUCT_CD = "01"  # 계좌번호 뒤 2자리 (종합계좌: 01)

# API URL
BASE_URL = "https://openapivts.koreainvestment.com:29443"  # 모의투자 서버
# 실전투자 시: "https://openapi.koreainvestment.com:9443"

# API 호출 제한 설정
API_DELAY = 0.2  # 각 API 호출 사이에 0.2초 대기


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
    time.sleep(API_DELAY)
    
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
    time.sleep(API_DELAY)
    
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
    time.sleep(API_DELAY)
    
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


# ========== 4. 보유 종목 잔고 조회 ==========
def get_stock_balance(access_token, stock_code="102780"):
    """
    보유 중인 주식 잔고를 조회합니다.
    """
    url = f"{BASE_URL}/uapi/domestic-stock/v1/trading/inquire-balance"
    
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {access_token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "VTTC8434R",  # 모의투자 잔고조회
        "custtype": "P"  # 개인: P, 법인: B
    }
    
    params = {
        "CANO": ACCOUNT_NO,
        "ACNT_PRDT_CD": ACCOUNT_PRODUCT_CD,
        "AFHR_FLPR_YN": "N",  # 시간외단일가여부
        "OFL_YN": "",  # 오프라인여부
        "INQR_DVSN": "02",  # 조회구분 (01:대출일별, 02:종목별)
        "UNPR_DVSN": "01",  # 단가구분
        "FUND_STTL_ICLD_YN": "N",  # 펀드결제분포함여부
        "FNCG_AMT_AUTO_RDPT_YN": "N",  # 융자금액자동상환여부
        "PRCS_DVSN": "01",  # 처리구분 (00:전일, 01:당일)
        "CTX_AREA_FK100": "",  # 연속조회검색조건100
        "CTX_AREA_NK100": ""  # 연속조회키100
    }
    
    response = requests.get(url, headers=headers, params=params)
    time.sleep(API_DELAY)
    
    if response.status_code == 200:
        data = response.json()
        if data["rt_cd"] == "0":
            stocks = data["output1"]
            
            # 특정 종목 찾기
            for stock in stocks:
                if stock["pdno"] == stock_code:
                    quantity = int(stock["hldg_qty"])  # 보유수량
                    avg_price = stock["pchs_avg_pric"]  # 매입평균가격
                    current_value = stock["evlu_amt"]  # 평가금액
                    profit_loss = stock["evlu_pfls_amt"]  # 평가손익금액
                    profit_rate = stock["evlu_pfls_rt"]  # 수익률
                    
                    print(f"📦 {stock_code} 보유 정보:")
                    print(f"   보유수량: {quantity}주")
                    print(f"   매입평균가: {avg_price}원")
                    print(f"   평가금액: {current_value}원")
                    print(f"   평가손익: {profit_loss}원 ({profit_rate}%)")
                    
                    return {
                        "quantity": quantity,
                        "avg_price": avg_price,
                        "current_value": current_value,
                        "profit_loss": profit_loss,
                        "profit_rate": profit_rate
                    }
            
            print(f"⚠️ {stock_code} 종목을 보유하고 있지 않습니다.")
            return None
        else:
            print(f"❌ 잔고 조회 실패: {data['msg1']}")
            return None
    else:
        print(f"❌ API 호출 실패: {response.text}")
        return None


# ========== 5. 매도 가능 수량 조회 ==========
def get_sellable_quantity(access_token, stock_code="102780"):
    """
    매도 가능한 수량을 조회합니다.
    """
    url = f"{BASE_URL}/uapi/domestic-stock/v1/trading/inquire-psbl-sell"
    
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {access_token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "VTTC8408R",  # 모의투자 매도가능수량조회
        "custtype": "P"  # 개인: P, 법인: B
    }
    
    params = {
        "CANO": ACCOUNT_NO,
        "ACNT_PRDT_CD": ACCOUNT_PRODUCT_CD,
        "PDNO": stock_code,
        "ORD_UNPR": "0",  # 주문단가
        "ORD_DVSN": "01",  # 주문구분 (01:시장가)
        "CMA_EVLU_AMT_ICLD_YN": "N",  # CMA평가금액포함여부
        "OVRS_ICLD_YN": "N"  # 해외포함여부
    }
    
    response = requests.get(url, headers=headers, params=params)
    time.sleep(API_DELAY)
    
    if response.status_code == 200:
        data = response.json()
        if data["rt_cd"] == "0":
            sellable_qty = int(data["output"]["ord_psbl_qty"])  # 주문가능수량
            print(f"💼 매도 가능 수량: {sellable_qty}주")
            return sellable_qty
        else:
            print(f"❌ 매도가능수량 조회 실패: {data['msg1']}")
            return None
    else:
        print(f"❌ API 호출 실패: {response.text}")
        return None


# ========== 6. 주식 매도 주문 ==========
def sell_stock(access_token, stock_code="102780", quantity=1, price=0, order_type="01"):
    """
    주식 매도 주문을 실행합니다.
    
    Args:
        access_token: 접근 토큰
        stock_code: 종목코드 (기본: KODEX 삼성그룹)
        quantity: 주문 수량 (0 또는 빈 문자열: 전량 매도)
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
        "tr_id": "VTTC0801U",  # 모의투자 매도 주문
        "custtype": "P",  # 개인: P
        "hashkey": hashkey
    }
    
    response = requests.post(url, headers=headers, data=json.dumps(data))
    time.sleep(API_DELAY)
    
    if response.status_code == 200:
        result = response.json()
        if result["rt_cd"] == "0":
            print(f"✅ 매도 주문 성공!")
            print(f"   주문번호: {result['output']['ODNO']}")
            print(f"   주문시간: {result['output']['ORD_TMD']}")
            return result
        else:
            print(f"❌ 매도 주문 실패: {result['msg1']}")
            return None
    else:
        print(f"❌ API 호출 실패: {response.text}")
        return None


# ========== 메인 실행 ==========
def main():
    """
    KODEX 삼성그룹 ETF를 모의투자 계좌에서 매도합니다.
    """
    print("=" * 50)
    print("KODEX 삼성그룹 ETF 모의투자 매도 프로그램")
    print("=" * 50)
    
    # 1. 접근 토큰 발급
    access_token = get_access_token()
    if not access_token:
        return
    
    print()
    
    # 2. 현재가 조회
    stock_code = "102780"  # KODEX 삼성그룹
    current_price = get_current_price(access_token, stock_code)
    
    print()
    
    # 3. 보유 종목 잔고 조회
    balance = get_stock_balance(access_token, stock_code)
    
    if not balance:
        print("\n⚠️ 보유 종목이 없어 매도할 수 없습니다.")
        return
    
    print()
    
    # 4. 매도 가능 수량 조회
    sellable_qty = get_sellable_quantity(access_token, stock_code)
    
    print()
    
    # 5. 매도 주문 실행
    # 예시 1: 시장가로 1주 매도
    quantity = 1
    order_type = "01"  # 시장가
    price = 0  # 시장가는 0
    
    print(f"💰 {stock_code} {quantity}주 매도 주문 시작...")
    result = sell_stock(
        access_token=access_token,
        stock_code=stock_code,
        quantity=quantity,
        price=price,
        order_type=order_type
    )
    
    print()
    print("=" * 50)
    
    # 예시 2: 보유 수량 전량 매도 (주석 처리됨)
    # print("\n📌 전량 매도 예시:")
    # sell_stock(
    #     access_token=access_token,
    #     stock_code="102780",
    #     quantity=balance["quantity"],  # 보유 수량 전체
    #     price=0,
    #     order_type="01"  # 시장가
    # )
    
    # 예시 3: 지정가 매도 (주석 처리됨)
    # print("\n📌 지정가 매도 예시:")
    # sell_stock(
    #     access_token=access_token,
    #     stock_code="102780",
    #     quantity=1,
    #     price=16000,  # 원하는 가격 입력
    #     order_type="00"  # 지정가
    # )


if __name__ == "__main__":
    main()