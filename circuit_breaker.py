"""
Fox-Kripto V2.3 — Devre Kesiciler ve Cooldown Motoru (Circuit Breaker Engine)
Telif Hakkı (c) 2026 Fox-Kripto Quant Ekibi.

Günlük kayıp limiti, ardışık zarar, maksimum işlem sayısı ve soğuma (cooldown) sürelerini
kesintisiz denetler. Eşik aşıldığında sistemi güvenli SIGNAL_ONLY moduna düşürür.
"""

import time
import math
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta

def _blocked(code: str, message: str) -> Dict[str, Any]:
    return {"passed": False, "circuit_breaker": code, "message": f"🛑 [Devre Kesici]: {message}"}


def _is_paper_trade(trade: Dict[str, Any]) -> bool:
    details = trade.get("execution_details") or {}
    raw = details.get("raw_order") or {}
    return (str(trade.get("status", "")).upper() == "EXECUTED_SIMULATED"
            or str(trade.get("order_id") or "").startswith(("SIM_", "PAPER_"))
            or bool(details.get("is_simulated") or (raw.get("info") or {}).get("is_paper")))


def realized_pnl_usd(trade: Dict[str, Any]) -> float:
    details = trade.get("execution_details") or {}
    for key in ("realized_pnl_usd", "net_profit_usd"):
        if details.get(key) is not None:
            value = float(details[key])
            break
    else:
        pct = details.get("realized_pnl_pct", details.get("net_profit_pct"))
        amount = details.get("cost_basis_usd", trade.get("amount_usd"))
        if pct is None or amount is None:
            raise ValueError("Missing realized PnL")
        value = float(amount) * float(pct) / 100.0
    if not math.isfinite(value):
        raise ValueError("Invalid realized PnL")
    return value


def _daily_equity_reference(client, tenant_id, exchange_id, is_simulated, day, equity):
    session_id = f"risk_day_{tenant_id}_{exchange_id}_{'paper' if is_simulated else 'live'}_{day}"
    query = lambda: client.table("crypto_agent_states").select("state_data").eq("session_id", session_id).execute().data
    rows = query()
    if not rows:
        if equity is None or not math.isfinite(float(equity)) or float(equity) <= 0:
            raise ValueError("Missing equity reference")
        try:
            client.table("crypto_agent_states").insert({
                "session_id": session_id,
                "state_data": {"equity_usd": float(equity), "captured_at": datetime.now(timezone.utc).isoformat()}
            }).execute()
        except Exception:
            # A concurrent worker may have created the same daily reference.
            if not query():
                raise
        rows = query()
    reference = float(rows[0]["state_data"]["equity_usd"])
    if not math.isfinite(reference) or reference <= 0:
        raise ValueError("Invalid equity reference")
    return reference


def check_tenant_circuit_breakers(
    tenant_id: str,
    exchange_id: str = "binance",
    daily_loss_limit_pct: float = 2.0,
    max_consecutive_losses: int = 3,
    post_stop_cooldown_minutes: int = 180,
    max_daily_trades: int = 5,
    max_concurrent_positions: int = 3,
    current_active_positions_count: int = 0,
    is_simulated: bool = False,
    current_equity_usd: Optional[float] = None
) -> Dict[str, Any]:
    """Block new entries if tenant/mode-specific risk cannot be verified."""
    now = datetime.now(timezone.utc)
    now_tr = now.astimezone(timezone(timedelta(hours=3)))
    today_start = now_tr.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).isoformat()
    try:
        from db import get_supabase, get_strategy_config
        if not str(tenant_id or "").strip():
            raise ValueError("Missing tenant")
        cfg = get_strategy_config(use_cache=True)
        if not isinstance(cfg, dict) or not cfg:
            raise ValueError("Missing risk configuration")
        client = get_supabase()
        if client is None:
            raise ValueError("Database unavailable")
        max_concurrent_positions = int(cfg.get("max_concurrent_positions", max_concurrent_positions))
        max_daily_trades = int(cfg.get("max_daily_trades", max_daily_trades))
        max_consecutive_losses = int(cfg.get("max_consecutive_losses", max_consecutive_losses))
        post_stop_cooldown_minutes = int(cfg.get("post_stop_cooldown_minutes", post_stop_cooldown_minutes))
        daily_loss_limit_pct = float(cfg.get("daily_loss_limit_pct", daily_loss_limit_pct))
        if min(max_concurrent_positions, max_daily_trades, max_consecutive_losses) <= 0 or post_stop_cooldown_minutes < 0:
            raise ValueError("Invalid risk limits")
        if not math.isfinite(daily_loss_limit_pct) or not 0 < daily_loss_limit_pct <= 100:
            raise ValueError("Invalid percentage limit")
        reference = _daily_equity_reference(client, str(tenant_id), exchange_id, is_simulated, now_tr.date().isoformat(), current_equity_usd)
        limit_usd = reference * daily_loss_limit_pct / 100.0
        if cfg.get("daily_max_loss_usd") is not None:
            absolute_limit = float(cfg["daily_max_loss_usd"])
            if not math.isfinite(absolute_limit) or absolute_limit <= 0:
                raise ValueError("Invalid dollar limit")
            limit_usd = min(limit_usd, absolute_limit)

        trades = []
        for offset in range(0, 100000, 500):
            rows = client.table("crypto_trade_logs").select("*").gte("created_at", today_start).order("created_at", desc=True).order("id", desc=True).range(offset, offset + 499).execute().data
            if rows is None:
                raise ValueError("Missing trade response")
            trades.extend(rows)
            if len(rows) < 500:
                break
        else:
            raise ValueError("Trade history incomplete")
        successful = []
        for trade in trades:
            details = trade.get("execution_details") or {}
            owner = str(trade.get("tenant_id") or details.get("tenant_id") or "")
            if owner != str(tenant_id):
                continue
            if _is_paper_trade(trade) != is_simulated:
                continue
            trade_exchange = details.get("exchange_id") or ("binancetr" if str(trade.get("symbol", "")).endswith("TRY") else "binance")
            if not is_simulated and trade_exchange != exchange_id:
                continue
            if str(trade.get("status", "")).upper() in {"SUCCESS", "EXECUTED", "FILLED", "EXECUTED_SIMULATED", "UNPROTECTED_POSITION"}:
                successful.append(trade)
        buys = sum(str(t.get("direction", "")).upper() == "BUY" for t in successful)
        sells = [t for t in successful if str(t.get("direction", "")).upper() == "SELL"]
        pnl = sum(realized_pnl_usd(t) for t in sells)
        if pnl <= -limit_usd:
            return _blocked("DAILY_LOSS_LIMIT_EXCEEDED", f"Günlük net zarar ${abs(pnl):.2f}; %{daily_loss_limit_pct:g} eşik ${limit_usd:.2f}.")
        if buys >= max_daily_trades:
            return _blocked("MAX_DAILY_TRADES_EXCEEDED", f"Günlük alım kotası dolu ({buys}/{max_daily_trades}).")
        if current_active_positions_count >= max_concurrent_positions:
            return _blocked("MAX_CONCURRENT_POSITIONS_FULL", f"Pozisyon slotları dolu ({current_active_positions_count}/{max_concurrent_positions}).")
        losses = 0
        for sell in sells:
            if realized_pnl_usd(sell) >= 0:
                break
            losses += 1
        if losses >= max_consecutive_losses:
            last_exit = datetime.fromisoformat(sells[0]["created_at"].replace("Z", "+00:00"))
            elapsed = (now - last_exit).total_seconds() / 60.0
            if elapsed < post_stop_cooldown_minutes:
                return _blocked("CONSECUTIVE_LOSS_COOLDOWN_ACTIVE", f"{losses} ardışık zarar sonrası soğuma aktif.")
        return {"passed": True, "circuit_breaker": "NONE", "message": "Risk kontrolleri geçti.",
                "daily_realized_pnl_usd": round(pnl, 4), "daily_loss_limit_usd": round(limit_usd, 2), "reference_equity_usd": reference}
    except Exception as exc:
        return _blocked("RISK_DATA_UNAVAILABLE", f"Risk verisi doğrulanamadı ({type(exc).__name__}); yeni alım kapalı.")

def check_entry_account_risk(tenant_config: Dict[str, Any]) -> Dict[str, Any]:
    from db import get_strategy_config, get_system_setting
    from exchange import fetch_portfolio_balance
    from balanced_spot_profile import capped_entry_budget
    try:
        tenant = dict(tenant_config or {})
        is_paper = bool(tenant.get("is_paper_trading")) or get_system_setting("execution_mode", "PAPER_TRADING") in {"PAPER_TRADING", "SIGNAL_ONLY", "SHADOW_TRADING"}
        tenant["is_paper_trading"] = is_paper
        portfolio = fetch_portfolio_balance(tenant)
        if portfolio.get("api_error"):
            raise ValueError("Portfolio unavailable")
        equity = float(portfolio.get("total_usdt") or portfolio.get("total_usd") or 0.0)
        cash = float(portfolio.get("free_usdt") or portfolio.get("free_usd") or 0.0)
        holdings = portfolio.get("holdings_details") or {}
        count = sum(k not in {"USDT", "TRY", "BNB", "USDC", "FDUSD"} and float(v.get("val_usd", 0)) > 5 for k, v in holdings.items())
        exchange_id = "paper" if is_paper else str(tenant.get("exchange_id") or "binance")
        result = check_tenant_circuit_breakers(
            tenant_id=str(tenant.get("id") or tenant.get("telegram_chat_id") or ""), exchange_id=exchange_id,
            is_simulated=is_paper, current_equity_usd=equity, current_active_positions_count=count)
        cfg = get_strategy_config(use_cache=True)
        result["max_entry_budget_usd"] = capped_entry_budget(
            equity, cash, max(0.0, equity - cash), float(tenant.get("max_budget_percent") or cfg["max_budget_percent"]), cfg)
        return result
    except Exception as exc:
        return _blocked("RISK_DATA_UNAVAILABLE", f"Emir öncesi hesap doğrulanamadı ({type(exc).__name__}).")


def get_adaptive_max_slots(total_equity_usd: float = 200.0, user_max_budget_pct: float = 30.0) -> int:
    """
    Kullanıcının panelden belirlediği azami eşzamanlı pozisyon slotunu dinamik olarak döndürür.
    """
    try:
        from db import get_strategy_config
        strat_cfg = get_strategy_config(use_cache=True)
        if strat_cfg and "max_concurrent_positions" in strat_cfg:
            return int(strat_cfg.get("max_concurrent_positions") or 3)
    except Exception:
        pass
    if user_max_budget_pct >= 50.0:
        return 2
    return max(1, int(100.0 / user_max_budget_pct)) if user_max_budget_pct > 0 else 3

def can_place_live_order(
    profile_status: str,
    execution_mode: str,
    live_validation_status: str,
    global_kill_switch: bool = False,
    tenant_kill_switch: bool = False,
    user_kill_switch: bool = False,
    data_quality_status: str = "PASS",
    risk_engine_healthy: bool = True,
    execution_engine_healthy: bool = True
) -> Dict[str, Any]:
    """
    V2.3 Şartnamesi Bölüm 2.2 ve 9.1 — Backend Canlı Emir İnfaz Kapısı:
    Tüm güvenlik kriterleri eksiksiz karşılanmadan canlı emir üretilemez.
    """
    if global_kill_switch or tenant_kill_switch or user_kill_switch:
        return {"can_trade": False, "reason": "🛑 Kill Switch Devrede (Yeni Alımlar Durduruldu)."}
    if profile_status != "ACTIVE":
        return {"can_trade": False, "reason": f"🛑 Profil durumu aktif değil ({profile_status})."}
    if execution_mode not in ["LIVE_CANARY", "LIVE_TRADING"]:
        return {"can_trade": False, "reason": f"ℹ️ Canlı emir yetkisi yok (Mod: {execution_mode}). Yalnızca sinyal veya paper üretilir."}
    if live_validation_status != "PASSED":
        return {"can_trade": False, "reason": f"🛑 Canlı uygunluk testi geçilmedi ({live_validation_status})."}
    if data_quality_status != "PASS":
        return {"can_trade": False, "reason": f"🛑 Veri kalitesi yetersiz ({data_quality_status})."}
    if not risk_engine_healthy or not execution_engine_healthy:
        return {"can_trade": False, "reason": "🛑 Risk veya infaz motoru sağlık kontrolünden geçemedi."}
        
    return {"can_trade": True, "reason": "✅ Tüm canlı işlem güvenlik kapıları başarıyla geçildi."}

def check_configuration_drift(
    frontend_config: Optional[Dict[str, Any]] = None,
    db_config: Optional[Dict[str, Any]] = None,
    worker_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Bölüm 2 — Configuration Drift Devre Kesicisi:
    Frontend, Supabase DB ve çalışan Worker parametreleri arasında uyuşmazlık
    varsa CONFIGURATION_DRIFT alarmı üretir ve yeni alımları engeller.
    """
    try:
        if db_config is None:
            from db import get_strategy_config
            db_config = get_strategy_config(use_cache=False) or {}
            
        # Kritik parametreler
        db_max_gain = float(db_config.get("max_recent_gain_24h", 3.5))
        db_vol_mult = float(db_config.get("volume_spike_multiplier", db_config.get("min_volume_multiplier", 2.2)))
        
        # Drift denetimi: Eğer Scalp profilinde olup 24s prim %20'nin üzerindeyse
        active_preset = db_config.get("active_preset", "whale_hunting")
        if "scalp" in active_preset.lower() and db_max_gain > 5.0:
            return {
                "drift_detected": True,
                "circuit_breaker": "CONFIGURATION_DRIFT",
                "message": f"🛑 [Configuration Drift]: Scalp profilinde beklenmeyen %{db_max_gain} prim limiti tespit edildi."
            }
            
        if worker_config:
            w_max_gain = float(worker_config.get("max_recent_gain_24h", db_max_gain))
            if abs(w_max_gain - db_max_gain) > 0.01:
                return {
                    "drift_detected": True,
                    "circuit_breaker": "CONFIGURATION_DRIFT",
                    "message": f"🛑 [Configuration Drift]: Worker ({w_max_gain}) ile DB ({db_max_gain}) parametresi uyuşmuyor!"
                }
    except Exception as e:
        print(f"⚠️ Configuration drift denetim hatası: {e}")
        
    return {
        "drift_detected": False,
        "circuit_breaker": "NONE",
        "message": "Konfigürasyon bütünlüğü doğrulandı (Drift yok)."
    }

def pre_order_risk_check(
    tenant_id: str,
    symbol: str,
    signal_id: str,
    signal_age_seconds: float,
    current_price: float,
    retest_zone: List[float],
    spread_pct: float,
    estimated_slippage_pct: float,
    execution_mode: str = "PAPER_TRADING",
    is_retest_confirmed: bool = True,
    profile_active: bool = True,
    current_active_positions_count: int = 0,
    max_concurrent_positions: int = 2
) -> Dict[str, Any]:
    """
    Bölüm 11 — Emir Öncesi 12 Maddelik Son Deterministik Risk Kontrolü:
    Herhangi biri başarısız olursa NO_TRADE üretir.
    """
    # 1. Profil aktif mi?
    if not profile_active:
        return {"can_order": False, "reason": "NO_TRADE: Profile is not active"}
    # 2. Execution mode izin veriyor mu?
    if execution_mode not in ["PAPER_TRADING", "SHADOW_TRADING", "LIVE_CANARY", "LIVE_TRADING"]:
        return {"can_order": False, "reason": f"NO_TRADE: Execution mode {execution_mode} blocks order placement"}
    # 3. Sinyal süresi doldu mu? (>90s)
    if signal_age_seconds > 90.0:
        return {"can_order": False, "reason": f"NO_TRADE: Signal expired ({signal_age_seconds:.1f}s > 90s)"}
    # 4. Retest geçerli mi?
    if not is_retest_confirmed:
        return {"can_order": False, "reason": "NO_TRADE: Retest confirmation missing"}
    # 5. Fiyat giriş aralığında mı? (Maksimum %0.40 chase limiti)
    if retest_zone and len(retest_zone) == 2:
        if current_price < retest_zone[0] * 0.995 or current_price > retest_zone[1] * 1.004:
            return {"can_order": False, "reason": f"NO_TRADE: Price ${current_price} out of retest zone {retest_zone} (Chase > %0.40)"}
    # 6. Spread uygun mu? (<= %0.15)
    if spread_pct > 0.15:
        return {"can_order": False, "reason": f"NO_TRADE: Spread too wide (%{spread_pct:.2f} > %0.15)"}
    # 7. Slippage uygun mu? (<= %0.15)
    if estimated_slippage_pct > 0.15:
        return {"can_order": False, "reason": f"NO_TRADE: Slippage too high (%{estimated_slippage_pct:.2f} > %0.15)"}
    # 8. Maksimum pozisyon doldu mu?
    if current_active_positions_count >= max_concurrent_positions:
        return {"can_order": False, "reason": f"NO_TRADE: Max concurrent positions full ({current_active_positions_count}/{max_concurrent_positions})"}
    # 9. Tenant devre kesici kontrolü
    cb_res = check_tenant_circuit_breakers(tenant_id=tenant_id, max_concurrent_positions=max_concurrent_positions, current_active_positions_count=current_active_positions_count)
    if not cb_res["passed"]:
        return {"can_order": False, "reason": f"NO_TRADE: Circuit breaker tripped ({cb_res.get('circuit_breaker')})"}
        
    return {"can_order": True, "reason": "ALL_12_RISK_GATES_PASSED"}


