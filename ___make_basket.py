import mojito
import json
import time
import threading
from typing import Dict, List, Tuple
from queue import Queue
import websocket

class SamsungETFBasketTrader:
    """Kodex 삼성그룹 ETF 바스켓 매수 클래스 (웹소켓 + REST API)"""
    
    def __init__(self, key: str, secret: str, acc_no: str, 
                 total_investment_amount: int, mock: bool = True):
        """
        Args:
            key: API Key
            secret: API Secret
            acc_no: 계좌번호
            total_investment_amount: 총 투자금액 (원)
            mock: 모의투자 여부
        """
        self.broker = mojito.KoreaInvestment(
            api_key=key,
            api_secret=secret,
            acc_no=acc_no,
            mock=mock
        )
        self.api_key = key
        self.api_secret = secret
        self.total_investment = total_investment_amount
        self.mock = mock
        
        # ETF 구성종목
        self.constituents = [
            "삼성E&A", "삼성SDI", "삼성물산", "삼성바이오로직스", 
            "삼성생명", "삼성에스디에스", "삼성전기", "삼성전자",
            "삼성중공업", "삼성증권", "삼성카드", "삼성화재",
            "에스원", "제일기획", "호텔신라"
        ]
        
        # 종목코드 매핑
        self.stock_codes = {
            "삼성전자": "005930",
            "삼성바이오로직스": "207940",
            "삼성SDI": "006400",
            "삼성물산": "028260",
            "삼성전기": "009150",
            "삼성생명": "032830",
            "삼성화재": "000810",
            "삼성에스디에스": "018260",
            "호텔신라": "008770",
            "삼성증권": "016360",
            "삼성카드": "029780",
            "삼성E&A": "028050",
            "제일기획": "030000",
            "에스원": "012750",
            "삼성중공업": "010140"
        }
        
        # 실시간 시세 저장소
        self.realtime_prices = {}
        self.price_ready = threading.Event()
        self.ws = None
        self.ws_approval_key = None
        
    def get_composition_ratios(self) -> Dict[str, float]:
        """ETF 구성비율 반환 (외부 구현 가정)"""
        raise NotImplementedError("구성비율 조회 함수를 구현해야 합니다")
    
    def get_websocket_approval_key(self) -> str:
        """웹소켓 접속키 발급"""
        try:
            url = "https://openapi.koreainvestment.com:9443" if not self.mock else \
                  "https://openapivts.koreainvestment.com:29443"
            
            import requests
            headers = {
                "content-type": "application/json"
            }
            body = {
                "grant_type": "client_credentials",
                "appkey": self.api_key,
                "secretkey": self.api_secret
            }
            
            response = requests.post(
                f"{url}/oauth2/Approval",
                headers=headers,
                data=json.dumps(body)
            )
            
            if response.status_code == 200:
                approval_key = response.json()['approval_key']
                print(f"✅ 웹소켓 접속키 발급 완료: {approval_key[:20]}...")
                return approval_key
            else:
                raise Exception(f"접속키 발급 실패: {response.text}")
                
        except Exception as e:
            print(f"❌ 웹소켓 접속키 발급 오류: {e}")
            raise
    
    def on_message(self, ws, message):
        """웹소켓 메시지 수신 처리"""
        try:
            if message.startswith("0|"):  # PINGPONG
                ws.send("1|")  # PONG 응답
                return
            
            # 실시간 시세 데이터 파싱
            tokens = message.split("|")
            if len(tokens) >= 4:
                recv_type = tokens[0]
                
                # 실시간 체결가 (H0STCNT0)
                if recv_type == "0" or recv_type == "1":
                    data = tokens[3]
                    
                    # 데이터 파싱 (고정길이 형식)
                    stock_code = data[0:6]
                    current_price = int(data[38:48].strip())
                    
                    # 종목명 찾기
                    stock_name = None
                    for name, code in self.stock_codes.items():
                        if code == stock_code:
                            stock_name = name
                            break
                    
                    if stock_name:
                        self.realtime_prices[stock_name] = current_price
                        print(f"📊 {stock_name:15s} | {stock_code} | {current_price:,}원")
                        
                        # 모든 종목의 시세가 수신되었는지 확인
                        if len(self.realtime_prices) == len(self.constituents):
                            print(f"\n✅ 전체 {len(self.constituents)}개 종목 시세 수신 완료!\n")
                            self.price_ready.set()
                            
        except Exception as e:
            print(f"⚠️ 메시지 처리 오류: {e}")
    
    def on_error(self, ws, error):
        """웹소켓 에러 처리"""
        print(f"❌ 웹소켓 에러: {error}")
    
    def on_close(self, ws, close_status_code, close_msg):
        """웹소켓 종료 처리"""
        print(f"🔌 웹소켓 연결 종료: {close_status_code} - {close_msg}")
    
    def on_open(self, ws):
        """웹소켓 연결 시작"""
        print("🔗 웹소켓 연결 성공")
        print(f"📡 {len(self.constituents)}개 종목 실시간 시세 구독 시작...\n")
        
        # 각 종목에 대해 실시간 체결가 구독
        for stock_name in self.constituents:
            stock_code = self.stock_codes[stock_name]
            
            subscribe_data = {
                "header": {
                    "approval_key": self.ws_approval_key,
                    "custtype": "P",
                    "tr_type": "1",  # 등록
                    "content-type": "utf-8"
                },
                "body": {
                    "input": {
                        "tr_id": "H0STCNT0",  # 실시간 체결가
                        "tr_key": stock_code
                    }
                }
            }
            
            ws.send(json.dumps(subscribe_data))
            time.sleep(0.05)  # 구독 요청 간 딜레이
    
    def start_websocket(self):
        """웹소켓 시작"""
        try:
            # 접속키 발급
            self.ws_approval_key = self.get_websocket_approval_key()
            
            # 웹소켓 URL
            ws_url = "ws://ops.koreainvestment.com:21000" if not self.mock else \
                     "ws://ops.koreainvestment.com:31000"
            
            # 웹소켓 연결
            self.ws = websocket.WebSocketApp(
                ws_url,
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close,
                on_open=self.on_open
            )
            
            # 별도 스레드에서 웹소켓 실행
            ws_thread = threading.Thread(target=self.ws.run_forever)
            ws_thread.daemon = True
            ws_thread.start()
            
            print("⏳ 실시간 시세 수신 대기 중...\n")
            
        except Exception as e:
            print(f"❌ 웹소켓 시작 오류: {e}")
            raise
    
    def stop_websocket(self):
        """웹소켓 종료"""
        if self.ws:
            # 모든 종목 구독 해제
            for stock_name in self.constituents:
                stock_code = self.stock_codes[stock_name]
                
                unsubscribe_data = {
                    "header": {
                        "approval_key": self.ws_approval_key,
                        "custtype": "P",
                        "tr_type": "2",  # 해제
                        "content-type": "utf-8"
                    },
                    "body": {
                        "input": {
                            "tr_id": "H0STCNT0",
                            "tr_key": stock_code
                        }
                    }
                }
                
                self.ws.send(json.dumps(unsubscribe_data))
                time.sleep(0.05)
            
            self.ws.close()
            print("\n🔌 웹소켓 연결 종료")
    
    def calculate_quantities(self, 
                            composition_ratios: Dict[str, float]) -> List[Tuple[str, str, int, int, int]]:
        """
        실시간 시세를 이용한 매수 수량 계산
        """
        basket_info = []
        
        print("[수량 계산 시작]")
        print("-" * 80)
        
        for stock_name in self.constituents:
            stock_code = self.stock_codes[stock_name]
            
            # 웹소켓으로 받은 실시간 시세 사용
            current_price = self.realtime_prices.get(stock_name, 0)
            
            if current_price == 0:
                print(f"⚠️ {stock_name}: 시세 정보 없음 (스킵)")
                continue
            
            # 투자금액 계산
            ratio = composition_ratios.get(stock_name, 0) / 100
            investment_amount = int(self.total_investment * ratio)
            
            # 매수 수량 계산
            quantity = investment_amount // current_price
            actual_amount = quantity * current_price
            
            basket_info.append((
                stock_name,
                stock_code,
                current_price,
                quantity,
                actual_amount
            ))
            
            print(f"{stock_name:15s} | {stock_code} | "
                  f"현재가: {current_price:,}원 | "
                  f"비율: {composition_ratios.get(stock_name, 0):.2f}% | "
                  f"수량: {quantity:,}주 | "
                  f"금액: {actual_amount:,}원")
        
        return basket_info
    
    def execute_basket_order(self, 
                            basket_info: List[Tuple[str, str, int, int, int]],
                            order_delay: float = 0.2) -> Dict:
        """
        REST API를 통한 바스켓 주문 실행
        
        Args:
            basket_info: 매수 정보
            order_delay: 주문 간 딜레이 (초)
        """
        order_results = {
            "success": [],
            "failed": [],
            "total_ordered_amount": 0
        }
        
        print("\n[주문 실행 시작]")
        print("-" * 80)
        
        for stock_name, stock_code, current_price, quantity, _ in basket_info:
            if quantity == 0:
                print(f"⏭️ {stock_name}: 매수 수량 0주 (스킵)")
                continue
            
            try:
                # REST API로 시장가 매수 주문
                resp = self.broker.create_market_buy_order(
                    symbol=stock_code,
                    quantity=quantity
                )
                
                if resp.get('rt_cd') == '0':
                    order_no = resp.get('output', {}).get('ODNO', '')
                    order_results["success"].append({
                        "stock_name": stock_name,
                        "stock_code": stock_code,
                        "quantity": quantity,
                        "price": current_price,
                        "order_no": order_no
                    })
                    order_results["total_ordered_amount"] += (quantity * current_price)
                    print(f"✅ {stock_name:15s} | {quantity:,}주 매수 주문 완료 (주문번호: {order_no})")
                else:
                    error_msg = resp.get('msg1', '알 수 없는 오류')
                    order_results["failed"].append({
                        "stock_name": stock_name,
                        "stock_code": stock_code,
                        "error": error_msg
                    })
                    print(f"❌ {stock_name:15s} | 주문 실패: {error_msg}")
                
                # API 호출 제한 방지를 위한 딜레이
                time.sleep(order_delay)
                
            except Exception as e:
                order_results["failed"].append({
                    "stock_name": stock_name,
                    "stock_code": stock_code,
                    "error": str(e)
                })
                print(f"⚠️ {stock_name:15s} | 주문 오류: {e}")
        
        return order_results
    
    def create_basket(self, 
                     composition_ratios: Dict[str, float],
                     timeout: int = 60,
                     order_delay: float = 0.2) -> Dict:
        """
        ETF 바스켓 생성 (웹소켓 + REST API)
        
        Args:
            composition_ratios: 구성비율
            timeout: 시세 수신 대기 시간 (초)
            order_delay: 주문 간 딜레이 (초)
        """
        print("=" * 80)
        print("Kodex 삼성그룹 ETF 바스켓 매수 시작")
        print("=" * 80)
        print(f"💰 총 투자금액: {self.total_investment:,}원")
        print(f"📊 전략: 웹소켓 실시간 시세 + REST API 주문")
        print(f"🎯 대상 종목: {len(self.constituents)}개")
        print("=" * 80)
        print()
        
        try:
            # 1. 웹소켓 시작 및 실시간 시세 수신
            print("[1단계] 웹소켓 실시간 시세 수신")
            print("-" * 80)
            self.start_websocket()
            
            # 모든 종목의 시세가 수신될 때까지 대기
            if not self.price_ready.wait(timeout=timeout):
                print(f"⚠️ {timeout}초 내에 모든 시세를 받지 못했습니다.")
                print(f"   수신된 종목: {len(self.realtime_prices)}/{len(self.constituents)}")
            
            # 2. 매수 수량 계산
            print("\n[2단계] 종목별 매수 수량 계산")
            print("-" * 80)
            basket_info = self.calculate_quantities(composition_ratios)
            
            # 총 투자금액 확인
            total_calculated = sum(amount for _, _, _, _, amount in basket_info)
            print(f"\n💵 계산된 총 매수금액: {total_calculated:,}원")
            print(f"📊 실제 투자금액 대비: {total_calculated / self.total_investment * 100:.2f}%")
            
            # 3. REST API로 주문 실행
            print("\n[3단계] REST API 주문 실행")
            print("-" * 80)
            order_results = self.execute_basket_order(basket_info, order_delay=order_delay)
            
            # 4. 웹소켓 종료
            self.stop_websocket()
            
            # 5. 결과 요약
            print("\n" + "=" * 80)
            print("📋 주문 결과 요약")
            print("=" * 80)
            print(f"✅ 성공: {len(order_results['success'])}건")
            print(f"❌ 실패: {len(order_results['failed'])}건")
            print(f"💰 총 주문금액: {order_results['total_ordered_amount']:,}원")
            
            if order_results['failed']:
                print("\n실패 종목 상세:")
                for failed in order_results['failed']:
                    print(f"  - {failed['stock_name']}: {failed['error']}")
            
            print("=" * 80)
            
            return order_results
            
        except Exception as e:
            print(f"\n❌ 바스켓 생성 중 오류 발생: {e}")
            self.stop_websocket()
            raise


# 사용 예시
if __name__ == "__main__":
    # API 인증 정보
    API_KEY = "YOUR_API_KEY"
    API_SECRET = "YOUR_API_SECRET"
    ACCOUNT_NO = "YOUR_ACCOUNT_NUMBER"
    
    # 바스켓 트레이더 초기화
    trader = SamsungETFBasketTrader(
        key="PSVP4uaIGfmv9oviIqOjn58WIV3coGzjAEqu",
        secret="NYuz2xS/ZFfTnLBa15UsPnU/iFaGMMAQiv/RoB4Xxi2yHOCCY1Zq9IgJARubfjWXzoFUbun4wlG7xhDQyWXIvSaWkK27RkFz8k4TBYpOtNzcRCeW17eBpQ1GULQkqP3AUultGWtcycBDkL/KHcPAga53hK37kM4YcSEsjoZgncVb6yO2DOc=",
        acc_no="50154524-01",
        total_investment_amount=10_000_000,  # 1천만원
        mock=True  # 모의투자
    )
    
    # 구성비율 (예시 - 실제로는 get_composition_ratios() 구현 필요)
    composition_ratios = {
        "삼성전자": 60.0,
        "삼성바이오로직스": 10.0,
        "삼성SDI": 5.0,
        "삼성물산": 4.0,
        "삼성전기": 3.5,
        "삼성생명": 3.0,
        "삼성화재": 2.5,
        "삼성에스디에스": 2.5,
        "호텔신라": 2.0,
        "삼성증권": 2.0,
        "삼성카드": 1.5,
        "삼성E&A": 1.5,
        "제일기획": 1.0,
        "에스원": 1.0,
        "삼성중공업": 0.5
    }
    
    # 바스켓 생성 실행
    results = trader.create_basket(
        composition_ratios=composition_ratios,
        timeout=60,  # 시세 수신 대기 60초
        order_delay=0.2  # 주문 간 0.2초 딜레이
    )
    
    # 결과 저장
    with open("basket_order_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print("\n✅ 결과가 basket_order_results.json에 저장되었습니다.")