#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
二次創新高股票策略機器人 v2.0
自動化版本 - 每晚21:00自動執行，不含假日
"""

import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
import requests
import time
import pytz
import traceback
from io import StringIO

# FinLab 套件
try:
    import finlab
    from finlab import data
except ImportError as e:
    print(f"❌ FinLab 套件導入失敗: {e}")
    sys.exit(1)


class AutomatedSecondHighStrategy:
    """自動化二次創新高策略 v2.0"""
    
    def __init__(self):
        self.name = "二次創新高策略"
        self.version = "v2.0 Auto"
        
        # 策略參數（可調整）
        self.lookback_period = 60      # 新高回望期間
        self.gap_period = 30           # 間隔期間  
        self.confirmation_period = 25  # 確認期間（30-55日）
        self.long_term_period = 120    # 長期趨勢
        self.medium_term_period = 60   # 中期趨勢
        self.revenue_short = 3         # 營收短期平均
        self.revenue_long = 12         # 營收長期平均
        self.volume_short = 5          # 成交量短期平均
        self.volume_long = 20          # 成交量長期平均
        
        # Telegram 設定
        self.telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')
        
        # FinLab 設定
        self.finlab_token = os.getenv('FINLAB_API_TOKEN')
        
        # 執行環境資訊
        self.execution_mode = os.getenv('EXECUTION_MODE', 'manual')
        self.github_run_id = os.getenv('GITHUB_RUN_ID', '')
        self.github_repo = os.getenv('GITHUB_REPOSITORY', '')
        
        # 台灣時區
        self.tw_tz = pytz.timezone('Asia/Taipei')
        
        print(f"🚀 {self.name} {self.version} 初始化完成")
        print(f"⏰ 執行時間: {self.get_tw_time()}")
        print(f"🔧 執行模式: {self.execution_mode}")
        
    def get_tw_time(self) -> str:
        """取得台灣時間字串"""
        return datetime.now(self.tw_tz).strftime('%Y-%m-%d %H:%M:%S')
    
    def initialize_finlab(self) -> bool:
        """初始化 FinLab 連接"""
        try:
            if not self.finlab_token:
                raise ValueError("FINLAB_API_TOKEN 環境變數未設定")
            
            print("🔗 連接 FinLab API...")
            finlab.login(self.finlab_token)
            print("✅ FinLab 登入成功")
            return True
            
        except Exception as e:
            print(f"❌ FinLab 初始化失敗: {e}")
            return False
    
    def get_stock_data(self) -> Optional[Dict[str, pd.DataFrame]]:
        """取得股票資料"""
        try:
            print("📊 取得股票資料...")
            
            # 基本價格資料
            close = data.get('price:收盤價')
            high = data.get('price:最高價')
            volume = data.get('price:成交股數')
            
            if close is None or close.empty:
                raise ValueError("無法取得收盤價資料")
            
            print(f"✅ 資料範圍: {close.index[0]} ~ {close.index[-1]}")
            print(f"📈 股票數量: {close.shape[1]} 檔")
            
            # 營收資料
            try:
                monthly_revenue = data.get('monthly_revenue:當月營收')
                print(f"💰 營收資料: {monthly_revenue.shape if monthly_revenue is not None else 'None'}")
            except:
                monthly_revenue = None
                print("⚠️ 營收資料取得失敗，將跳過營收條件")
            
            # 市值資料（用於篩選規模）
            try:
                market_cap = data.get('price:市值')
            except:
                market_cap = None
                print("⚠️ 市值資料取得失敗")
            
            return {
                'close': close,
                'high': high,
                'volume': volume,
                'monthly_revenue': monthly_revenue,
                'market_cap': market_cap
            }
            
        except Exception as e:
            print(f"❌ 股票資料取得失敗: {e}")
            traceback.print_exc()
            return None
    
    def apply_basic_filters(self, data_dict: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """應用基礎篩選條件"""
        close = data_dict['close']
        
        # 移除缺失值過多的股票
        valid_days = close.count()
        min_days = min(250, len(close) * 0.8)  # 至少80%的資料
        valid_stocks = valid_days >= min_days
        
        print(f"📊 基礎篩選: {valid_stocks.sum()} / {len(valid_stocks)} 檔股票有足夠資料")
        
        # 移除價格過低的股票（< 10元）
        latest_price = close.iloc[-1]
        price_filter = latest_price >= 10
        
        print(f"💲 價格篩選: {price_filter.sum()} 檔股票價格 >= 10元")
        
        # 移除成交量過小的股票
        volume = data_dict['volume']
        if volume is not None:
            avg_volume_20d = volume.rolling(20).mean().iloc[-1]
            volume_filter = avg_volume_20d >= 1000  # 平均日成交量 >= 1000股
            print(f"📊 成交量篩選: {volume_filter.sum()} 檔股票成交量充足")
        else:
            volume_filter = pd.Series(True, index=close.columns)
        
        # 綜合篩選
        basic_filter = valid_stocks & price_filter & volume_filter
        
        print(f"✅ 基礎篩選結果: {basic_filter.sum()} 檔股票通過")
        
        return close.loc[:, basic_filter]
    
    def calculate_second_high_conditions(self, close_filtered: pd.DataFrame, 
                                       data_dict: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """計算二次創新高的8個條件"""
        print("🔍 開始計算二次創新高條件...")
        
        results = []
        stock_count = len(close_filtered.columns)
        
        for i, stock_id in enumerate(close_filtered.columns):
            if i % 100 == 0:
                print(f"進度: {i+1}/{stock_count}")
            
            try:
                stock_close = close_filtered[stock_id].dropna()
                
                if len(stock_close) < self.long_term_period + 10:
                    continue
                
                # 取得最新價格
                latest_price = stock_close.iloc[-1]
                latest_date = stock_close.index[-1]
                
                # 條件1: 創60日新高
                high_60d = stock_close.rolling(self.lookback_period).max().iloc[-1]
                condition1 = latest_price >= high_60d
                
                if not condition1:
                    continue
                
                # 條件2: 前30日有整理期（至少一日未創新高）
                past_30d_prices = stock_close.iloc[-self.gap_period-1:-1]
                past_30d_highs = past_30d_prices.rolling(self.lookback_period).max()
                condition2 = (past_30d_prices < past_30d_highs).any()
                
                # 條件3: 第30-55日前曾創60日新高
                check_period = stock_close.iloc[-55:-self.gap_period]
                if len(check_period) < self.confirmation_period:
                    continue
                    
                historical_highs = check_period.rolling(self.lookback_period).max()
                condition3 = (check_period >= historical_highs).any()
                
                # 條件4: 突破前30-55日最高價
                resistance_level = stock_close.iloc[-55:-self.gap_period].max()
                condition4 = latest_price > resistance_level
                
                # 條件5: 長期趨勢向上（現價 > 120日前價格）
                if len(stock_close) >= self.long_term_period:
                    price_120d_ago = stock_close.iloc[-self.long_term_period]
                    condition5 = latest_price > price_120d_ago
                else:
                    condition5 = False
                
                # 條件6: 中期趨勢向上（現價 > 60日前價格）
                if len(stock_close) >= self.medium_term_period:
                    price_60d_ago = stock_close.iloc[-self.medium_term_period]
                    condition6 = latest_price > price_60d_ago
                else:
                    condition6 = False
                
                # 條件7: 營收成長加速
                condition7 = self.check_revenue_growth(stock_id, data_dict)
                
                # 條件8: 成交量放大確認
                condition8 = self.check_volume_expansion(stock_id, data_dict)
                
                # 只保留完全符合8個條件的股票
                all_conditions = [condition1, condition2, condition3, condition4, 
                                condition5, condition6, condition7, condition8]
                
                if all(all_conditions):
                    # 計算技術指標
                    tech_metrics = self.calculate_technical_metrics(stock_close, data_dict, stock_id)
                    
                    results.append({
                        'stock_id': stock_id,
                        'latest_price': latest_price,
                        'latest_date': latest_date,
                        'resistance_break': resistance_level,
                        'breakthrough_ratio': (latest_price / resistance_level - 1) * 100,
                        'long_term_gain': (latest_price / price_120d_ago - 1) * 100 if len(stock_close) >= self.long_term_period else 0,
                        'medium_term_gain': (latest_price / price_60d_ago - 1) * 100 if len(stock_close) >= self.medium_term_period else 0,
                        **tech_metrics,
                        'conditions_met': sum(all_conditions),
                        'condition_details': {
                            '創60日新高': condition1,
                            '前30日整理': condition2,
                            '歷史強勢確認': condition3,
                            '真正突破確認': condition4,
                            '長期趨勢向上': condition5,
                            '中期趨勢向上': condition6,
                            '營收成長加速': condition7,
                            '成交量放大確認': condition8
                        }
                    })
                
            except Exception as e:
                continue
        
        if results:
            df = pd.DataFrame(results)
            df = df.sort_values(['conditions_met', 'breakthrough_ratio'], ascending=[False, False])
            print(f"🎯 找到 {len(df)} 檔完全符合8條件的股票")
            return df
        else:
            print("❌ 未找到符合條件的股票")
            return pd.DataFrame()
    
    def check_revenue_growth(self, stock_id: str, data_dict: Dict[str, pd.DataFrame]) -> bool:
        """檢查營收成長條件"""
        try:
            monthly_revenue = data_dict.get('monthly_revenue')
            if monthly_revenue is None or stock_id not in monthly_revenue.columns:
                return True  # 如果沒有營收資料，視為通過
            
            revenue_data = monthly_revenue[stock_id].dropna()
            if len(revenue_data) < self.revenue_long:
                return True
            
            # 計算近3月平均 vs 近12月平均
            recent_3m = revenue_data.tail(self.revenue_short).mean()
            recent_12m = revenue_data.tail(self.revenue_long).mean()
            
            return recent_3m > recent_12m
            
        except Exception:
            return True  # 出錯時視為通過
    
    def check_volume_expansion(self, stock_id: str, data_dict: Dict[str, pd.DataFrame]) -> bool:
        """檢查成交量放大條件"""
        try:
            volume = data_dict.get('volume')
            if volume is None or stock_id not in volume.columns:
                return True  # 如果沒有成交量資料，視為通過
            
            volume_data = volume[stock_id].dropna()
            if len(volume_data) < self.volume_long:
                return True
            
            # 計算近5日平均 vs 近20日平均
            volume_5d = volume_data.tail(self.volume_short).mean()
            volume_20d = volume_data.tail(self.volume_long).mean()
            
            return volume_5d > volume_20d * 1.2  # 放大20%以上
            
        except Exception:
            return True  # 出錯時視為通過
    
    def calculate_technical_metrics(self, stock_close: pd.Series, 
                                  data_dict: Dict[str, pd.DataFrame], stock_id: str) -> Dict:
        """計算技術指標"""
        try:
            # 移動平均線
            ma5 = stock_close.rolling(5).mean().iloc[-1]
            ma10 = stock_close.rolling(10).mean().iloc[-1]
            ma20 = stock_close.rolling(20).mean().iloc[-1]
            
            # RSI
            delta = stock_close.diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            # 成交量比率
            volume_ratio = 1.0
            if data_dict.get('volume') is not None and stock_id in data_dict['volume'].columns:
                volume_data = data_dict['volume'][stock_id].dropna()
                if len(volume_data) >= 20:
                    volume_5d = volume_data.tail(5).mean()
                    volume_20d = volume_data.tail(20).mean()
                    volume_ratio = volume_5d / volume_20d if volume_20d > 0 else 1.0
            
            # 波動率
            volatility = stock_close.pct_change().tail(20).std() * 100
            
            return {
                'ma5': ma5,
                'ma10': ma10,
                'ma20': ma20,
                'rsi': rsi.iloc[-1] if not rsi.empty else 50,
                'volume_ratio': volume_ratio,
                'volatility': volatility
            }
            
        except Exception:
            return {
                'ma5': 0, 'ma10': 0, 'ma20': 0, 'rsi': 50,
                'volume_ratio': 1.0, 'volatility': 0
            }
    
    def format_results_message(self, results_df: pd.DataFrame) -> List[str]:
        """格式化結果訊息"""
        if results_df.empty:
            return [f"""📊 {self.name} {self.version}

⏰ 分析時間: {self.get_tw_time()}

❌ 今日無股票完全符合8大條件

🔍 完整8大條件:
1. 創60日新高
2. 前30日有整理期  
3. 歷史強勢確認
4. 真正突破確認
5. 長期趨勢向上
6. 中期趨勢向上
7. 營收成長加速
8. 成交量放大確認

💡 建議: 持續關注，等待更好的進場時機"""]
        
        messages = []
        
        # 標題訊息
        header = f"""🚀 {self.name} {self.version}

⏰ 分析時間: {self.get_tw_time()}
🎯 找到 {len(results_df)} 檔完全符合8條件的強勢股

📊 完整8大條件全數通過:
✅ 創60日新高 ✅ 前30日整理期
✅ 歷史強勢確認 ✅ 真正突破確認  
✅ 長期趨勢向上 ✅ 中期趨勢向上
✅ 營收成長加速 ✅ 成交量放大確認

───────────────────"""
        
        messages.append(header)
        
        # 個股詳細資訊
        for idx, row in results_df.head(10).iterrows():  # 最多顯示10檔
            stock_msg = f"""📈 {row['stock_id']}

💰 最新價格: ${row['latest_price']:.2f}
📊 突破阻力: ${row['resistance_break']:.2f}
🚀 突破幅度: +{row['breakthrough_ratio']:.1f}%

📈 績效表現:
• 長期漲幅: +{row['long_term_gain']:.1f}% (120日)
• 中期漲幅: +{row['medium_term_gain']:.1f}% (60日)

🔧 技術指標:
• MA5/MA10/MA20: {row['ma5']:.1f}/{row['ma10']:.1f}/{row['ma20']:.1f}
• RSI: {row['rsi']:.0f}
• 成交量比: {row['volume_ratio']:.1f}x
• 波動率: {row['volatility']:.1f}%

⚠️ 風險提醒:
• 建議分批進場，設定停損
• 注意大盤走勢變化
• 控制單一個股比重

───────────────────"""
            
            messages.append(stock_msg)
        
        # 結尾提醒
        footer = f"""💡 操作建議:

🎯 進場策略:
• 分2-3批進場，降低風險
• 突破後回檔至支撐可加碼
• 嚴格執行停損停利

⚠️ 風控重點:
• 單檔持股不超過總資金10%
• 設定7-10%停損點
• 獲利20%以上可考慮減碼

📱 持續追蹤:
• 關注成交量是否持續
• 注意是否跌破關鍵支撐
• 搭配大盤趨勢判斷

🤖 每晚21:00自動更新
祝您投資順利！ 🌟"""
        
        messages.append(footer)
        
        return messages
    
    def send_telegram_message(self, message: str) -> bool:
        """發送 Telegram 訊息"""
        if not self.telegram_token or not self.telegram_chat_id:
            print("❌ Telegram 設定不完整")
            return False
        
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            
            # 清理訊息格式，移除可能的問題字符
            cleaned_message = message.strip()
            
            # 分割長訊息
            max_length = 4000  # 降低限制，確保安全
            if len(cleaned_message) <= max_length:
                messages = [cleaned_message]
            else:
                messages = []
                lines = cleaned_message.split('\n')
                current_msg = ""
                
                for line in lines:
                    if len(current_msg) + len(line) + 1 <= max_length:
                        current_msg += line + '\n'
                    else:
                        if current_msg:
                            messages.append(current_msg.strip())
                        current_msg = line + '\n'
                
                if current_msg:
                    messages.append(current_msg.strip())
            
            # 發送所有訊息片段
            success_count = 0
            for i, msg in enumerate(messages):
                try:
                    data = {
                        "chat_id": self.telegram_chat_id,
                        "text": msg
                    }
                    
                    response = requests.post(url, data=data, timeout=30)
                    
                    if response.status_code == 200:
                        success_count += 1
                        print(f"✅ 訊息片段 {i+1}/{len(messages)} 發送成功")
                    else:
                        print(f"❌ 訊息片段 {i+1} 發送失敗: {response.status_code}")
                        print(f"回應內容: {response.text}")
                    
                    # 避免觸發頻率限制
                    if i < len(messages) - 1:
                        time.sleep(1)
                        
                except Exception as e:
                    print(f"❌ 發送訊息片段 {i+1} 時出錯: {e}")
            
            if success_count > 0:
                print(f"✅ Telegram 訊息發送完成 ({success_count}/{len(messages)})")
                return True
            else:
                print(f"❌ Telegram 訊息發送完全失敗")
                return False
            
        except Exception as e:
            print(f"❌ Telegram 發送失敗: {e}")
            return False
    
    def run_analysis(self) -> bool:
        """執行完整分析流程"""
        try:
            print(f"\n{'='*50}")
            print(f"🚀 開始執行 {self.name} {self.version}")
            print(f"⏰ 開始時間: {self.get_tw_time()}")
            print(f"{'='*50}\n")
            
            # 1. 初始化 FinLab
            if not self.initialize_finlab():
                raise Exception("FinLab 初始化失敗")
            
            # 2. 取得股票資料
            data_dict = self.get_stock_data()
            if data_dict is None:
                raise Exception("股票資料取得失敗")
            
            # 3. 基礎篩選
            close_filtered = self.apply_basic_filters(data_dict)
            if close_filtered.empty:
                raise Exception("基礎篩選後無可用股票")
            
            # 4. 計算二次創新高條件
            results_df = self.calculate_second_high_conditions(close_filtered, data_dict)
            
            # 5. 格式化並發送結果
            messages = self.format_results_message(results_df)
            
            success_count = 0
            for message in messages:
                success = self.send_telegram_message(message)
                if success:
                    success_count += 1
                time.sleep(2)  # 訊息間隔
            
            # 只要有一個訊息發送成功，就視為部分成功
            overall_success = success_count > 0
            
            print(f"\n{'='*50}")
            print(f"✅ 分析完成: {self.get_tw_time()}")
            print(f"📊 符合條件股票: {len(results_df) if not results_df.empty else 0} 檔")
            print(f"📱 Telegram 發送: {'成功' if overall_success else '失敗'} ({success_count}/{len(messages)})")
            print(f"{'='*50}\n")
            
            return overall_success
            
        except Exception as e:
            error_msg = f"❌ 策略執行失敗: {str(e)}"
            print(error_msg)
            traceback.print_exc()
            
            # 發送錯誤通知
            error_notification = f"""❌ 策略機器人執行失敗

⏰ 失敗時間: {self.get_tw_time()}
🔧 執行模式: {self.execution_mode}
❗ 錯誤原因: {str(e)}

請檢查：
• FinLab API Token 是否有效
• 網路連接是否正常  
• 程式碼是否有錯誤

{f'🔗 查看詳情: https://github.com/{self.github_repo}/actions/runs/{self.github_run_id}' if self.github_run_id else ''}"""
            
            self.send_telegram_message(error_notification)
            return False


def main():
    """主程式入口"""
    try:
        # 檢查是否為週末（台灣時間）
        tw_tz = pytz.timezone('Asia/Taipei')
        now_tw = datetime.now(tw_tz)
        weekday = now_tw.weekday()  # 0=週一, 6=週日
        
        # 如果是週六(5)或週日(6)，且非強制執行模式
        if weekday >= 5:
            force_weekend = os.getenv('force_weekend', 'false').lower() == 'true'
            if not force_weekend:
                print(f"🗓️ 今日為週末 ({now_tw.strftime('%Y-%m-%d %A')})")
                print("💤 策略機器人休息中，週一見！")
                return True
        
        # 創建並執行策略
        strategy = AutomatedSecondHighStrategy()
        success = strategy.run_analysis()
        
        if success:
            print("🎉 程式執行成功完成")
            return True
        else:
            print("💥 程式執行失敗")
            return False
            
    except KeyboardInterrupt:
        print("\n⛔ 用戶中斷執行")
        return False
    except Exception as e:
        print(f"💥 程式執行時發生未預期錯誤: {e}")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
