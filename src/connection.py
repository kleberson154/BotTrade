import os
from pybit.unified_trading import HTTP, WebSocket

def _safe_ws_ping_config(prefix="WS"):
    ping_interval = int(os.getenv(f"{prefix}_PING_INTERVAL", "30"))
    ping_timeout = int(os.getenv(f"{prefix}_PING_TIMEOUT", "20"))
    retries = int(os.getenv(f"{prefix}_RETRIES", "20"))

    if ping_interval <= ping_timeout:
        ping_interval = ping_timeout + 5

    return ping_interval, ping_timeout, retries

def get_http_session(api_key, api_secret, testnet=False, demo=False):
    return HTTP(
        testnet=testnet,
        demo=demo,
        api_key=api_key,
        api_secret=api_secret,
        recv_window=10000
    )

def handle_message(message):
    data = message['data']
    print(f"Novo preço: {data[0]['close']}")

def get_websocket_session(testnet=False):
    # Usamos a mesma lógica de segurança do privado
    p_int, p_out, ret = _safe_ws_ping_config("PUBLIC_WS") 
    return WebSocket(
        testnet=testnet,
        channel_type="linear",
        ping_interval=p_int,
        ping_timeout=p_out,
        retries=ret,
        restart_on_error=True
    )

def get_private_websocket_session(api_key, api_secret, testnet=False, demo=False):
    """WebSocket privado (ordens, posições) — suporta demo=True."""
    ping_interval, ping_timeout, retries = _safe_ws_ping_config("PRIVATE_WS")

    return WebSocket(
        testnet=testnet,
        demo=demo,
        api_key=api_key,
        api_secret=api_secret,
        channel_type="private",
        # Parâmetros de resiliência:
        ping_interval=ping_interval,
        ping_timeout=ping_timeout,
        retries=retries,
        restart_on_error=True # Tenta reiniciar a thread se der erro
    )
