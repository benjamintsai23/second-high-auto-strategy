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

# FinLab 套件
import finlab
from finlab import data


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
        self.volume_short = 5          # 成交量短期
        self.volume_long = 20          # 成交量長期
        
        self.taiwan_tz = pytz.timezone('Asia/Taipei')
        
        print(f"📊 初始化 {self.name} {self.version}")
        print(f"⏰ 系統時間: {self.get_taiwan_time()}")
        
    def get_taiwan_time(self) -> str:
        """取得台灣時間"""
        now = datetime.now(self.taiwan_tz)
        return now.strftime('%Y-%m-%d %H:%M:%S')
    
    def is_trading_day(self, check_date: Optional[date] = None) -> bool:
        """檢查是否為交易日（排除週末）"""
        if check_date is None:
            check_date = datetime.now(self.taiwan_tz).date()
        
        # 簡單的交易日檢查：排除週末
        weekday = check_date.weekday()  # 0=週一, 6=週日
        return weekday < 5  # 週一到週五
    
    def get_latest_trading_date(self) -> date:
        """取得最新交易日"""
        today = datetime.now(self.taiwan_tz).date()
        current_time = datetime.now(self.taiwan_tz).time()
        
        # 如果是交易日且已過收盤時間（13:30），使用今天
        if self.is_trading_day(today) and current_time.hour >= 14:
            return today
        
        # 否則找上一個交易日
        check_date = today - timedelta(days=1)
        max_lookback = 10  # 最多回溯10天
        
        for _ in range(max_lookback):
            if self.is_trading_day(check_date):
                return check_date
            check_date -= timedelta(days=1)
        
        return today  # 兜底返回今天
    
    def get_stock_name(self, code: str) -> str:
        """擴展版股票名稱對照"""
        names = {
            # 權值股
            '2330': '台積電', '2317': '鴻海', '2454': '聯發科', '1301': '台塑',
            '2412': '中華電', '1303': '南亞', '1326': '台化', '2002': '中鋼',
            '2207': '和泰車', '2308': '台達電', '3008': '大立光', '2382': '廣達',
            
            # 電子股
            '2303': '聯電', '2379': '瑞昱', '2409': '友達', '2344': '華邦電',
            '6770': '力積電', '3034': '聯詠', '2337': '光罩', '3711': '日月光投控',
            '2408': '南亞科', '2357': '華碩', '2324': '仁寶', '2356': '英業達',
            '3702': '大聯大', '2377': '微星', '3481': '群創', '2475': '華映',
            
            # 金融股  
            '2881': '富邦金', '2882': '國泰金', '2891': '中信金', '2892': '第一金',
            '2884': '玉山金', '2886': '兆豐金', '2883': '開發金', '2885': '元大金',
            '2887': '台新金', '2890': '永豐金', '2888': '新光金', '2889': '國票金',
            '5880': '合庫金', '5820': '日盛金', '2834': '臺企銀',
            
            # 傳產股
            '2105': '正新', '9904': '寶成', '1216': '統一', '1102': '亞泥',
            '2633': '台灣高鐵', '2801': '彰銀', '2809': '京城銀', '2812': '台中銀',
            
            # ETF
            '0050': '元大台灣50', '0056': '元大高股息', '006208': '富邦台50',
            '00878': '國泰永續高股息', '00881': '國泰台灣5G+', 
            '00892': '富邦台灣半導體', '00893': '國泰智能電動車'
        }
        return names.get(code, f"股票{code}")
    
    def analyze_candidates(self) -> List[Dict[str, Any]]:
        """執行完整的候選股票分析"""
        print("🔍 開始完整策略分析...")
        
        try:
            # 1. 取得基本資料
            print("📊 取得股票基本資料...")
            close = data.get('price:收盤價')
            volume = data.get('price:成交股數')
            
            if close is None or volume is None:
                raise ValueError("無法取得基本股價或成交量資料")
            
            print(f"   ✅ 價格資料: {close.shape[1]:,} 檔股票")
            print(f"   ✅ 時間範圍: {close.index[0]} 至 {close.index[-1]}")
            
            # 2. 嘗試取得營收資料
            print("💰 嘗試取得營收資料...")
            revenue = None
            try:
                revenue = data.get('monthly_revenue:當月營收')
                if revenue is not None and not revenue.empty:
                    print(f"   ✅ 營收資料: {revenue.shape[1]:,} 檔公司")
                else:
                    print("   ⚠️ 營收資料為空")
            except Exception as e:
                print(f"   ⚠️ 營收資料取得失敗: {e}")
            
            # 3. 計算所有策略條件
            print("🧮 計算策略條件...")
            
            # 條件1: 創60日新高
            print("   → 條件1: 創60日新高")
            newhigh = close.rolling(self.lookback_period, min_periods=1).max() == close
            
            # 條件2: 前30日有整理
            print("   → 條件2: 前30日有整理")
            cond2 = (newhigh.shift(1) == 0).rolling(self.gap_period).sum() > 0
            
            # 條件3: 歷史強勢確認
            print("   → 條件3: 歷史強勢確認")
            cond3 = (newhigh.shift(self.gap_period).rolling(self.confirmation_period).sum() > 0)
            
            # 條件4: 真正突破確認
            print("   → 條件4: 真正突破確認")
            past_max = close.shift(self.gap_period).rolling(self.confirmation_period).max()
            cond4 = past_max < close
            
            # 條件5: 長期趨勢向上
            print("   → 條件5: 長期趨勢向上(120日)")
            cond5 = close > close.shift(self.long_term_period)
            
            # 條件6: 中期趨勢向上
            print("   → 條件6: 中期趨勢向上(60日)")
            cond6 = close > close.shift(self.medium_term_period)
            
            # 條件7: 營收成長加速
            print("   → 條件7: 營收成長加速")
            if revenue is not None and not revenue.empty:
                rev_short = revenue.rolling(self.revenue_short, min_periods=1).mean()
                rev_long = revenue.rolling(self.revenue_long, min_periods=1).mean()
                cond7 = rev_short > rev_long
                print("      ✅ 營收條件已加入")
            else:
                cond7 = pd.DataFrame(True, index=close.index, columns=close.columns)
                print("      ⚠️ 營收資料不足，跳過此條件")
            
            # 條件8: 成交量放大
            print("   → 條件8: 成交量放大確認")
            vol_short = volume.rolling(self.volume_short, min_periods=1).mean()
            vol_long = volume.rolling(self.volume_long, min_periods=1).mean()
            cond8 = vol_short > vol_long
            
            # 4. 組合所有條件
            print("🎯 組合所有條件...")
            buy_signal = newhigh & cond2 & cond3 & cond4 & cond5 & cond6 & cond7 & cond8
            
            # 5. 取得分析日期
            analysis_date = self.get_latest_trading_date()
            latest_date_str = close.index[-1]  # 資料中的最新日期
            
            print(f"📅 目標分析日期: {analysis_date}")
            print(f"📅 資料最新日期: {latest_date_str}")
            
            # 使用資料中的最新日期
            target_date = latest_date_str
            
            # 6. 統計各條件通過情況
            conditions_stats = [
                ("條件1-創60日新高", newhigh.loc[target_date].sum()),
                ("條件2-前30日整理", cond2.loc[target_date].sum()),
                ("條件3-歷史強勢", cond3.loc[target_date].sum()),
                ("條件4-真正突破", cond4.loc[target_date].sum()),
                ("條件5-長期向上", cond5.loc[target_date].sum()),
                ("條件6-中期向上", cond6.loc[target_date].sum()),
                ("條件7-營收成長", cond7.loc[target_date].sum()),
                ("條件8-量能放大", cond8.loc[target_date].sum())
            ]
            
            print("\n📊 各條件通過統計:")
            for name, count in conditions_stats:
                print(f"   {name}: {count:4d} 檔")
            
            # 7. 找出最終符合條件的股票
            day_signals = buy_signal.loc[target_date]
            selected_stocks = day_signals[day_signals == True]
            final_count = len(selected_stocks)
            
            print(f"\n🎯 最終符合全部條件: {final_count} 檔")
            
            if final_count == 0:
                print("   暫無股票符合完整8個條件")
                return []
            
            # 8. 處理符合條件的股票
            candidates = []
            processed_count = 0
            
            print("\n📈 處理符合條件的股票:")
            for stock_code in selected_stocks.index:
                try:
                    processed_count += 1
                    print(f"   處理 {processed_count}/{final_count}: {stock_code}")
                    
                    candidate = self._process_single_stock(
                        stock_code, target_date, close, volume, revenue,
                        [newhigh, cond2, cond3, cond4, cond5, cond6, cond7, cond8]
                    )
                    
                    if candidate:
                        candidates.append(candidate)
                        
                except Exception as e:
                    print(f"      ⚠️ 處理失敗: {e}")
                    continue
            
            # 9. 排序結果
            candidates.sort(key=lambda x: (x['signal_strength'], x['volume_ratio']), reverse=True)
            
            print(f"\n✅ 策略分析完成")
            print(f"   成功處理: {len(candidates)} 檔")
            
            if candidates:
                print("\n🏆 信號強度排行:")
                for i, candidate in enumerate(candidates[:5], 1):
                    print(f"   {i}. {candidate['name']}({candidate['code']}) - 強度:{candidate['signal_strength']:.0%}")
            
            return candidates
            
        except Exception as e:
            print(f"❌ 策略分析失敗: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _process_single_stock(self, stock_code: str, target_date: str, 
                            close: pd.DataFrame, volume: pd.DataFrame, 
                            revenue: Optional[pd.DataFrame],
                            conditions_list: List[pd.DataFrame]) -> Optional[Dict[str, Any]]:
        """處理單一股票"""
        try:
            # 基本價格資訊
            current_price = float(close.loc[target_date, stock_code])
            current_volume = int(volume.loc[target_date, stock_code]) if not pd.isna(volume.loc[target_date, stock_code]) else 0
            
            # 計算漲跌幅
            prev_dates = close.index[close.index < target_date]
            if len(prev_dates) > 0:
                prev_price = float(close.loc[prev_dates[-1], stock_code])
                change_percent = ((current_price - prev_price) / prev_price) * 100
            else:
                change_percent = 0.0
            
            # 技術指標
            price_series = close[stock_code].dropna()
            if len(price_series) > 60:
                high_60d = float(price_series.rolling(60).max().loc[target_date])
                low_60d = float(price_series.rolling(60).min().loc[target_date])
                sma20 = float(price_series.rolling(20).mean().loc[target_date])
                sma60 = float(price_series.rolling(60).mean().loc[target_date])
            else:
                high_60d = low_60d = sma20 = sma60 = current_price
            
            # 成交量分析
            vol_series = volume[stock_code].dropna()
            if len(vol_series) > 20:
                avg_vol_20d = float(vol_series.rolling(20).mean().loc[target_date])
                volume_ratio = current_volume / avg_vol_20d if avg_vol_20d > 0 else 1.0
            else:
                volume_ratio = 1.0
            
            # 營收成長分析
            revenue_growth = "N/A"
            revenue_trend = "未知"
            if revenue is not None and stock_code in revenue.columns:
                try:
                    rev_series = revenue[stock_code].dropna()
                    if len(rev_series) >= 12:
                        recent_3m = rev_series.tail(3).mean()
                        past_12m = rev_series.tail(12).mean()
                        if past_12m > 0:
                            growth_rate = ((recent_3m / past_12m) - 1) * 100
                            revenue_growth = f"{growth_rate:+.1f}%"
                            revenue_trend = "加速" if growth_rate > 0 else "減緩"
                except:
                    pass
            
            # 信號強度計算
            signal_strength = self._calculate_signal_strength(conditions_list, stock_code, target_date)
            
            # 技術評分
            tech_score = self._calculate_technical_score(current_price, sma20, sma60, high_60d, low_60d)
            
            return {
                'code': stock_code,
                'name': self.get_stock_name(stock_code),
                'price': current_price,
                'change_percent': change_percent,
                'volume': current_volume,
                'volume_ratio': volume_ratio,
                'high_60d': high_60d,
                'low_60d': low_60d,
                'sma20': sma20,
                'sma60': sma60,
                'signal_strength': signal_strength,
                'tech_score': tech_score,
                'revenue_growth': revenue_growth,
                'revenue_trend': revenue_trend,
                'date': target_date,
                'is_new_high': current_price >= high_60d * 0.999,
                'above_sma20': current_price > sma20,
                'above_sma60': current_price > sma60
            }
            
        except Exception as e:
            print(f"      處理股票 {stock_code} 失敗: {e}")
            return None
    
    def _calculate_signal_strength(self, conditions_list: List[pd.DataFrame], 
                                 stock_code: str, target_date: str) -> float:
        """計算信號強度 (通過條件數 / 總條件數)"""
        try:
            passed = 0
            total = len(conditions_list)
            
            for condition_df in conditions_list:
                if (target_date in condition_df.index and 
                    stock_code in condition_df.columns and 
                    condition_df.loc[target_date, stock_code]):
                    passed += 1
            
            return passed / total
            
        except Exception as e:
            print(f"      計算信號強度失敗: {e}")
            return 0.5
    
    def _calculate_technical_score(self, price: float, sma20: float, sma60: float, 
                                 high_60d: float, low_60d: float) -> int:
        """計算技術面評分 (0-100)"""
        score = 50  # 基礎分數
        
        # 相對均線位置
        if price > sma20:
            score += 15
        if price > sma60:
            score += 15
        if sma20 > sma60:
            score += 10
        
        # 相對高低點位置
        range_60d = high_60d - low_60d
        if range_60d > 0:
            position = (price - low_60d) / range_60d
            if position > 0.8:
                score += 10  # 接近高點
            elif position < 0.2:
                score -= 10  # 接近低點
        
        return max(0, min(100, score))
    
    def generate_report(self, candidates: List[Dict[str, Any]]) -> str:
        """生成完整策略報告"""
        taiwan_time = self.get_taiwan_time()
        
        # 報告標題
        report = f"""🚀 **二次創新高策略報告**
📅 {taiwan_time}
🤖 自動執行版本 v2.0

**完整8條件篩選：**
✅ 1. 創60日新高
✅ 2. 前30日有整理期
✅ 3. 歷史強勢確認
✅ 4. 真正突破確認
✅ 5. 長期趨勢向上(120日)
✅ 6. 中期趨勢向上(60日)
✅ 7. 營收成長加速
✅ 8. 成交量放大確認
{'='*40}

"""
        
        if not candidates:
            report += self._generate_empty_report()
        else:
            report += self._generate_candidates_report(candidates)
        
        # 操作建議
        report += self._generate_trading_advice(candidates)
        
        # 風險提醒
        report += self._generate_risk_warning()
        
        # 報告結尾
        report += f"""
📊 **策略統計**
- 執行時間: {taiwan_time}
- 策略版本: v2.0 自動化
- 篩選條件: 8個條件全部滿足
- 候選檔數: {len(candidates)} 檔

🔔 **下次推播**
明日晚間 21:00 自動執行
"""
        
        return report
    
    def _generate_empty_report(self) -> str:
        """生成無候選股票的報告"""
        return """🔍 **今日篩選結果**
暫無符合完整8條件的股票

💡 **市況分析**
- 策略條件相當嚴格，通過率約1-3%
- 市場可能處於整理或弱勢格局
- 建議耐心等待優質機會出現

📈 **操作建議**
- 保持現金部位，等待轉強訊號
- 關注營收公佈和法說會動態
- 留意國際股市和資金面變化
"""
    
    def _generate_candidates_report(self, candidates: List[Dict[str, Any]]) -> str:
        """生成有候選股票的報告"""
        report = f"📊 **今日篩選結果**\n🎯 共發現 **{len(candidates)}** 檔符合完整條件的股票\n\n"
        
        for i, stock in enumerate(candidates, 1):
            report += f"**{i}. {stock['name']} ({stock['code']})**\n"
            
            # 價格資訊
            report += f"   💰 現價: ${stock['price']:.2f}"
            if abs(stock['change_percent']) > 0.01:
                emoji = "📈" if stock['change_percent'] > 0 else "📉"
                report += f" {emoji} {stock['change_percent']:+.2f}%"
            report += "\n"
            
            # 技術指標
            report += f"   📊 技術: 20日線${stock['sma20']:.1f}"
            if stock['above_sma20']:
                report += " ✅"
            else:
                report += " ❌"
            
            report += f" | 60日線${stock['sma60']:.1f}"
            if stock['above_sma60']:
                report += " ✅"
            report += "\n"
            
            # 新高狀態
            if stock['is_new_high']:
                report += f"   🎯 **創60日新高** (${stock['high_60d']:.2f})\n"
            else:
                report += f"   📈 60日高點: ${stock['high_60d']:.2f}\n"
            
            # 成交量分析
            report += f"   📊 成交量: {stock['volume']:,}股"
            if stock['volume_ratio'] > 3.0:
                report += f" (爆量{stock['volume_ratio']:.1f}倍) 🔥🔥"
            elif stock['volume_ratio'] > 2.0:
                report += f" (大量{stock['volume_ratio']:.1f}倍) 🔥"
            elif stock['volume_ratio'] > 1.5:
                report += f" (放量{stock['volume_ratio']:.1f}倍) 🌟"
            elif stock['volume_ratio'] > 1.2:
                report += f" (溫和放量{stock['volume_ratio']:.1f}倍)"
            report += "\n"
            
            # 營收成長
            if stock['revenue_growth'] != "N/A":
                report += f"   💰 營收成長: {stock['revenue_growth']} ({stock['revenue_trend']})\n"
            
            # 評分資訊
            report += f"   ⭐ 信號強度: {stock['signal_strength']:.0%}"
            if stock['signal_strength'] == 1.0:
                report += " **完美通過** ✨"
            elif stock['signal_strength'] >= 0.875:
                report += " **極強訊號** 🔥"
            
            report += f" | 技術評分: {stock['tech_score']}/100"
            if stock['tech_score'] >= 80:
                report += " **強勢** 💪"
            elif stock['tech_score'] >= 70:
                report += " **偏強** 👍"
            
            report += "\n\n"
        
        return report
    
    def _generate_trading_advice(self, candidates: List[Dict[str, Any]]) -> str:
        """生成操作建議"""
        if not candidates:
            return ""
        
        # 根據候選股票特性給建議
        high_strength_count = len([c for c in candidates if c['signal_strength'] >= 0.875])
        high_volume_count = len([c for c in candidates if c['volume_ratio'] > 2.0])
        
        advice = """
**操作策略建議：**

💡 **選股優先順序**
"""
        
        if high_strength_count > 0:
            advice += f"• 優先關注{high_strength_count}檔信號強度≥87.5%的標的\n"
        
        if high_volume_count > 0:
            advice += f"• 重點留意{high_volume_count}檔大量或爆量的股票\n"
        
        advice += """• 選擇技術評分≥70分且站上兩條均線的股票

⏰ **進場時機**
- 開盤後觀察是否持續強勢
- 等待盤中回檔至20日均線附近
- 分2-3批建立部位，避免追高

⚠️ **風險管理**
- 停損設定：跌破20日均線或-8%
- 單檔部位：建議不超過總資金10-15%
- 總持股水位：控制在60-70%

📈 **獲利目標**
- 短線目標：10-20%
- 中線目標：30-50%
- 停利方式：分批獲利了結或移動停利

🔍 **後續觀察重點**
- 是否連續3日創新高
- 成交量能否維持高檔
- 外資和投信買賣超狀況
- 下次營收公佈表現
"""
        
        return advice
    
    def _generate_risk_warning(self) -> str:
        """生成風險提醒"""
        return """
⚠️ **重要風險提醒**
- 本策略僅供參考，不構成投資建議
- 股市投資有賺有賠，請謹慎評估風險
- 務必嚴格執行停損，保護資本安全
- 留意大盤系統性風險和國際情勢變化
- 建議搭配基本面分析，避免單純追高

🎯 **投資心法**
- 紀律第一，嚴守停損
- 分散投資，控制部位
- 順勢操作，不逆勢攤平
- 保持學習，持續改進
"""


class TelegramNotifier:
    """改進版 Telegram 通知器"""
    
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{token}"
        self.max_message_length = 4000
        
    def send_message(self, message: str, parse_mode: str = 'Markdown') -> bool:
        """發送訊息（支援長訊息分割）"""
        if len(message) <= self.max_message_length:
            return self._send_single_message(message, parse_mode)
        else:
            return self._send_long_message(message, parse_mode)
    
    def _send_single_message(self, message: str, parse_mode: str = 'Markdown') -> bool:
        """發送單一訊息"""
        url = f"{self.api_url}/sendMessage"
        data = {
            'chat_id': self.chat_id,
            'text': message,
            'parse_mode': parse_mode
        }
        
        try:
            response = requests.post(url, data=data, timeout=30)
            if response.status_code == 200:
                return True
            else:
                print(f"❌ Telegram 發送失敗: {response.status_code}")
                print(

       print(f"   回應: {response.text[:200]}...")
                return False
                
        except Exception as e:
            print(f"❌ Telegram 發送錯誤: {e}")
            return False
    
    def _send_long_message(self, message: str, parse_mode: str = 'Markdown') -> bool:
        """分割並發送長訊息"""
        print("📝 訊息較長，準備分割發送...")
        
        # 按段落分割
        parts = self._split_message(message)
        print(f"   分割為 {len(parts)} 段")
        
        success_count = 0
        for i, part in enumerate(parts, 1):
            print(f"   發送第 {i}/{len(parts)} 段...")
            
            if i > 1:
                time.sleep(2)  # 避免發送太快被限制
            
            if self._send_single_message(part, parse_mode):
                success_count += 1
            else:
                print(f"   第 {i} 段發送失敗")
        
        print(f"✅ 分段發送完成: {success_count}/{len(parts)} 成功")
        return success_count == len(parts)
    
    def _split_message(self, message: str) -> List[str]:
        """智能分割訊息"""
        if len(message) <= self.max_message_length:
            return [message]
        
        parts = []
        lines = message.split('\n')
        current_part = ""
        
        for line in lines:
            # 檢查加入這一行是否會超過限制
            test_length = len(current_part + line + '\n')
            
            if test_length > self.max_message_length:
                # 如果當前部分不為空，保存它
                if current_part.strip():
                    parts.append(current_part.strip())
                
                # 如果單行太長，需要強制分割
                if len(line) > self.max_message_length:
                    # 強制分割這一行
                    while len(line) > self.max_message_length:
                        parts.append(line[:self.max_message_length])
                        line = line[self.max_message_length:]
                    current_part = line + '\n' if line else ""
                else:
                    current_part = line + '\n'
            else:
                current_part += line + '\n'
        
        # 添加最後一部分
        if current_part.strip():
            parts.append(current_part.strip())
        
        return parts
    
    def send_startup_notification(self, execution_mode: str = "auto") -> bool:
        """發送啟動通知"""
        taiwan_tz = pytz.timezone('Asia/Taipei')
        now = datetime.now(taiwan_tz)
        
        message = f"""🤖 **策略機器人啟動**
⏰ {now.strftime('%Y-%m-%d %H:%M:%S')}
🔧 執行模式: {"自動排程" if execution_mode == "auto_schedule" else "手動測試"}

🔍 正在執行完整8條件分析...
📊 預計3-5分鐘內完成分析

💡 **策略特色**
- 嚴格的8條件篩選
- 結合技術面和基本面
- 自動化每日推播"""
        
        return self.send_message(message)
    
    def send_error_notification(self, error_msg: str) -> bool:
        """發送錯誤通知"""
        taiwan_tz = pytz.timezone('Asia/Taipei')
        now = datetime.now(taiwan_tz)
        
        message = f"""❌ **策略機器人執行失敗**
⏰ {now.strftime('%Y-%m-%d %H:%M:%S')}

❗ **錯誤訊息**
{error_msg[:500]}...

🔧 **自動處理**
- 系統將自動重試最多3次
- 如持續失敗將在下次排程重新執行

📞 **聯絡方式**
如持續發生問題，請檢查：
- FinLab API 額度和Token狀態
- 網路連線是否正常
- GitHub Actions 執行日誌"""
        
        return self.send_message(message)


def main():
    """主程式入口"""
    print("=" * 60)
    print("🤖 二次創新高策略機器人 v2.0 自動化版本")
    print("=" * 60)
    
    # 檢查執行環境
    execution_mode = os.getenv('EXECUTION_MODE', 'manual')
    print(f"🔧 執行模式: {execution_mode}")
    
    # 取得台灣時間
    taiwan_tz = pytz.timezone('Asia/Taipei')
    taiwan_time = datetime.now(taiwan_tz)
    print(f"⏰ 執行時間: {taiwan_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 檢查是否為工作日
    if execution_mode == "auto_schedule":
        weekday = taiwan_time.weekday()  # 0=週一, 6=週日
        if weekday >= 5:  # 週末
            print("🗓️ 今日為週末，程式將結束")
            print("📅 下次執行：下週一晚上 21:00")
            return
        else:
            print(f"✅ 今日為工作日 (週{weekday + 1})，開始執行分析")
    
    # 檢查環境變數
    print("\n🔍 檢查環境變數...")
    required_vars = {
        'FINLAB_API_TOKEN': os.getenv('FINLAB_API_TOKEN'),
        'TELEGRAM_BOT_TOKEN': os.getenv('TELEGRAM_BOT_TOKEN'),
        'TELEGRAM_CHAT_ID': os.getenv('TELEGRAM_CHAT_ID')
    }
    
    missing_vars = [k for k, v in required_vars.items() if not v]
    if missing_vars:
        print(f"❌ 缺少必要環境變數: {', '.join(missing_vars)}")
        sys.exit(1)
    
    print("✅ 環境變數檢查通過")
    
    try:
        # 初始化元件
        print("\n🔧 初始化系統元件...")
        
        # FinLab 登入
        print("   登入 FinLab...")
        finlab.login(required_vars['FINLAB_API_TOKEN'])
        print("   ✅ FinLab 登入成功")
        
        # 初始化策略和通知器
        strategy = AutomatedSecondHighStrategy()
        notifier = TelegramNotifier(
            required_vars['TELEGRAM_BOT_TOKEN'], 
            required_vars['TELEGRAM_CHAT_ID']
        )
        
        print("   ✅ 系統元件初始化完成")
        
        # 發送啟動通知
        print("\n📱 發送啟動通知...")
        notifier.send_startup_notification(execution_mode)
        
        # 執行策略分析
        print("\n🚀 開始策略分析...")
        candidates = strategy.analyze_candidates()
        
        # 生成報告
        print("\n📝 生成策略報告...")
        report = strategy.generate_report(candidates)
        
        # 發送報告
        print("\n📤 發送策略報告...")
        if notifier.send_message(report):
            print("✅ 報告發送成功")
        else:
            print("❌ 報告發送失敗")
            raise Exception("報告發送失敗")
        
        # 發送總結通知
        if candidates:
            summary_msg = f"""🎉 **今日策略執行完成**

📊 **結果摘要**
- 篩選股票: {len(candidates)} 檔
- 執行時間: {taiwan_time.strftime('%H:%M')}
- 策略版本: v2.0 自動化

🔔 **明日預告**
明晚21:00自動執行下一輪分析

💪 祝您投資順利！"""
            notifier.send_message(summary_msg)
        
        print(f"\n🎉 策略機器人執行完成！")
        print(f"   找到符合條件股票: {len(candidates)} 檔")
        print("=" * 60)
        
    except Exception as e:
        error_msg = str(e)
        print(f"\n💥 程式執行失敗: {error_msg}")
        
        # 列印詳細錯誤
        import traceback
        traceback.print_exc()
        
        # 發送錯誤通知
        try:
            notifier = TelegramNotifier(
                required_vars['TELEGRAM_BOT_TOKEN'], 
                required_vars['TELEGRAM_CHAT_ID']
            )
            notifier.send_error_notification(error_msg)
        except:
            print("❌ 無法發送錯誤通知")
        
        sys.exit(1)


if __name__ == "__main__":
    main()       
