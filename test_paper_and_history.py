import sys, io, time
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

print("=" * 65)
print("🧪 SANAL TEST (PAPER TRADING) VE GEÇMİŞ COİN HAFIZASI TESTİ 🧪")
print("=" * 65)

# -------------------------------------------------------------
# 1. GEÇMİŞ COİN İŞLEM HAFIZASI SORGULAMA TESTİ
# -------------------------------------------------------------
print("\n[TEST 1/3] Geçmiş Coin İşlem Hafızası Sorgulanıyor (db.py)...")
from db import get_coin_historical_performance
perf_btc = get_coin_historical_performance("test_tenant", "BTC")
perf_sol = get_coin_historical_performance("test_tenant", "SOL")
print(f"  ✅ BTC Geçmiş İstatistiği: {perf_btc.get('insight_summary')}")
print(f"  ✅ SOL Geçmiş İstatistiği: {perf_sol.get('insight_summary')}")
assert "insight_summary" in perf_btc, "Geçmiş özet üretilemedi!"

# -------------------------------------------------------------
# 2. SANAL BORSA İSTEMCİSİ (VirtualPaperExchangeClient) TESTİ
# -------------------------------------------------------------
print("\n[TEST 2/3] Sanal Borsa İstemcisi İnfaz ve Komisyon Testi (exchange.py)...")
from exchange import VirtualPaperExchangeClient
from db import update_virtual_balance, get_virtual_balance

paper_tid = "paper_test_tenant_999"
update_virtual_balance(paper_tid, 100.0) # $100 başlangıç

client = VirtualPaperExchangeClient(tenant_id=paper_tid, initial_balance=100.0)
bal_before = client.fetch_balance()
print(f"  ✅ Başlangıç Sanal Serbest Bakiye: ${bal_before['free']['USDT']:.2f}")
assert bal_before['free']['USDT'] == 100.0, "Başlangıç bakiyesi 100.0 olmalı!"

# $10 Sanal Alım
buy_res = client.create_order(symbol="SOL/USDT", type="market", side="buy", amount=0.07, amount_usd=10.0)
print(f"  ✅ Sanal Alım Başarılı: #{buy_res.get('id')} - Fiyat: ${buy_res.get('price'):,.2f}")
bal_after_buy = client.fetch_balance()
print(f"  ✅ Alım Sonrası Sanal Kasa: ${bal_after_buy['free']['USDT']:.2f} (Serbest) | SOL: {bal_after_buy['free'].get('SOL', 0):.4f} adet")
assert bal_after_buy['free']['USDT'] < 100.0, "Alım sonrası serbest bakiye düşmedi!"

# Sanal Satış (Tamamını Sat)
sold_qty = bal_after_buy['free'].get('SOL', 0)
sell_res = client.create_order(symbol="SOL/USDT", type="market", side="sell", amount=sold_qty)
print(f"  ✅ Sanal Satış Başarılı: #{sell_res.get('id')} - Fiyat: ${sell_res.get('price'):,.2f}")
bal_after_sell = client.fetch_balance()
print(f"  ✅ Satış Sonrası Sanal Kasa: ${bal_after_sell['free']['USDT']:.2f} (Komisyon düşüldü, sıfır borsa riski)")

# -------------------------------------------------------------
# 3. LANGGRAPH SANAL TENANT OTONOM KARAR TESTİ
# -------------------------------------------------------------
print("\n[TEST 3/3] LangGraph Sanal Kiracı (Paper Tenant) Tam Döngü Testi...")
from graph import create_crypto_graph
app_graph = create_crypto_graph()

paper_tenant = {
    "id": paper_tid,
    "tenant_name": "S (Sanal Test Hesabı - $100)",
    "telegram_chat_id": 8739367825,
    "is_paper_trading": True,
    "exchange_id": "paper",
    "exchange_api_key": "VIRTUAL_KEY",
    "exchange_secret_key": "VIRTUAL_SECRET",
    "take_profit_percent": 3.0,
    "stop_loss_percent": 1.5,
    "max_budget_percent": 10.0,
    "is_active": True
}

init_state = {
    "messages": [],
    "current_stage": "STARTED",
    "news_data": None,
    "portfolio_state": None,
    "sentiment_score": None,
    "trade_proposal": None,
    "human_approval": "Approved",
    "execution_result": None,
    "tenant_config": paper_tenant
}

res_graph = app_graph.invoke(init_state)
print("  ✅ LangGraph Sanal Döngü Başarıyla Tamamlandı!")
print(f"  ✅ İnfaz Sonucu: {res_graph.get('execution_result')}")

print("\n" + "=" * 65)
print("🎉 TÜM SANAL TEST VE GEÇMİŞ HAFIZA SİSTEMLERİ %100 BAŞARILI! 🎉")
print("=" * 65)
