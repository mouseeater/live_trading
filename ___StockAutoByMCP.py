import asyncio
import aiohttp
import websockets
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import deque
import json
import time
import logging
import hashlib
import base64
from typing import Dict, List, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('arbitrage_trading.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class KISWebSocketClient:
    """한국투자증권 웹소켓 실시간 시세 클라이언트"""
    
    def __init__(self, app_key: str, app_secret: str, is_mock: bool = True):
        self.app_key = app_key
        self.app_secret = app_secret
        self.is_mock = is_mock
        
        # WebSocket URL 설정
        if is_mock:
            self.ws_url = "ws://ops.koreainvestment.com:31000"
        else:
            self.ws_url = "ws://ops.koreainvestment.com:21000"
            
        self.ws = None
        self.approval_key = None
        self.price_data = {}  # 실시간 가격 저장
        self.subscribed_stocks = set()
        self.callbacks = {}  # 종목별 콜백 함수
        
    async def get_approval_key(self):
        """웹소켓 접속키 발급"""
        if self.is_mock:
            base_url = "https://openapivts.koreainvestment.com:29443"
        else:
            base_url = "https://openapi.koreainvestment.com:9443"
            
        url = f"{base_url}/oauth2/Approval"
        headers = {"content-type": "application/json"}
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "secretkey": self.app_secret
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=body) as response:
                data = await response.json()
                self.approval_key = data["approval_key"]
                logger.info(f"웹소켓 접속키 발급 완료: {self.approval_key[:10]}...")
                return self.approval_key
                
    def create_subscribe_message(self, stock_code: str, tr_type: str = "1"):
        """실시간 시세 구독 메시지 생성"""
        header = {
            "approval_key": self.approval_key,
            "custtype": "P",
            "tr_type": tr_type,  # 1: 등록, 2: 해제
            "content-type": "utf-8"
        }
        
        body = {
            "input": {
                "tr_id": "H0STCNT0",  # 실시간 체결가
                "tr_key": stock_code
            }
        }
        
        return json.dumps({
            "header": header,
            "body": body
        })
        
    def create_orderbook_subscribe_message(self, stock_code: str, tr_type: str = "1"):
        """실시간 호가 구독 메시지 생성"""
        header = {
            "approval_key": self.approval_key,
            "custtype": "P",
            "tr_type": tr_type,
            "content-type": "utf-8"
        }
        
        body = {
            "input": {
                "tr_id": "H0STASP0",  # 실시간 호가
                "tr_key": stock_code
            }
        }
        
        return json.dumps({
            "header": header,
            "body": body
        })
        
    def decrypt_message(self, encrypted_msg: str) -> str:
        """AES256 메시지 복호화"""
        # 실시간 시세는 평문으로 오므로 그대로 반환
        return encrypted_msg
        
    async def connect(self):
        """웹소켓 연결"""
        await self.get_approval_key()
        
        self.ws = await websockets.connect(
            self.ws_url,
            ping_interval=30,
            ping_timeout=10
        )
        
        logger.info(f"웹소켓 연결 성공: {self.ws_url}")
        
    async def subscribe(self, stock_codes: List[str]):
        """종목 구독"""
        if not self.ws:
            await self.connect()
            
        for code in stock_codes:
            if code not in self.subscribed_stocks:
                # 실시간 체결가 구독
                msg = self.create_subscribe_message(code)
                await self.ws.send(msg)
                
                # 실시간 호가 구독
                msg_orderbook = self.create_orderbook_subscribe_message(code)
                await self.ws.send(msg_orderbook)
                
                self.subscribed_stocks.add(code)
                logger.info(f"종목 구독: {code}")
                
                await asyncio.sleep(0.1)  # 구독 간 짧은 대기
                
    async def unsubscribe(self, stock_codes: List[str]):
        """종목 구독 해제"""
        for code in stock_codes:
            if code in self.subscribed_stocks:
                msg = self.create_subscribe_message(code, tr_type="2")
                await self.ws.send(msg)
                self.subscribed_stocks.remove(code)
                logger.info(f"종목 구독 해제: {code}")
                
    def parse_realtime_price(self, data: str) -> Dict:
        """실시간 체결가 파싱 - 한국투자증권 실제 형식"""
        try:
            parts = data.split("|")
            
            if len(parts) < 4:
                return {}
                
            # 헤더 정보
            tr_id = parts[1] if len(parts) > 1 else ""
            
            if tr_id == "H0STCNT0":  # 실시간 체결가
                # 실제 데이터는 parts[3]에 있음
                data_str = parts[3] if len(parts) > 3 else ""
                
                # 데이터 파싱 (한투 실제 포맷)
                # 데이터는 ^ 구분자로 되어 있음
                fields = data_str.split("^") if "^" in data_str else [data_str]
                
                if len(fields) >= 10:
                    stock_code = fields[0] if fields[0] else ""
                    
                    # 안전한 파싱
                    try:
                        # 체결시간
                        exec_time = fields[1] if len(fields) > 1 else ""
                        # 현재가 (체결가)
                        current_price = int(fields[2].replace(",", "")) if len(fields) > 2 and fields[2].replace(",", "").isdigit() else 0
                        # 전일대비
                        change = int(fields[3].replace(",", "")) if len(fields) > 3 and fields[3].replace(",", "").replace("-", "").isdigit() else 0
                        # 등락률
                        change_rate = float(fields[4].replace("%", "")) if len(fields) > 4 and fields[4].replace("%", "").replace("-", "").replace(".", "").isdigit() else 0
                        # 체결량
                        volume = int(fields[5].replace(",", "")) if len(fields) > 5 and fields[5].replace(",", "").isdigit() else 0
                        # 누적거래량
                        total_volume = int(fields[6].replace(",", "")) if len(fields) > 6 and fields[6].replace(",", "").isdigit() else 0
                        
                        if stock_code and current_price > 0:
                            return {
                                "stock_code": stock_code[:6],  # 종목코드 6자리
                                "price": current_price,
                                "volume": volume,
                                "total_volume": total_volume,
                                "change": change,
                                "change_rate": change_rate,
                                "time": exec_time
                            }
                    except (ValueError, IndexError) as e:
                        logger.debug(f"체결가 파싱 오류: {e}, 데이터: {fields[:7]}")
                        
            elif tr_id == "H0STASP0":  # 실시간 호가
                data_str = parts[3] if len(parts) > 3 else ""
                fields = data_str.split("^") if "^" in data_str else [data_str]
                
                if len(fields) >= 20:
                    stock_code = fields[0] if fields[0] else ""
                    
                    try:
                        # 호가 시간
                        quote_time = fields[1] if len(fields) > 1 else ""
                        
                        # 매도호가 (1~10)
                        ask_prices = []
                        ask_volumes = []
                        for i in range(10):
                            price_idx = 2 + i * 2
                            volume_idx = 3 + i * 2
                            if len(fields) > volume_idx:
                                price = int(fields[price_idx].replace(",", "")) if fields[price_idx].replace(",", "").isdigit() else 0
                                volume = int(fields[volume_idx].replace(",", "")) if fields[volume_idx].replace(",", "").isdigit() else 0
                                if price > 0:
                                    ask_prices.append(price)
                                    ask_volumes.append(volume)
                                    
                        # 매수호가 (1~10) 
                        bid_prices = []
                        bid_volumes = []
                        for i in range(10):
                            price_idx = 22 + i * 2
                            volume_idx = 23 + i * 2
                            if len(fields) > volume_idx:
                                price = int(fields[price_idx].replace(",", "")) if fields[price_idx].replace(",", "").isdigit() else 0
                                volume = int(fields[volume_idx].replace(",", "")) if fields[volume_idx].replace(",", "").isdigit() else 0
                                if price > 0:
                                    bid_prices.append(price)
                                    bid_volumes.append(volume)
                                    
                        if stock_code and ask_prices and bid_prices:
                            return {
                                "stock_code": stock_code[:6],
                                "ask_price": ask_prices[0] if ask_prices else 0,  # 1호가
                                "bid_price": bid_prices[0] if bid_prices else 0,  # 1호가
                                "ask_volume": ask_volumes[0] if ask_volumes else 0,
                                "bid_volume": bid_volumes[0] if bid_volumes else 0,
                                "time": quote_time
                            }
                    except (ValueError, IndexError) as e:
                        logger.debug(f"호가 파싱 오류: {e}")
                        
            # pingpong 메시지 처리
            elif tr_id == "PINGPONG":
                logger.debug("Ping-Pong 메시지 수신")
                return {"type": "pingpong"}
                
            # 시스템 메시지
            elif parts[0] in ["0", "1"]:
                if len(parts) > 2:
                    msg = parts[2] if len(parts) > 2 else ""
                    logger.debug(f"시스템 메시지: {msg}")
                    return {"type": "system", "message": msg}
                    
        except Exception as e:
            logger.debug(f"메시지 파싱 실패: {e}, 원본: {data[:100]}")
            
        return {}
        
    async def listen(self):
        """실시간 데이터 수신"""
        reconnect_count = 0
        max_reconnect = 5
        
        while reconnect_count < max_reconnect:
            try:
                if not self.ws:
                    await self.connect()
                    # 재연결 시 구독 복원
                    if self.subscribed_stocks:
                        stocks_to_resubscribe = list(self.subscribed_stocks)
                        self.subscribed_stocks.clear()
                        await self.subscribe(stocks_to_resubscribe)
                    
                message = await self.ws.recv()
                
                # 메시지 파싱
                parsed_data = self.parse_realtime_price(message)
                
                if parsed_data:
                    # pingpong 메시지 처리
                    if parsed_data.get("type") == "pingpong":
                        await self.ws.pong()
                        continue
                        
                    # 시스템 메시지 처리
                    if parsed_data.get("type") == "system":
                        continue
                        
                    # 가격 데이터 처리
                    if "stock_code" in parsed_data:
                        stock_code = parsed_data["stock_code"]
                        
                        # 가격 데이터 업데이트
                        if stock_code not in self.price_data:
                            self.price_data[stock_code] = {}
                            
                        # 기존 데이터와 병합 (호가와 체결가 모두 유지)
                        self.price_data[stock_code].update(parsed_data)
                        
                        # 로그 (디버그용 - 운영시 제거)
                        if "price" in parsed_data:
                            logger.debug(f"체결가 업데이트 - {stock_code}: {parsed_data['price']:,}원")
                        elif "ask_price" in parsed_data:
                            logger.debug(f"호가 업데이트 - {stock_code}: 매도 {parsed_data['ask_price']:,} / 매수 {parsed_data['bid_price']:,}")
                            
                        # 콜백 실행
                        if stock_code in self.callbacks:
                            await self.callbacks[stock_code](parsed_data)
                            
                # 재연결 카운터 리셋
                reconnect_count = 0
                        
            except websockets.exceptions.ConnectionClosed:
                logger.warning(f"웹소켓 연결 종료, 재연결 시도... ({reconnect_count + 1}/{max_reconnect})")
                self.ws = None
                reconnect_count += 1
                await asyncio.sleep(5 * reconnect_count)  # 재연결 간격 증가
                
            except asyncio.CancelledError:
                logger.info("웹소켓 리스너 종료")
                break
                
            except Exception as e:
                logger.error(f"웹소켓 수신 오류: {e}")
                await asyncio.sleep(1)
                
        if reconnect_count >= max_reconnect:
            logger.error("최대 재연결 횟수 초과, 웹소켓 리스너 종료")
                
    async def close(self):
        """웹소켓 연결 종료"""
        if self.ws:
            await self.ws.close()
            logger.info("웹소켓 연결 종료")

class KISAPI:
    """한국투자증권 API 클래스 (주문용)"""
    
    def __init__(self, app_key, app_secret, acc_no, is_mock=True):
        self.app_key = app_key
        self.app_secret = app_secret
        self.acc_no = acc_no
        self.is_mock = is_mock
        
        # API URL 설정 (모의투자/실전투자)
        if is_mock:
            self.base_url = "https://openapivts.koreainvestment.com:29443"
        else:
            self.base_url = "https://openapi.koreainvestment.com:9443"
            
        self.token = None
        self.token_expire = None
        
    async def get_token(self):
        """접근 토큰 발급"""
        if self.token and self.token_expire and datetime.now() < self.token_expire:
            return self.token
            
        url = f"{self.base_url}/oauth2/tokenP"
        headers = {"content-type": "application/json"}
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=body) as response:
                data = await response.json()
                self.token = data["access_token"]
                self.token_expire = datetime.now() + timedelta(seconds=data["expires_in"] - 60)
                return self.token
                
    async def buy_order(self, stock_code, quantity, price=None):
        """매수 주문"""
        await self.get_token()
        
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-cash"
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "VTTC0802U" if self.is_mock else "TTTC0802U"
        }
        
        body = {
            "CANO": self.acc_no[:8],
            "ACNT_PRDT_CD": self.acc_no[8:],
            "PDNO": stock_code,
            "ORD_DVSN": "00" if price else "01",  # 지정가/시장가
            "ORD_QTY": str(quantity),
            "ORD_UNPR": str(price) if price else "0"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=body) as response:
                data = await response.json()
                if data["rt_cd"] == "0":
                    logger.info(f"매수 주문 성공: {stock_code} {quantity}주")
                    return data["output"]["ORD_NO"]
                else:
                    logger.error(f"매수 주문 실패: {stock_code} - {data['msg1']}")
                    return None
                    
    async def sell_order(self, stock_code, quantity, price=None):
        """매도 주문"""
        await self.get_token()
        
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-cash"
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "VTTC0801U" if self.is_mock else "TTTC0801U"
        }
        
        body = {
            "CANO": self.acc_no[:8],
            "ACNT_PRDT_CD": self.acc_no[8:],
            "PDNO": stock_code,
            "ORD_DVSN": "00" if price else "01",
            "ORD_QTY": str(quantity),
            "ORD_UNPR": str(price) if price else "0"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=body) as response:
                data = await response.json()
                if data["rt_cd"] == "0":
                    logger.info(f"매도 주문 성공: {stock_code} {quantity}주")
                    return data["output"]["ORD_NO"]
                else:
                    logger.error(f"매도 주문 실패: {stock_code} - {data['msg1']}")
                    return None

class ETFArbitrageTrader:
    """ETF-현물 차익거래 시스템 (웹소켓 버전)"""
    
    def __init__(self, kis_api: KISAPI, ws_client: KISWebSocketClient):
        self.kis_api = kis_api
        self.ws_client = ws_client
        
        # ETF 및 구성종목 정보
        self.etf_code = "371160"  # KODEX 삼성그룹
        self.components = {
            "삼성E&A": "028050",
            "삼성SDI": "006400",
            "삼성물산": "028260",
            "삼성바이오로직스": "207940",
            "삼성생명": "032830",
            "삼성에스디에스": "018260",
            "삼성전기": "009150",
            "삼성전자": "005930",
            "삼성중공업": "010140",
            "삼성증권": "016360",
            "삼성카드": "029780",
            "삼성화재": "000810",
            "에스원": "012750",
            "제일기획": "030000",
            "호텔신라": "008770"
        }
        
        # 모든 종목 코드 리스트 (ETF + 구성종목)
        self.all_codes = [self.etf_code] + list(self.components.values())
        
        # ETF 구성비중 (예시값 - 실제값으로 업데이트 필요)
        self.weights = {
            "005930": 0.50,  # 삼성전자
            "006400": 0.08,  # 삼성SDI
            "207940": 0.07,  # 삼성바이오로직스
            "028260": 0.06,  # 삼성물산
            "000810": 0.05,  # 삼성화재
            "009150": 0.04,  # 삼성전기
            "032830": 0.04,  # 삼성생명
            "018260": 0.03,  # 삼성에스디에스
            "012750": 0.03,  # 에스원
            "030000": 0.02,  # 제일기획
            "016360": 0.02,  # 삼성증권
            "008770": 0.02,  # 호텔신라
            "029780": 0.02,  # 삼성카드
            "010140": 0.01,  # 삼성중공업
            "028050": 0.01   # 삼성E&A
        }
        
        # 트레이딩 파라미터
        self.basket_size = 20000000  # 바스켓 크기: 2천만원
        self.spread_history = deque(maxlen=100)  # 최근 100개 스프레드 기록
        self.position = None  # 현재 포지션
        self.entry_spread = None  # 진입 시 스프레드
        
        # 통계 파라미터
        self.spread_mean = 0
        self.spread_std = 0.001  # 초기 표준편차
        self.z_score_threshold = 2.0  # 2 시그마
        
        # 리스크 관리
        self.max_position_value = 20000000  # 최대 포지션: 2천만원
        self.stop_loss = 0.02  # 손절선: 2%
        
        # 실시간 가격 업데이트 플래그
        self.price_updated = asyncio.Event()
        
    async def setup_callbacks(self):
        """웹소켓 콜백 설정"""
        async def price_callback(data):
            """가격 업데이트 콜백"""
            self.price_updated.set()
            
        # 모든 종목에 대해 콜백 설정
        for code in self.all_codes:
            self.ws_client.callbacks[code] = price_callback
            
    async def calculate_basket_value(self, prices: Dict[str, float]) -> float:
        """바스켓 가치 계산"""
        basket_value = 0
        for code, weight in self.weights.items():
            if code in prices:
                basket_value += prices[code] * weight * 10000  # ETF 1주당 가치
        return basket_value
        
    def get_realtime_prices(self) -> Dict[str, float]:
        """웹소켓에서 실시간 가격 가져오기"""
        prices = {}
        
        # ETF 가격
        if self.etf_code in self.ws_client.price_data:
            etf_data = self.ws_client.price_data[self.etf_code]
            if "price" in etf_data and etf_data["price"] > 0:
                prices["ETF"] = etf_data["price"]
                # 호가 정보가 있으면 사용, 없으면 현재가 사용
                prices[f"{self.etf_code}_ask"] = etf_data.get("ask_price", etf_data["price"])
                prices[f"{self.etf_code}_bid"] = etf_data.get("bid_price", etf_data["price"])
                
        # 구성종목 가격
        for name, code in self.components.items():
            if code in self.ws_client.price_data:
                stock_data = self.ws_client.price_data[code]
                if "price" in stock_data and stock_data["price"] > 0:
                    prices[code] = stock_data["price"]
                    prices[f"{code}_ask"] = stock_data.get("ask_price", stock_data["price"])
                    prices[f"{code}_bid"] = stock_data.get("bid_price", stock_data["price"])
                    
        return prices
        
    async def calculate_spread(self, prices: Dict[str, float]) -> float:
        """스프레드(괴리율) 계산"""
        if "ETF" not in prices:
            return None
            
        etf_price = prices["ETF"]
        basket_value = await self.calculate_basket_value(prices)
        
        # 괴리율 = (ETF가격 - 바스켓가치) / 바스켓가치
        spread = (etf_price - basket_value) / basket_value
        return spread
        
    def update_statistics(self, spread: float):
        """통계 업데이트"""
        self.spread_history.append(spread)
        
        if len(self.spread_history) >= 20:
            self.spread_mean = np.mean(self.spread_history)
            self.spread_std = np.std(self.spread_history)
            
    def calculate_z_score(self, spread: float) -> float:
        """Z-score 계산"""
        if self.spread_std > 0:
            return (spread - self.spread_mean) / self.spread_std
        return 0
        
    async def calculate_basket_quantities(self, prices: Dict[str, float], total_value: float) -> Dict[str, int]:
        """바스켓 구성 수량 계산"""
        quantities = {}
        
        for code, weight in self.weights.items():
            if code in prices:
                target_value = total_value * weight
                quantity = int(target_value / prices[code])
                if quantity > 0:
                    quantities[code] = quantity
                    
        # 실제 투자금액 계산
        actual_value = sum(quantities[code] * prices[code] for code in quantities)
        
        # 2천만원 초과시 조정
        if actual_value > self.max_position_value:
            adjust_ratio = self.max_position_value / actual_value
            for code in quantities:
                quantities[code] = int(quantities[code] * adjust_ratio)
                
        return quantities
        
    async def open_position(self, position_type: str, prices: Dict[str, float]):
        """포지션 진입"""
        if self.position is not None:
            logger.warning("이미 포지션이 있습니다")
            return
            
        logger.info(f"포지션 진입: {position_type}")
        
        if position_type == "LONG_ETF_SHORT_BASKET":
            # ETF 매수
            etf_quantity = int(self.basket_size / prices["ETF"])
            await self.kis_api.buy_order(
                self.etf_code, 
                etf_quantity,
                prices[f"{self.etf_code}_ask"]
            )
            
            # 바스켓 구성종목 매도 (실제로는 공매도 불가능하므로 시뮬레이션)
            basket_quantities = await self.calculate_basket_quantities(prices, self.basket_size)
            for code, quantity in basket_quantities.items():
                logger.info(f"매도 시뮬레이션: {code} {quantity}주")
                
        elif position_type == "SHORT_ETF_LONG_BASKET":
            # ETF 매도 (실제로는 공매도 불가능하므로 시뮬레이션)
            etf_quantity = int(self.basket_size / prices["ETF"])
            logger.info(f"ETF 매도 시뮬레이션: {self.etf_code} {etf_quantity}주")
            
            # 바스켓 구성종목 매수
            basket_quantities = await self.calculate_basket_quantities(prices, self.basket_size)
            for code, quantity in basket_quantities.items():
                await self.kis_api.buy_order(
                    code, 
                    quantity,
                    prices[f"{code}_ask"]
                )
                await asyncio.sleep(0.2)  # 주문 간 대기
                
        self.position = {
            "type": position_type,
            "entry_time": datetime.now(),
            "entry_prices": prices.copy(),
            "etf_quantity": etf_quantity if 'etf_quantity' in locals() else 0,
            "basket_quantities": basket_quantities if 'basket_quantities' in locals() else {}
        }
        
    async def close_position(self, prices: Dict[str, float]):
        """포지션 청산"""
        if self.position is None:
            logger.warning("청산할 포지션이 없습니다")
            return
            
        logger.info(f"포지션 청산: {self.position['type']}")
        
        if self.position["type"] == "LONG_ETF_SHORT_BASKET":
            # ETF 매도
            await self.kis_api.sell_order(
                self.etf_code, 
                self.position["etf_quantity"],
                prices[f"{self.etf_code}_bid"]
            )
            
            # 바스켓 매수 (숏커버 시뮬레이션)
            for code, quantity in self.position["basket_quantities"].items():
                logger.info(f"매수 시뮬레이션 (숏커버): {code} {quantity}주")
                
        elif self.position["type"] == "SHORT_ETF_LONG_BASKET":
            # ETF 매수 (숏커버 시뮬레이션)
            logger.info(f"ETF 매수 시뮬레이션 (숏커버): {self.etf_code} {self.position['etf_quantity']}주")
            
            # 바스켓 매도
            for code, quantity in self.position["basket_quantities"].items():
                await self.kis_api.sell_order(
                    code, 
                    quantity,
                    prices[f"{code}_bid"]
                )
                await asyncio.sleep(0.2)  # 주문 간 대기
                
        # 수익률 계산
        pnl = self.calculate_pnl(prices)
        logger.info(f"포지션 청산 완료 - 수익률: {pnl:.2%}")
        
        self.position = None
        self.entry_spread = None
        
    def calculate_pnl(self, current_prices: Dict[str, float]) -> float:
        """손익 계산"""
        if self.position is None:
            return 0
            
        entry_prices = self.position["entry_prices"]
        pnl = 0
        
        if self.position["type"] == "LONG_ETF_SHORT_BASKET":
            # ETF 롱 수익
            etf_entry = entry_prices.get(f"{self.etf_code}_ask", entry_prices["ETF"])
            etf_exit = current_prices.get(f"{self.etf_code}_bid", current_prices["ETF"])
            etf_pnl = (etf_exit - etf_entry) * self.position["etf_quantity"]
            
            # 바스켓 숏 수익 (시뮬레이션)
            basket_pnl = 0
            for code, quantity in self.position["basket_quantities"].items():
                if code in current_prices and code in entry_prices:
                    basket_pnl += (entry_prices[code] - current_prices[code]) * quantity
                    
            pnl = etf_pnl + basket_pnl
            
        elif self.position["type"] == "SHORT_ETF_LONG_BASKET":
            # ETF 숏 수익 (시뮬레이션)
            etf_pnl = (entry_prices["ETF"] - current_prices["ETF"]) * self.position["etf_quantity"]
            
            # 바스켓 롱 수익
            basket_pnl = 0
            for code, quantity in self.position["basket_quantities"].items():
                entry = entry_prices.get(f"{code}_ask", entry_prices.get(code, 0))
                exit = current_prices.get(f"{code}_bid", current_prices.get(code, 0))
                if entry and exit:
                    basket_pnl += (exit - entry) * quantity
                    
            pnl = etf_pnl + basket_pnl
            
        # 수수료 고려
        commission = self.basket_size * 0.0003
        return (pnl - commission) / self.basket_size
        
    async def check_stop_loss(self, prices: Dict[str, float]) -> bool:
        """손절 체크"""
        if self.position is None:
            return False
            
        pnl = self.calculate_pnl(prices)
        if pnl < -self.stop_loss:
            logger.warning(f"손절선 도달: {pnl:.2%}")
            return True
        return False
        
    async def wait_for_initial_data(self):
        """초기 데이터 수신 대기"""
        logger.info("실시간 데이터 수신 대기 중...")
        
        max_wait = 30  # 최대 30초 대기
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            prices = self.get_realtime_prices()
            if len(prices) >= len(self.components) + 1:
                logger.info(f"실시간 데이터 수신 완료: {len(prices)}개 가격")
                return True
            await asyncio.sleep(1)
            
        logger.error("초기 데이터 수신 실패")
        return False
        
    async def run_strategy(self):
        """전략 실행 (웹소켓 기반)"""
        logger.info("차익거래 전략 시작 (웹소켓 모드)")
        
        # 웹소켓 연결 및 종목 구독
        await self.ws_client.connect()
        await self.ws_client.subscribe(self.all_codes)
        await self.setup_callbacks()
        
        # 웹소켓 리스너 시작
        ws_task = asyncio.create_task(self.ws_client.listen())
        
        # 초기 데이터 수신 대기
        if not await self.wait_for_initial_data():
            logger.error("초기 데이터 수신 실패, 전략 중단")
            return
            
        # 초기 통계 수집
        logger.info("초기 통계 수집 중...")
        for i in range(50):
            prices = self.get_realtime_prices()
            if len(prices) > len(self.components):
                spread = await self.calculate_spread(prices)
                if spread is not None:
                    self.update_statistics(spread)
                    if i % 10 == 0:
                        logger.info(f"통계 수집 [{i+1}/50]: 스프레드 {spread:.4%}")
            await asyncio.sleep(0.5)
            
        logger.info(f"통계 수집 완료 - 평균: {self.spread_mean:.4%}, 표준편차: {self.spread_std:.4%}")
        
        # 메인 트레이딩 루프
        last_log_time = time.time()
        
        try:
            while True:
                # 실시간 가격 데이터 대기
                try:
                    await asyncio.wait_for(self.price_updated.wait(), timeout=5.0)
                    self.price_updated.clear()
                except asyncio.TimeoutError:
                    # 타임아웃 시 연결 상태 체크
                    if not self.ws_client.ws or self.ws_client.ws.closed:
                        logger.warning("웹소켓 연결 끊김, 재연결 시도...")
                        await self.ws_client.connect()
                        await self.ws_client.subscribe(self.all_codes)
                    continue
                    
                # 실시간 가격 가져오기
                prices = self.get_realtime_prices()
                
                if len(prices) < len(self.components) + 1:
                    continue
                    
                # 스프레드 계산
                spread = await self.calculate_spread(prices)
                if spread is None:
                    continue
                    
                # 통계 업데이트
                self.update_statistics(spread)
                
                # Z-score 계산
                z_score = self.calculate_z_score(spread)
                
                # 10초마다 상태 로그
                current_time = time.time()
                if current_time - last_log_time >= 10:
                    logger.info(f"스프레드: {spread:.4%}, Z-score: {z_score:.2f}, 포지션: {self.position is not None}")
                    last_log_time = current_time
                    
                # 포지션이 없을 때
                if self.position is None:
                    # 진입 신호 체크
                    if z_score > self.z_score_threshold:
                        # ETF 과대평가 -> ETF 숏, 바스켓 롱
                        logger.info(f"진입 신호: ETF 과대평가 (Z-score: {z_score:.2f})")
                        await self.open_position("SHORT_ETF_LONG_BASKET", prices)
                        self.entry_spread = spread
                        
                    elif z_score < -self.z_score_threshold:
                        # ETF 과소평가 -> ETF 롱, 바스켓 숏
                        logger.info(f"진입 신호: ETF 과소평가 (Z-score: {z_score:.2f})")
                        await self.open_position("LONG_ETF_SHORT_BASKET", prices)
                        self.entry_spread = spread
                        
                # 포지션이 있을 때
                else:
                    # 포지션 수익률 실시간 모니터링
                    current_pnl = self.calculate_pnl(prices)
                    
                    # 손절 체크
                    if await self.check_stop_loss(prices):
                        await self.close_position(prices)
                        
                    # 청산 신호 체크 (평균 회귀)
                    elif abs(z_score) < 0.5:  # 0.5 시그마 이내로 돌아오면 청산
                        logger.info(f"청산 신호: 평균 회귀 (Z-score: {z_score:.2f}, PnL: {current_pnl:.2%})")
                        await self.close_position(prices)
                        
                    # 수익 실현 (목표 수익률 도달)
                    elif current_pnl > 0.01:  # 1% 수익 시
                        logger.info(f"목표 수익 도달: {current_pnl:.2%}")
                        await self.close_position(prices)
                        
                    # 반대 신호 발생시 청산 후 재진입
                    elif self.position["type"] == "LONG_ETF_SHORT_BASKET" and z_score > self.z_score_threshold:
                        logger.info(f"반대 신호 발생 - 포지션 전환 (PnL: {current_pnl:.2%})")
                        await self.close_position(prices)
                        await asyncio.sleep(1)
                        await self.open_position("SHORT_ETF_LONG_BASKET", prices)
                        self.entry_spread = spread
                        
                    elif self.position["type"] == "SHORT_ETF_LONG_BASKET" and z_score < -self.z_score_threshold:
                        logger.info(f"반대 신호 발생 - 포지션 전환 (PnL: {current_pnl:.2%})")
                        await self.close_position(prices)
                        await asyncio.sleep(1)
                        await self.open_position("LONG_ETF_SHORT_BASKET", prices)
                        self.entry_spread = spread
                        
                    # 포지션 보유 중 상태 업데이트 (1분마다)
                    elif current_time - last_log_time >= 60:
                        logger.info(f"포지션 상태 - Type: {self.position['type']}, PnL: {current_pnl:.2%}, Z-score: {z_score:.2f}")
                        
        except KeyboardInterrupt:
            logger.info("전략 중단 요청")
            
        except Exception as e:
            logger.error(f"전략 실행 중 오류: {e}")
            
        finally:
            # 정리 작업
            if self.position:
                logger.info("포지션 정리 중...")
                prices = self.get_realtime_prices()
                if prices:
                    await self.close_position(prices)
                    
            # 웹소켓 연결 종료
            await self.ws_client.close()
            ws_task.cancel()
            
            logger.info("전략 종료")

async def main():
    """메인 함수"""
    # API 키 설정 (실제 키로 교체 필요)
    APP_KEY = "PSVP4uaIGfmv9oviIqOjn58WIV3coGzjAEqu"
    APP_SECRET = "NYuz2xS/ZFfTnLBa15UsPnU/iFaGMMAQiv/RoB4Xxi2yHOCCY1Zq9IgJARubfjWXzoFUbun4wlG7xhDQyWXIvSaWkK27RkFz8k4TBYpOtNzcRCeW17eBpQ1GULQkqP3AUultGWtcycBDkL/KHcPAga53hK37kM4YcSEsjoZgncVb6yO2DOc="
    ACCOUNT_NO = "50154524"
    
    # 모의투자 여부
    IS_MOCK = True
    
    # KIS API 초기화 (주문용)
    kis_api = KISAPI(APP_KEY, APP_SECRET, ACCOUNT_NO, is_mock=IS_MOCK)
    
    # 웹소켓 클라이언트 초기화 (실시간 시세용)
    ws_client = KISWebSocketClient(APP_KEY, APP_SECRET, is_mock=IS_MOCK)
    
    # 트레이더 초기화
    trader = ETFArbitrageTrader(kis_api, ws_client)
    
    # 전략 실행
    try:
        await trader.run_strategy()
    except Exception as e:
        logger.error(f"메인 함수 오류: {e}")
    finally:
        await ws_client.close()
        
if __name__ == "__main__":
    # 이벤트 루프 실행
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("프로그램 종료")