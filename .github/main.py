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
