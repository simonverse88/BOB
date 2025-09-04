import streamlit as st
from binance.client import Client
import pandas as pd
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh
import streamlit.components.v1 as components
import plotly.graph_objects as go
import os, time

st.set_page_config(page_title="Binance 24/7 Bot", layout="wide")

# =============================
# SESSION STATE INIT
# =============================
if "client" not in st.session_state: st.session_state.client = None
if "symbol" not in st.session_state: st.session_state.symbol = None
if "sensitivity" not in st.session_state: st.session_state.sensitivity = 5
if "live" not in st.session_state: st.session_state.live = False
if "signals" not in st.session_state: st.session_state.signals = []
if "paper_trades" not in st.session_state: st.session_state.paper_trades = []
if "current_position" not in st.session_state: st.session_state.current_position = None
if "available_capital" not in st.session_state: st.session_state.available_capital = 1000.0
if "pending_signal" not in st.session_state: st.session_state.pending_signal = {"signal": None, "count": 0}
if "signal_confirmation" not in st.session_state: st.session_state.signal_confirmation = 2
if "last_save_time" not in st.session_state: st.session_state.last_save_time = time.time()

# =============================
# CONSTANTS
# =============================
MAX_SIGNALS_IN_MEMORY = 20
SAVE_HISTORY_INTERVAL_HOURS = 24
HISTORY_FILE = "signals_history.csv"

# =============================
# SIDEBAR
# =============================
st.sidebar.title("⚡ Binance Connection")
api_key = st.sidebar.text_input("API Key", type="password")
api_secret = st.sidebar.text_input("API Secret", type="password")

if st.sidebar.button("Connetti a Binance"):
    try:
        st.session_state.client = Client(api_key, api_secret)
        st.sidebar.success("✅ Connesso a Binance")
    except Exception as e:
        st.sidebar.error(f"Errore: {e}")

if st.session_state.client:
    info = st.session_state.client.get_exchange_info()
    symbols = [s["symbol"] for s in info["symbols"] if s["status"] == "TRADING"]
    st.session_state.symbol = st.sidebar.selectbox(
        "Coppia di Trading",
        symbols,
        index=symbols.index("BTCUSDT") if "BTCUSDT" in symbols else 0
    )
    st.session_state.sensitivity = st.sidebar.slider(
        "Sensibilità Sbilanciamento (%)", 1, 90, int(st.session_state.sensitivity)
    )
    st.session_state.signal_confirmation = st.sidebar.number_input(
        "Segnali consecutivi per conferma", min_value=1, max_value=10, value=2, step=1
    )

    if st.sidebar.button("▶️ Start Live"): st.session_state.live = True
    if st.sidebar.button("⏹ Stop Live"): st.session_state.live = False

    # Paper trading params
    capital = st.sidebar.number_input("Capitale iniziale ($)", min_value=100.0, value=1000.0, step=100.0)
    percent_per_trade = st.sidebar.slider("Percentuale capitale per operazione (%)", 1, 100, 10)
    fee_percent = st.sidebar.number_input("Fee exchange (%)", min_value=0.0, value=0.1, step=0.01)
    leverage = st.sidebar.slider("Leva finanziaria (x)", 1, 100, 1)
    st.session_state.available_capital = capital

    if st.sidebar.button("🔄 Reset Paper Trading"):
        st.session_state.paper_trades = []
        st.session_state.current_position = None
        st.session_state.available_capital = capital
        st.success("Paper trading resettato con successo!")

# =============================
# DASHBOARD PRINCIPALE
# =============================
st.title("📊 Binance 24/7 Bot & Trading Signals")

if st.session_state.live and st.session_state.client and st.session_state.symbol:
    st_autorefresh(interval=2000, key="refresh")
    symbol = st.session_state.symbol
    client = st.session_state.client

    try:
        # --- Order book ---
        depth = client.get_order_book(symbol=symbol, limit=50)
        bids = pd.DataFrame(depth["bids"], columns=["price", "quantity"], dtype=float)
        asks = pd.DataFrame(depth["asks"], columns=["price", "quantity"], dtype=float)
        bid_vol = bids["quantity"].sum()
        ask_vol = asks["quantity"].sum()
        imbalance = (bid_vol - ask_vol) / (bid_vol + ask_vol) * 100 if (bid_vol + ask_vol) != 0 else 0

        trades = client.get_recent_trades(symbol=symbol, limit=50)
        buy_vol = sum([float(t['qty']) for t in trades if t['isBuyerMaker'] == False])
        sell_vol = sum([float(t['qty']) for t in trades if t['isBuyerMaker'] == True])

        # --- Stats order book ---
        st.subheader("📘 Order Book Stats (aggiornamento live)")
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Bid Volume", f"{bid_vol:.2f}")
        col2.metric("Ask Volume", f"{ask_vol:.2f}")
        col3.metric("Imbalance %", f"{imbalance:.2f}")
        col4.metric("Buy Vol", f"{buy_vol:.2f}")
        col5.metric("Sell Vol", f"{sell_vol:.2f}")

        # --- Segnali ---
        signal = None
        if imbalance > st.session_state.sensitivity and buy_vol > sell_vol:
            signal = "BUY"
        elif imbalance < -st.session_state.sensitivity and sell_vol > buy_vol:
            signal = "SELL"

        # --- Conferma N segnali consecutivi e Paper Trading ---
        if signal:
            price_now = float(client.get_symbol_ticker(symbol=symbol)["price"])
            pending = st.session_state.pending_signal

            if pending["signal"] == signal:
                pending["count"] += 1
                if pending["count"] >= st.session_state.signal_confirmation:
                    # Segnale confermato
                    new_signal = {
                        "time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                        "signal": signal,
                        "price": price_now,
                        "imbalance": imbalance
                    }
                    st.session_state.signals.append(new_signal)
                    if len(st.session_state.signals) > MAX_SIGNALS_IN_MEMORY:
                        st.session_state.signals = st.session_state.signals[-MAX_SIGNALS_IN_MEMORY:]

                    # --- PAPER TRADING ---
                    invest_amount = st.session_state.available_capital * (percent_per_trade / 100)
                    invest_amount *= leverage
                    fee = invest_amount * fee_percent / 100
                    net_invest = invest_amount - fee

                    current = st.session_state.current_position
                    if current:
                        # Chiudi/inverti solo se il segnale è opposto
                        if (current["type"] == "long" and signal == "SELL") or (current["type"] == "short" and signal == "BUY"):
                            pnl = (price_now - current["entry_price"])*(current["size"]/current["entry_price"]) if current["type"]=="long" else (current["entry_price"] - price_now)*(current["size"]/current["entry_price"])
                            pnl -= current["fee"]
                            st.session_state.available_capital += current["size"]/leverage + pnl
                            st.session_state.paper_trades.append({
                                "time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                                "type": current["type"],
                                "entry_price": current["entry_price"],
                                "exit_price": price_now,
                                "pnl": pnl,
                                "fee": current["fee"]
                            })
                            # Apri nuova posizione opposta
                            st.session_state.current_position = {
                                "type": "long" if signal=="BUY" else "short",
                                "size": net_invest,
                                "entry_price": price_now,
                                "fee": fee
                            }
                        # Se stesso segnale, mantieni posizione aperta
                    else:
                        # Nessuna posizione aperta, apri nuova
                        st.session_state.current_position = {
                            "type": "long" if signal=="BUY" else "short",
                            "size": net_invest,
                            "entry_price": price_now,
                            "fee": fee
                        }

                    # Reset pending
                    st.session_state.pending_signal = {"signal": None, "count": 0}
            else:
                # Nuovo segnale diverso
                st.session_state.pending_signal = {"signal": signal, "count": 1}

        # --- Grafico TradingView ---
        st.subheader("📈 Grafico TradingView")
        tradingview_widget = f"""
        <div id="tradingview_chart"></div>
        <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
        <script type="text/javascript">
          new TradingView.widget({{
            "width": "100%",
            "height": 600,
            "symbol": "BINANCE:{symbol}",
            "interval": "1",
            "timezone": "Etc/UTC",
            "theme": "light",
            "style": "1",
            "locale": "it",
            "toolbar_bg": "#f1f3f6",
            "enable_publishing": false,
            "hide_side_toolbar": false,
            "allow_symbol_change": true,
            "container_id": "tradingview_chart"
          }});
        </script>
        """
        components.html(tradingview_widget, height=650)

        # --- Storico segnali e tabella ---
        st.subheader("📜 Storico Segnali")
        threshold = st.slider("Cancella segnali con imbalance < %", min_value=0, max_value=100, value=0)
        if st.button("🗑 Cancella segnali sotto soglia"):
            st.session_state.signals = [s for s in st.session_state.signals if abs(s["imbalance"]) >= threshold]
            st.success(f"Segnali con imbalance < {threshold}% cancellati!")

        if st.session_state.signals:
            df_signals = pd.DataFrame(st.session_state.signals)
            df_signals["imbalance"] = df_signals["imbalance"].map(lambda x: f"{x:.2f}%")
            st.dataframe(df_signals[["time","signal","price","imbalance"]], height=300)

        # --- Grafico segnali indipendente ---
        if st.session_state.signals:
            df_signal_graph = pd.DataFrame(st.session_state.signals)
            df_signal_graph["time"] = pd.to_datetime(df_signal_graph["time"])
            df_signal_graph = df_signal_graph.sort_values("time")

            fig_signal = go.Figure()
            for i in range(1, len(df_signal_graph)):
                x0, y0 = df_signal_graph["time"].iloc[i-1], df_signal_graph["price"].iloc[i-1]
                x1, y1 = df_signal_graph["time"].iloc[i], df_signal_graph["price"].iloc[i]
                color = "green" if y1 > y0 else "red"
                fig_signal.add_trace(go.Scatter(
                    x=[x0, x1],
                    y=[y0, y1],
                    mode="lines+markers",
                    line=dict(color=color, width=2),
                    marker=dict(size=8),
                    showlegend=False
                ))
            fig_signal.update_layout(title="📈 Indicatore Trend Segnali", xaxis_title="Tempo", yaxis_title="Prezzo", height=400)
            st.plotly_chart(fig_signal, use_container_width=True)

        # --- Paper trading dettagliato e conto ---
        st.subheader("💼 Operazioni Paper Trading")
        trades_list = []

        for t in st.session_state.paper_trades:
            pnl_percent = (t["exit_price"] - t["entry_price"]) / t["entry_price"] * 100 if t["type"]=="long" else (t["entry_price"] - t["exit_price"]) / t["entry_price"] * 100
            trades_list.append({
                "Time": t["time"],
                "Type": t["type"].upper(),
                "Entry Price": t["entry_price"],
                "Exit Price": t["exit_price"],
                "PNL ($)": float(round(t["pnl"],2)),
                "PNL (%)": float(round(pnl_percent,2)),
                "Fee ($)": float(round(t["fee"],2))
            })

        if st.session_state.current_position:
            pos = st.session_state.current_position
            price_now = float(client.get_symbol_ticker(symbol=symbol)["price"])
            pnl = (price_now - pos["entry_price"])*(pos["size"]/pos["entry_price"]) if pos["type"]=="long" else (pos["entry_price"] - price_now)*(pos["size"]/pos["entry_price"])
            pnl -= pos["fee"]
            pnl_percent = (price_now - pos["entry_price"])/pos["entry_price"]*100 if pos["type"]=="long" else (pos["entry_price"] - price_now)/pos["entry_price"]*100
            trades_list.append({
                "Time": "Open",
                "Type": pos["type"].upper(),
                "Entry Price": pos["entry_price"],
                "Exit Price": price_now,
                "PNL ($)": float(round(pnl,2)),
                "PNL (%)": float(round(pnl_percent,2)),
                "Fee ($)": float(pos["fee"])
            })

        # DataFrame con colonne fisse
        columns = ["Time", "Type", "Entry Price", "Exit Price", "PNL ($)", "PNL (%)", "Fee ($)"]
        df_trades = pd.DataFrame(trades_list, columns=columns).fillna(0.0)

        # Colorazione PNL
        def color_pnl(val): return f'color: {"green" if val>0 else "red"}'
        st.dataframe(df_trades.style.map(color_pnl, subset=["PNL ($)","PNL (%)"]), height=300)

        # Statistiche conto
        closed_trades = [t for t in st.session_state.paper_trades if "pnl" in t]
        total_pnl = sum([t["pnl"] for t in closed_trades])
        if st.session_state.current_position: total_pnl += pnl
        success_count = len([t for t in closed_trades if t["pnl"]>0])
        total_closed = len(closed_trades)
        success_rate = (success_count/total_closed*100) if total_closed>0 else 0

        # Max Drawdown
        equity_curve = [st.session_state.available_capital]  # start with capital
        cum_pnl = 0
        for t in closed_trades:
            cum_pnl += t["pnl"]
            equity_curve.append(st.session_state.available_capital + cum_pnl)
        equity_series = pd.Series(equity_curve)
        drawdown = (equity_series.cummax() - equity_series).max() if len(equity_series)>0 else 0

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Capitale Disponibile ($)", f"{st.session_state.available_capital:.2f}")
        col2.metric("PNL Totale ($)", f"{total_pnl:.2f}")
        col3.metric("PNL Totale (%)", f"{(total_pnl/st.session_state.available_capital*100 if st.session_state.available_capital>0 else 0):.2f}%")
        col4.metric("Success Rate (%)", f"{success_rate:.2f}")
        col5.metric("Max Drawdown ($)", f"{drawdown:.2f}")

        # Salvataggio giornaliero storico
        if time.time() - st.session_state.last_save_time > SAVE_HISTORY_INTERVAL_HOURS*3600:
            if os.path.exists(HISTORY_FILE):
                old = pd.read_csv(HISTORY_FILE)
                new = pd.DataFrame(st.session_state.signals)
                pd.concat([old, new], ignore_index=True).to_csv(HISTORY_FILE, index=False)
            else:
                pd.DataFrame(st.session_state.signals).to_csv(HISTORY_FILE, index=False)
            st.session_state.signals = st.session_state.signals[-MAX_SIGNALS_IN_MEMORY:]
            st.session_state.last_save_time = time.time()

    except Exception as e:
        st.error(f"Errore nel caricamento dati: {e}")

else:
    st.info("Connettiti a Binance e avvia la modalità Live 🚀")
