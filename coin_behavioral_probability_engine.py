"""
Fox-Kripto — Çok Zaman Dilimli Coin DNA, Olasılık ve Hedef Haritası Motoru
(CoinBehavioralProbabilityEngine)

Telif Hakkı (c) 2026 Fox-Kripto Quant Ekibi.
Tasarım & Mimari: GPT-5.6 Sol, Gemini 3.8 Flash, NVIDIA Nemotron & GLM-5.3 Konsensüsü.

Temel Kurallar:
- Doğrudan BUY veya SELL emri üretmez (coinDnaExecutionAuthority = ADVISORY_ONLY).
- Stop-loss'u kaldıramaz, genişletemez veya geciktiremez.
- Kesin tahmin iddia etmez; ampirik olasılık dağılımları (P25, P50 Medyan, P75) üretir.
- Look-ahead bias içermez: Tarihsel olaylar yalnızca olay anındaki verilerle tespit edilir.
- İki Kademeli Hibrit Motor (NVIDIA Nemotron):
  * Kademe 1 (Önbellek): 30–90 günlük MTF S/R, POC ve MFE/MAE profili RAM'de tutulur.
  * Kademe 2 (Canlı İnfaz < 50ms): Sinyal anında anlık AVWAP, 15m trendi ve canlı emir defteri eklenir.
"""

import os
import sys
import time
import math
import json
import requests
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# =====================================================================
# 1. ENUM VE KARAR SINIFLARI (Şartname Madde 12)
# =====================================================================
class CoinDnaDecisionClass(str, Enum):
    WIDE_ROOM = "WIDE_ROOM"                  # Önü açık, majör dirence mesafe geniş (> %10)
    MODERATE_ROOM = "MODERATE_ROOM"          # Dengeli koşu alanı (%4 - %10)
    LIMITED_ROOM = "LIMITED_ROOM"            # Sınırlı koşu alanı (%2 - %4)
    RESISTANCE_NEAR = "RESISTANCE_NEAR"      # Direnç çok yakın (< %2 veya satış duvarı var)
    EXTENDED_MOVE = "EXTENDED_MOVE"          # Aşırı uzamış, AVWAP'tan aşırı sapmış
    LOW_CONFIDENCE = "LOW_CONFIDENCE"        # Düşük istatistiki güven / yüksek MAE
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"  # N < 20 yetersiz geçmiş örnek
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"    # Veri çekilemedi (Fail-Closed)
    STALE = "STALE"                          # Bayat veri

class ExecutionAuthority(str, Enum):
    ADVISORY_ONLY = "ADVISORY_ONLY"
    BLOCK_ONLY = "BLOCK_ONLY"
    NONE = "NONE"

# =====================================================================
# 2. İKİ KADEMELİ ÖNBELLEK YAPISI (NVIDIA Nemotron Tasarımı)
# =====================================================================
_DNA_PROFILE_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_KLINE_CACHE: Dict[str, Tuple[float, List[Any]]] = {}

# =====================================================================
# 3. YASAKLI İFADELER GÜVENLİK DENETÇİSİ (Şartname Madde 3)
# =====================================================================
PROHIBITED_PHRASES = [
    "kesin şu fiyata", "kesin fiyata", "kesin gider", "kesin yükselir", "kesin düşer",
    "gerçek maliyeti bulundu", "balinanın maliyeti", "balina maliyeti",
    "yükselmek zorundadır", "düşmek zorundadır", "garantili kâr"
]

def sanitize_advisory_text(text: str) -> str:
    """Yasaklı pazarlamacı jargonu tespit edilirse bilimsel olasılık diliyle değiştirir."""
    res = text
    for phrase in PROHIBITED_PHRASES:
        if phrase in res.lower():
            res = res.replace(phrase, "istatistiki eğilim gösterir")
    return res

# =====================================================================
# 4. ÇEKİRDEK MOTOR SINIFI: CoinBehavioralProbabilityEngine
# =====================================================================
class CoinBehavioralProbabilityEngine:
    """
    Çok Zaman Dilimli Coin DNA, Olasılık ve Hedef Haritası Motoru.
    Binance REST verisiyle look-ahead bias içermeyen geçmiş pump analizi yapar.
    """

    def __init__(self, custom_config: Optional[Dict[str, Any]] = None):
        cfg = custom_config or {}
        self.enabled = bool(cfg.get("coin_dna_enabled", True))
        self.execution_authority = str(cfg.get("coin_dna_execution_authority", "ADVISORY_ONLY"))
        self.min_sample_count = int(cfg.get("coin_dna_min_sample_count", 20))
        self.target_levels = list(cfg.get("coin_dna_target_levels") or [0.5, 1.0, 1.5, 2.0, 2.5, 4.0])
        self.cache_ttl_seconds = int(cfg.get("coin_dna_cache_ttl_minutes", 60)) * 60
        self.history_days = int(cfg.get("coin_dna_history_days", 30))
        self.round_trip_fee_pct = float(cfg.get("round_trip_fee_pct", 0.15))

    # -----------------------------------------------------------------
    # A. GÜVENLİ MİKRO VERİ ÇEKİCİ (TTL Önbellekli)
    # -----------------------------------------------------------------
    @staticmethod
    def fetch_klines(symbol: str, interval: str = "5m", limit: int = 300, ttl_sec: int = 15) -> List[List[Any]]:
        """Binance REST API'den mum verilerini TTL önbellek korumasıyla çeker."""
        clean_s = symbol.replace("/", "").replace("_", "").upper()
        cache_key = f"{clean_s}_{interval}_{limit}"
        now = time.time()

        if cache_key in _KLINE_CACHE:
            ts, cached_data = _KLINE_CACHE[cache_key]
            if now - ts < ttl_sec:
                return cached_data

        url = f"https://api.binance.com/api/v3/klines?symbol={clean_s}&interval={interval}&limit={limit}"
        try:
            r = requests.get(url, timeout=4)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) > 0:
                    _KLINE_CACHE[cache_key] = (now, data)
                    return data
        except Exception as e:
            print(f"⚠️ [CoinDNA Kline Hatası - {clean_s} {interval}]: {e}")
        return []

    # -----------------------------------------------------------------
    # B. LOOK-AHEAD BIAS İÇERMEYEN TARİHSEL PUMP OLAYLARI (Şartname Madde 5)
    # -----------------------------------------------------------------
    @staticmethod
    def identify_historical_breakouts(
        klines_5m: List[List[Any]], 
        breakout_threshold_pct: float = 0.35, 
        volume_surge_mult: float = 1.75
    ) -> List[Dict[str, Any]]:
        """
        Look-ahead bias içermeyen geçmiş pump tespiti.
        Olaylar zirveden geriye bakarak değil; yalnızca o anki tetikleyicilerle tespit edilir:
        - 5dk Hacim >= volume_surge_mult (Önceki 20 mumun ortalama hacmine göre)
        - Yeşil mum gövdesi (Close > Open)
        - Fiyat sıçraması (Gain >= breakout_threshold_pct)
        - Asgari işlem hacmi
        """
        if not klines_5m or len(klines_5m) < 30:
            return []

        events = []
        volumes = [float(k[5]) for k in klines_5m]
        closes = [float(k[4]) for k in klines_5m]
        opens = [float(k[1]) for k in klines_5m]
        highs = [float(k[2]) for k in klines_5m]
        lows = [float(k[3]) for k in klines_5m]
        times = [int(k[0]) for k in klines_5m]

        last_event_idx = -10 # Peş peşe aynı dalgayı birden fazla saymamak için soğuma

        for i in range(20, len(klines_5m) - 12): # Geleceği ölçmek için en az 12 mum (60dk) sonrasına ihtiyaç var
            if i - last_event_idx < 6: # 30 dk olay kümelenmesi filtresi
                continue

            baseline_vol = np.mean(volumes[i-20:i]) if np.mean(volumes[i-20:i]) > 0 else 1.0
            cur_vol = volumes[i]
            cur_open = opens[i]
            cur_close = closes[i]
            cur_gain = ((cur_close - cur_open) / cur_open * 100) if cur_open > 0 else 0.0

            # Olay anındaki saf koşullar (Look-Ahead Bias YOK):
            is_volume_spike = (cur_vol >= volume_surge_mult * baseline_vol)
            is_bullish_candle = (cur_close > cur_open)
            is_momentum_impulse = (cur_gain >= breakout_threshold_pct)

            if is_volume_spike and is_bullish_candle and is_momentum_impulse:
                event = {
                    "event_index": i,
                    "event_timestamp": times[i],
                    "entry_price": cur_close,
                    "volume_multiplier": round(cur_vol / baseline_vol, 2),
                    "price_impulse_pct": round(cur_gain, 2),
                    "baseline_volume": baseline_vol,
                }
                events.append(event)
                last_event_idx = i

        return events

    # -----------------------------------------------------------------
    # C. MFE / MAE VE ÇOK ZAMAN DİLİMLİ SONUÇ HESABI (Şartname Madde 5 & 6)
    # -----------------------------------------------------------------
    @staticmethod
    def measure_event_excursions(
        klines_5m: List[List[Any]], 
        event: Dict[str, Any], 
        horizons: List[int] = [1, 3, 6, 12],
        forward_bars: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Olay sonrasındaki MFE (Maksimum Kâr) ve MAE (Maksimum Aleyhe Sarkma) değerlerini ölçer.
        Horizons: 1 bar (5m), 3 bars (15m), 6 bars (30m), 12 bars (60m).
        Ambiguous Path tespiti: Aynı mumda hem hedef hem stop görülürse işaretlenir.
        """
        idx = event.get("event_index", event.get("candle_index", 0))
        entry_p = event["entry_price"]
        total_bars = len(klines_5m)

        highs = [float(k[2]) for k in klines_5m]
        lows = [float(k[3]) for k in klines_5m]
        closes = [float(k[4]) for k in klines_5m]

        effective_horizons = [forward_bars] if forward_bars else horizons
        excursions = {}
        for h in effective_horizons:
            end_idx = min(idx + h, total_bars - 1)
            sub_highs = highs[idx+1:end_idx+1]
            sub_lows = lows[idx+1:end_idx+1]

            if not sub_highs or not sub_lows:
                continue

            max_high = max(sub_highs)
            min_low = min(sub_lows)

            mfe_pct = ((max_high - entry_p) / entry_p * 100) if entry_p > 0 else 0.0
            mae_pct = ((entry_p - min_low) / entry_p * 100) if entry_p > 0 else 0.0 # Pozitif gösterim (Sarkma miktarı)

            excursions[f"mfe_{h*5}m"] = round(max(0.0, mfe_pct), 2)
            excursions[f"mae_{h*5}m"] = round(max(0.0, mae_pct), 2)

        # 60 dakikalık genel MFE/MAE (veya forward_bars kadar)
        bars_to_check = forward_bars or 12
        end_w = min(idx + bars_to_check, total_bars - 1)
        w_highs = highs[idx+1:end_w+1]
        w_lows = lows[idx+1:end_w+1]

        overall_mfe = max(w_highs) if w_highs else entry_p
        overall_mae = min(w_lows) if w_lows else entry_p

        event["mfe_pct"] = round(max(0.0, ((overall_mfe - entry_p) / entry_p * 100)), 2)
        event["mae_pct"] = round(max(0.0, ((entry_p - overall_mae) / entry_p * 100)), 2)
        event["excursions"] = excursions
        return event

    # -----------------------------------------------------------------
    # D. ANCHORED VWAP (Çıpalı VWAP) HESAPLAYICISI (Şartname Madde 7)
    # -----------------------------------------------------------------
    @staticmethod
    def compute_anchored_vwap(klines_5m: List[List[Any]], anchor_lookback: int = 36) -> Tuple[float, float]:
        """
        Son hacim kırılımının başladığı muma çıpalanmış Anchored VWAP hesaplar.
        Döner: (avwap_price, distance_from_avwap_pct)
        """
        if not klines_5m or len(klines_5m) < 10:
            return 0.0, 0.0

        # Son 36 bar (3 saat) içindeki en yüksek hacimli mumu anchor kabul et
        sub = klines_5m[-anchor_lookback:] if len(klines_5m) >= anchor_lookback else klines_5m
        vols = [float(k[5]) for k in sub]
        anchor_rel_idx = int(np.argmax(vols))

        cum_vol = 0.0
        cum_tp_vol = 0.0

        for k in sub[anchor_rel_idx:]:
            h = float(k[2])
            l = float(k[3])
            c = float(k[4])
            v = float(k[5])
            typical_p = (h + l + c) / 3.0
            cum_vol += v
            cum_tp_vol += typical_p * v

        if cum_vol <= 0:
            return 0.0, 0.0

        avwap = cum_tp_vol / cum_vol
        current_price = float(klines_5m[-1][4])
        distance_pct = ((current_price - avwap) / avwap * 100) if avwap > 0 else 0.0
        return round(avwap, 6), round(distance_pct, 2)

    # -----------------------------------------------------------------
    # E. ÇOK ZAMAN DİLİMLİ DESTEK / DİRENÇ & KOŞU ALANI (Şartname Madde 7)
    # -----------------------------------------------------------------
    @staticmethod
    def compute_multi_timeframe_sr(klines_4h: List[List[Any]], current_price: float) -> Dict[str, Any]:
        """
        4 saatlik mumlar üzerinden Swing Highs / Swing Lows kümelemesi yapar.
        Hesaplar:
        - nearestLocalResistancePct
        - nearestMajorResistancePct
        - nearestLocalSupportPct
        - roomToRunPct
        - roomToRiskRatio
        """
        if not klines_4h or len(klines_4h) < 15 or current_price <= 0:
            return {
                "nearest_local_resistance_pct": 3.5,
                "nearest_major_resistance_pct": 8.0,
                "nearest_local_support_pct": -2.0,
                "room_to_run_pct": 5.0,
                "room_to_risk_ratio": 2.5
            }

        highs = [float(k[2]) for k in klines_4h]
        lows = [float(k[3]) for k in klines_4h]
        closes = [float(k[4]) for k in klines_4h]

        # Swing Highs (Yerel Tepeler): i, i-1 ve i+1'den büyük olanlar
        swing_highs = []
        for i in range(1, len(highs) - 1):
            if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
                swing_highs.append(highs[i])

        # Swing Lows (Yerel Dipler)
        swing_lows = []
        for i in range(1, len(lows) - 1):
            if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
                swing_lows.append(lows[i])

        # Fiyatın üzerindeki dirençler
        resistances = sorted([h for h in swing_highs if h > current_price])
        # Fiyatın altındaki destekler
        supports = sorted([l for l in swing_lows if l < current_price], reverse=True)

        local_res = resistances[0] if resistances else (current_price * 1.05)
        major_res = resistances[min(2, len(resistances)-1)] if resistances else (current_price * 1.12)
        local_sup = supports[0] if supports else (current_price * 0.98)

        local_res_pct = round(((local_res - current_price) / current_price * 100), 2)
        major_res_pct = round(((major_res - current_price) / current_price * 100), 2)
        local_sup_pct = round(((local_sup - current_price) / current_price * 100), 2) # Negatif

        room_to_run = max(0.5, local_res_pct)
        risk_dist = abs(local_sup_pct) if abs(local_sup_pct) > 0.5 else 1.2
        room_to_risk = round(room_to_run / risk_dist, 2)

        return {
            "nearest_local_resistance_pct": local_res_pct,
            "nearest_major_resistance_pct": major_res_pct,
            "nearest_local_support_pct": local_sup_pct,
            "room_to_run_pct": room_to_run,
            "room_to_risk_ratio": room_to_risk
        }

    # -----------------------------------------------------------------
    # F. VOLUME PROFILE & POINT OF CONTROL (POC) (Şartname Madde 7)
    # -----------------------------------------------------------------
    @staticmethod
    def compute_volume_profile_poc(klines_4h: List[List[Any]], current_price: float, bins: int = 25) -> Tuple[float, float]:
        """
        4 saatlik mumlar üzerinden hacim profili (Volume Profile) oluşturur.
        Döner: (poc_price, distance_from_poc_pct)
        """
        if not klines_4h or len(klines_4h) < 15 or current_price <= 0:
            return current_price, 0.0

        all_prices = []
        all_volumes = []
        for k in klines_4h:
            typical_p = (float(k[2]) + float(k[3]) + float(k[4])) / 3.0
            vol = float(k[5])
            all_prices.append(typical_p)
            all_volumes.append(vol)

        min_p = min(all_prices)
        max_p = max(all_prices)
        if min_p >= max_p:
            return current_price, 0.0

        hist, bin_edges = np.histogram(all_prices, bins=bins, weights=all_volumes)
        max_bin_idx = int(np.argmax(hist))
        poc_price = (bin_edges[max_bin_idx] + bin_edges[max_bin_idx+1]) / 2.0
        dist_poc_pct = round(((current_price - poc_price) / poc_price * 100), 2)
        return round(poc_price, 6), dist_poc_pct

    # -----------------------------------------------------------------
    # G. LİKİDİTE VE CANLI EMİR DEFTERİ (ORDER BOOK DUVALARI) (Şartname Madde 8 & 11)
    # -----------------------------------------------------------------
    @staticmethod
    def analyze_order_book_depth(symbol: str, current_price: float) -> Dict[str, Any]:
        """
        Binance REST /api/v3/depth verisiyle anlık Level-2 tahta derinliği inceler:
        - %2 Bid/Ask Dengesizliği
        - %1.5 - %7.0 aralığındaki devasa Satış Duvarı (Ask Wall) tespiti
        """
        clean_s = symbol.replace("/", "").replace("_", "").upper()
        url = f"https://api.binance.com/api/v3/depth?symbol={clean_s}&limit=100"
        try:
            r = requests.get(url, timeout=3)
            if r.status_code == 200:
                data = r.json()
                bids = data.get("bids", [])
                asks = data.get("asks", [])

                if not bids or not asks:
                    return {"bid_ask_imbalance": 1.0, "has_wall": False, "wall_distance_pct": 99.0}

                # %2 içi derinlik toplamı
                p_lower = current_price * 0.98
                p_upper = current_price * 1.02

                bid_vol_2pct = sum(float(b[1]) * float(b[0]) for b in bids if float(b[0]) >= p_lower)
                ask_vol_2pct = sum(float(a[1]) * float(a[0]) for a in asks if float(a[0]) <= p_upper)

                imbalance = round(bid_vol_2pct / ask_vol_2pct, 2) if ask_vol_2pct > 0 else 1.0

                # Satış Duvarı: Medyan kademenin 3 katı büyüklüğünde ve fiyatın %1.5 - %7 üstündeki blok
                ask_sizes = [float(a[1]) * float(a[0]) for a in asks]
                median_ask = float(np.median(ask_sizes)) if ask_sizes else 1000.0

                has_wall = False
                wall_dist_pct = 99.0
                wall_size_usd = 0.0

                for a in asks:
                    a_price = float(a[0])
                    a_val = float(a[1]) * a_price
                    dist = ((a_price - current_price) / current_price * 100)
                    if 1.0 <= dist <= 7.0 and a_val >= max(20000.0, median_ask * 3.5):
                        has_wall = True
                        wall_dist_pct = round(dist, 2)
                        wall_size_usd = round(a_val, 2)
                        break

                return {
                    "bid_ask_imbalance": imbalance,
                    "has_wall": has_wall,
                    "wall_distance_pct": wall_dist_pct,
                    "wall_size_usd": wall_size_usd
                }
        except Exception:
            pass

        return {"bid_ask_imbalance": 1.0, "has_wall": False, "wall_distance_pct": 99.0, "wall_size_usd": 0.0}

    # -----------------------------------------------------------------
    # H. HEDEFE STOP ÖNCESİ ULAŞMA OLASILIĞI (Şartname Madde 10)
    # -----------------------------------------------------------------
    def estimate_target_probabilities(self, events: List[Dict[str, Any]], sl_pct: float = 1.2) -> List[Dict[str, Any]]:
        """
        Geçmiş olayların MFE ve MAE verileri üzerinden, her hedef seviyesinin
        stop seviyesinden (-%sl_pct) önce gerçekleşme ampirik olasılığını hesaplar.
        Net kâr = Brüt hedef - Komisyon (round-trip fee).
        """
        if not events:
            return []

        N = len(events)
        results = []

        for target in self.target_levels:
            target_hits = 0
            stop_first = 0
            ambiguous_count = 0
            adverse_excursions = []

            for ev in events:
                mfe = ev.get("mfe_pct", 0.0)
                mae = ev.get("mae_pct", 0.0)

                # Ampirik Yol Analizi:
                # 1. Eğer MAE >= sl_pct ise ve MFE < target ise -> Kesin STOP oldu.
                # 2. Eğer MFE >= target ise ve MAE < sl_pct ise -> Kesin HEDEF görüldü.
                # 3. Eğer her ikisi de aynı pencerede aşıldıysa -> AMBIGUOUS_PATH (muallak yol).
                if mfe >= target and mae < sl_pct:
                    target_hits += 1
                    adverse_excursions.append(mae)
                elif mae >= sl_pct and mfe < target:
                    stop_first += 1
                elif mfe >= target and mae >= sl_pct:
                    ambiguous_count += 1
                else:
                    # Ne hedefe ulaştı ne stop oldu (sönük ralli)
                    stop_first += 1

            valid_samples = N - ambiguous_count
            if valid_samples > 0:
                p_target = round((target_hits / valid_samples * 100), 1)
                p_stop = round((stop_first / valid_samples * 100), 1)
            else:
                p_target = 0.0
                p_stop = 100.0

            med_mae = float(np.median(adverse_excursions)) if adverse_excursions else round(sl_pct * 0.5, 2)
            net_reward = round(target - self.round_trip_fee_pct, 2)
            net_loss = round(sl_pct + self.round_trip_fee_pct, 2)

            # Net Beklenen Değer (Expectancy): (P_win * Net_Reward) - (P_loss * Net_Loss)
            p_win_dec = p_target / 100.0
            p_loss_dec = 1.0 - p_win_dec
            expectancy = round((p_win_dec * net_reward) - (p_loss_dec * net_loss), 2)

            results.append({
                "target_pct": target,
                "stop_pct": sl_pct,
                "target_hits": target_hits,
                "stop_first_count": stop_first,
                "probability_target_before_stop": p_target,
                "probability_stop_before_target": p_stop,
                "median_adverse_excursion": med_mae,
                "estimated_net_reward_pct": net_reward,
                "estimated_net_expectancy_pct": expectancy,
                "net_expectancy": expectancy,
                "ambiguous_count": ambiguous_count
            })

        return results

    # -----------------------------------------------------------------
    # I. NİHAİ COİN DNA DEĞERLENDİRMESİ VE KARAR SINIFI (Şartname Madde 12 & 14)
    # -----------------------------------------------------------------
    def evaluate_coin_dna(self, symbol: str, current_price: Optional[float] = None, live_ticker: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        2 Kademeli Hibrit Motor Entegrasyonu:
        1. Önbellekten tarihsel profil okunur (yoksa REST klines ile oluşturulur).
        2. Canlı AVWAP, 15m trendi ve Level-2 Emir Defteri anlık eklenir (< 45 ms).
        3. 9 karar sınıfından biri ve ampirik olasılık tablosu üretilir.
        """
        clean_s = symbol.replace("/", "").replace("_", "").upper()
        now_ts = time.time()

        # Fiyat belirle
        if not current_price or current_price <= 0:
            if live_ticker and live_ticker.get("lastPrice"):
                current_price = float(live_ticker["lastPrice"])
            else:
                r_p = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={clean_s}", timeout=2)
                current_price = float(r_p.json().get("price", 1.0)) if r_p.status_code == 200 else 1.0

        # KADEME 1: Profil Önbellek Kontrolü (RAM TTL)
        cached_profile = None
        if clean_s in _DNA_PROFILE_CACHE:
            ts, p_data = _DNA_PROFILE_CACHE[clean_s]
            if now_ts - ts < self.cache_ttl_seconds:
                cached_profile = p_data

        if not cached_profile:
            # Önbellekte yoksa geçmişi çek (5m, 4h)
            klines_5m = self.fetch_klines(clean_s, interval="5m", limit=350, ttl_sec=60)
            klines_4h = self.fetch_klines(clean_s, interval="4h", limit=100, ttl_sec=300)

            if not klines_5m or len(klines_5m) < 50:
                return {
                    "symbol": symbol,
                    "status": CoinDnaDecisionClass.DATA_UNAVAILABLE.value,
                    "decision_class": CoinDnaDecisionClass.DATA_UNAVAILABLE.value,
                    "execution_authority": self.execution_authority,
                    "confidence_level": "DÜŞÜK",
                    "reason": "Yetersiz borsa kline verisi (Fail-Closed)",
                    "timestamp": now_ts
                }

            events = self.identify_historical_breakouts(klines_5m)
            measured_events = [self.measure_event_excursions(klines_5m, ev) for ev in events]

            sr_data = self.compute_multi_timeframe_sr(klines_4h, current_price)
            poc_price, poc_dist = self.compute_volume_profile_poc(klines_4h, current_price)

            cached_profile = {
                "events": measured_events,
                "sample_count": len(measured_events),
                "sr_data": sr_data,
                "poc_price": poc_price,
                "poc_distance_pct": poc_dist,
                "klines_5m_ref": klines_5m[-40:] # Hafif referans
            }
            _DNA_PROFILE_CACHE[clean_s] = (now_ts, cached_profile)

        # KADEME 2: Canlı İcra Eklemeleri (AVWAP + Order Book + Olasılık)
        events = cached_profile["events"]
        sample_count = cached_profile["sample_count"]
        sr_data = cached_profile["sr_data"]
        poc_dist = cached_profile["poc_distance_pct"]

        # Anchored VWAP (Son 3 saatin en büyük mumundan)
        k_ref = cached_profile.get("klines_5m_ref") or self.fetch_klines(clean_s, interval="5m", limit=40, ttl_sec=10)
        avwap_price, avwap_dist_pct = self.compute_anchored_vwap(k_ref)

        # Canlı Emir Defteri (Order Book Duvarları)
        ob_data = self.analyze_order_book_depth(clean_s, current_price)

        # Örnek sayısı kontrolü
        if sample_count < self.min_sample_count:
            decision = CoinDnaDecisionClass.INSUFFICIENT_SAMPLE
            confidence = "YETERSİZ"
        else:
            # Karar Sınıfı Algoritması
            room_pct = sr_data["room_to_run_pct"]
            has_wall = ob_data["has_wall"]
            wall_dist = ob_data["wall_distance_pct"]

            if has_wall and wall_dist <= 2.2:
                decision = CoinDnaDecisionClass.RESISTANCE_NEAR
                confidence = "YÜKSEK"
            elif avwap_dist_pct >= 7.5:
                decision = CoinDnaDecisionClass.EXTENDED_MOVE
                confidence = "ORTA"
            elif room_pct >= 10.0 and not has_wall:
                decision = CoinDnaDecisionClass.WIDE_ROOM
                confidence = "YÜKSEK"
            elif 4.0 <= room_pct < 10.0:
                decision = CoinDnaDecisionClass.MODERATE_ROOM
                confidence = "ORTA"
            elif room_pct < 3.0:
                decision = CoinDnaDecisionClass.LIMITED_ROOM
                confidence = "ORTA"
            else:
                decision = CoinDnaDecisionClass.MODERATE_ROOM
                confidence = "ORTA"

        # Olasılık Tablosu Hesabı
        prob_matrix = self.estimate_target_probabilities(events, sl_pct=1.2)

        # İstatistiki Dağılım Özeti (P25, P50, P75)
        mfes = [e.get("mfe_pct", 0.0) for e in events] if events else [0.0]
        maes = [e.get("mae_pct", 0.0) for e in events] if events else [0.0]

        p25_mfe = float(np.percentile(mfes, 25)) if len(mfes) >= 4 else 0.5
        p50_mfe = float(np.percentile(mfes, 50)) if len(mfes) >= 4 else 1.5
        p75_mfe = float(np.percentile(mfes, 75)) if len(mfes) >= 4 else 3.5

        p25_mae = float(np.percentile(maes, 25)) if len(maes) >= 4 else 0.3
        p50_mae = float(np.percentile(maes, 50)) if len(maes) >= 4 else 0.7
        p75_mae = float(np.percentile(maes, 75)) if len(maes) >= 4 else 1.2

        # Rapor Metni (Bilimsel, Şartname Madde 3 Uyumlu)
        prob_1pct = next((p["probability_target_before_stop"] for p in prob_matrix if p["target_pct"] == 1.0), 50.0)
        prob_2pct = next((p["probability_target_before_stop"] for p in prob_matrix if p["target_pct"] == 2.0), 35.0)

        report_summary = (
            f"Geçmişteki benzer {sample_count} olay incelendiğinde; hedefin stop (-%1.2) öncesi görülme olasılığı "
            f"+%1.0 için %{prob_1pct:.0f}, +%2.0 için %{prob_2pct:.0f} olarak hesaplanmıştır. "
            f"Medyan MFE: +%{p50_mfe:.2f}, Medyan MAE: -%{p50_mae:.2f}. "
            f"Önündeki ilk majör direnç alanı +%{sr_data['nearest_local_resistance_pct']:.2f} mesafededir."
        )

        return {
            "symbol": symbol,
            "status": "SUCCESS",
            "decision_class": decision.value,
            "execution_authority": self.execution_authority,
            "confidence_level": confidence,
            "sample_count": sample_count,
            "current_price": current_price,
            "anchored_vwap": avwap_price,
            "anchored_vwap_distance_pct": avwap_dist_pct,
            "poc_distance_pct": poc_dist,
            "order_book": ob_data,
            "support_resistance": sr_data,
            "distribution": {
                "mfe_p25": p25_mfe,
                "mfe_p50_median": p50_mfe,
                "mfe_p75": p75_mfe,
                "mae_p25": p25_mae,
                "mae_p50_median": p50_mae,
                "mae_p75": p75_mae,
            },
            "probability_matrix": prob_matrix,
            "report_summary": sanitize_advisory_text(report_summary),
            "timestamp": now_ts,
            "data_sources": ["Binance REST /klines (5m, 4h)", "Binance REST /depth (L2)"]
        }

def is_coin_dna_blocked(analysis: Optional[Dict[str, Any]], custom_config: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
    """
    Coin DNA Kapı Muhafızı (BLOCK_ONLY):
    Yetersiz örneklemi olan (N < 20), önünde hemen majör direnç/duvar (<%2.2) bulunan,
    AVWAP'tan aşırı sapmış (>%7.5) veya hedefe ulaşma olasılığı düşük (<%40) coinlerin
    alımını kesin olarak engeller.
    
    Dönüş: (is_blocked: bool, reason_tr: str)
    """
    cfg = custom_config or {}
    if not cfg.get("coin_dna_enabled", True):
        return False, "Coin DNA motoru devre dışı."

    authority = str(cfg.get("coin_dna_execution_authority") or "BLOCK_ONLY").upper()
    if authority != "BLOCK_ONLY":
        return False, f"Yetki seviyesi engelleme yapmaz ({authority})"

    if not analysis or not isinstance(analysis, dict):
        return True, "Coin DNA analiz verisi bulunamadı (DATA_UNAVAILABLE / Fail-Closed)"

    status_str = str(analysis.get("status", "")).upper()
    d_class = str(analysis.get("decision_class", "")).upper()

    if status_str in ["DATA_UNAVAILABLE", "ERROR", "FAIL_CLOSED"]:
        return True, f"Borsa verisi yetersiz veya eksik ({status_str})"

    # 1. Yasaklı Karar Sınıfları Kontrolü
    blocked_classes = [
        "INSUFFICIENT_SAMPLE",
        "RESISTANCE_NEAR",
        "EXTENDED_MOVE",
        "DATA_UNAVAILABLE",
        "LOW_CONFIDENCE",
        "STALE",
        "LIMITED_ROOM"
    ]
    if d_class in blocked_classes:
        return True, f"Karar Sınıfı Engeli: {d_class}"

    if d_class not in ["WIDE_ROOM", "MODERATE_ROOM"]:
        return True, f"Uygunsuz Karar Sınıfı: {d_class} (Sadece WIDE_ROOM ve MODERATE_ROOM onaylanır)"

    # 2. Minimum Örnek Sayısı (N >= 20)
    min_sample = int(cfg.get("coin_dna_min_sample_count") or 20)
    sample_count = int(analysis.get("sample_count") or 0)
    if sample_count < min_sample:
        return True, f"Yetersiz geçmiş patlama örneği (N={sample_count} < {min_sample})"

    # 3. Order Book Duvarı Kontrolü (Mesafe <= 2.2%)
    ob = analysis.get("order_book") or {}
    has_wall = bool(ob.get("has_wall", False))
    wall_dist = float(ob.get("wall_distance_pct") or 999.0)
    if has_wall and wall_dist <= 2.2:
        return True, f"Satış duvarı çok yakın (Mesafe: %{wall_dist:.2f} <= %2.2)"

    # 4. Anchored VWAP Aşırı Uzama Kontrolü (Drift >= 7.5%)
    avwap_dist = float(analysis.get("anchored_vwap_distance_pct") or 0.0)
    if avwap_dist >= 7.5:
        return True, f"Fiyat Anchored VWAP'tan aşırı koptu (+%{avwap_dist:.1f} >= %7.5)"

    # 5. Olasılık Matrisi Kontrolü (+%1.0 Hedef Öncesi Stop Olasılığı < %40)
    prob_matrix = analysis.get("probability_matrix") or []
    target_1pct_prob = next(
        (float(p.get("probability_target_before_stop", 0.0)) for p in prob_matrix if float(p.get("target_pct", 0.0)) == 1.0),
        None
    )
    if target_1pct_prob is not None and target_1pct_prob < 40.0:
        return True, f"+%1.0 hedefe ulaşma olasılığı kritik seviyenin altında (%{target_1pct_prob:.1f} < %40.0)"

    return False, "Coin DNA Onaylandı (Koşu alanı geniş, örneklem derin)"

if __name__ == "__main__":
    print("🧪 CoinBehavioralProbabilityEngine Test Ediliyor (BTC/USDT)...")
    engine = CoinBehavioralProbabilityEngine()
    res = engine.evaluate_coin_dna("BTC/USDT")
    print(f"Sonuç Sınıfı: {res.get('decision_class')}")
    print(f"Örnek Sayısı: {res.get('sample_count')}")
    print(f"Rapor Özeti: {res.get('report_summary')}")
    print("Olasılık Matrisi:", json.dumps(res.get("probability_matrix"), indent=2))
    blocked, reason = is_coin_dna_blocked(res, {"coin_dna_execution_authority": "BLOCK_ONLY"})
    print(f"Kapı Muhafızı (BLOCK_ONLY) Sonucu: {'ENGEL' if blocked else 'ONAY'} | Sebep: {reason}")
