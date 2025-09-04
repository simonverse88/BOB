# Binance Order Book Trend Signal - Streamlit App

**Descrizione**
App demo in Python (Streamlit) che:
- Permette di inserire API Key/Secret di Binance per connettersi.
- Scarica la lista di simboli tradabili da Binance.
- Esegue polling dell'order book e visualizza statistiche (imbalance, spread, vwap, walls).
- Calcola e visualizza indicatori sul timeframe a 15 minuti (SMA, EMA, RSI, MACD).
- Fornisce un segnale di conferma di cambio trend basato sulla soglia di sbilanciamento selezionata.
- Mostra un grafico in tempo reale (aggiornato via polling).

**Come usare**
1. Installare le dipendenze:
   ```bash
   pip install -r requirements.txt
   ```
2. Avviare l'app:
   ```bash
   streamlit run app.py
   ```
3. Inserire API Key e Secret nel pannello laterale e premere "Connect to Binance".
4. Selezionare la coppia e premere "Start Live".

**Nota importante**
- Questo è un esempio didattico. Per trading reale:
  - Aggiungi gestione degli errori, retry, logging.
  - Considera l'uso di WebSocket per latenza ridotta.
  - Fai backtest approfonditi e paper trading prima di mettere capitale.
  - Le API Key con permessi di ordine non sono necessarie per leggere il book, ma sono richieste per trading.