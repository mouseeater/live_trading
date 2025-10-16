import requests
import json

def get_hashkey(data, base_url, app_key, app_secret):
    """POST 요청시 필요한 해시키 생성"""
    url = f"{base_url}/uapi/hashkey"
    headers = {
        "content-type": "application/json",
        "appkey": app_key,
        "appsecret": app_secret,
    }
    response = requests.post(url, headers=headers, data=json.dumps(data))
    if response.status_code == 200:
        return response.json().get("HASH")
    else:
        print(f"❌ 해시키 생성 실패: {response.text}")
        return None

# --------------------------------------------------------------
def buy_etf(access_token, base_url, app_key, app_secret, account_no, stock_code, quantity, stock_name, tr_id="VTTC0802U"):
    """시장가 매수 주문 (모듈화된 함수)"""
    print(f"\n>>>> 🛒 {stock_name} {quantity}주 시장가 매수 주문 실행!")
    path = "/uapi/domestic-stock/v1/trading/order-cash"
    url = f"{base_url}{path}"

    try:
        cano, acnt_prdt_cd = account_no.split('-')
    except Exception:
        print("❌ ACCOUNT_NO 포맷 오류 (예: '50154524-01')")
        return None

    data = {
        "CANO": cano,
        "ACNT_PRDT_CD": acnt_prdt_cd,
        "PDNO": stock_code,
        "ORD_DVSN": "01",  # 01: 시장가
        "ORD_QTY": str(quantity),
        "ORD_UNPR": "0",
    }

    hashkey = get_hashkey(data, base_url, app_key, app_secret)
    if not hashkey:
        return None

    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {access_token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": tr_id,
        "custtype": "P",
        "hashkey": hashkey
    }

    response = requests.post(url, headers=headers, data=json.dumps(data))
    if response.status_code == 200:
        result = response.json()
        if result.get("rt_cd") == "0":
            odno = result.get("output", {}).get("ODNO")
            print(f"✅ 매수 주문 성공! (주문번호: {odno})")
        else:
            print(f"❌ 매수 주문 실패: {result.get('msg1')}")
        return result
    else:
        print(f"❌ 매수 API 호출 실패: {response.text}")
        return None

# --------------------------------------------------------------
def sell_etf(access_token, base_url, app_key, app_secret, account_no, stock_code, quantity, stock_name, tr_id="VTTC0801U"):
    """시장가 매도 주문 (모듈화된 함수)"""
    print(f"\n>>>> 💰 {stock_name} {quantity}주 시장가 매도 주문 실행!")
    path = "/uapi/domestic-stock/v1/trading/order-cash"
    url = f"{base_url}{path}"

    try:
        cano, acnt_prdt_cd = account_no.split('-')
    except Exception:
        print("❌ ACCOUNT_NO 포맷 오류 (예: '50154524-01')")
        return None

    data = {
        "CANO": cano,
        "ACNT_PRDT_CD": acnt_prdt_cd,
        "PDNO": stock_code,
        "ORD_DVSN": "01",  # 01: 시장가
        "ORD_QTY": str(quantity),
        "ORD_UNPR": "0",
    }

    hashkey = get_hashkey(data, base_url, app_key, app_secret)
    if not hashkey:
        return None

    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {access_token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": tr_id,
        "custtype": "P",
        "hashkey": hashkey
    }

    response = requests.post(url, headers=headers, data=json.dumps(data))
    if response.status_code == 200:
        result = response.json()
        if result.get("rt_cd") == "0":
            odno = result.get("output", {}).get("ODNO")
            print(f"✅ 매도 주문 성공! (주문번호: {odno})")
        else:
            print(f"❌ 매도 주문 실패: {result.get('msg1')}")
        return result
    else:
        print(f"❌ 매도 API 호출 실패: {response.text}")
        return None