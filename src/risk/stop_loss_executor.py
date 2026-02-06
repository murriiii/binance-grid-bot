"""Shared stop-loss execution with retry logic and balance-aware quantity."""

import logging
import time

logger = logging.getLogger("trading_bot")

MAX_RETRIES = 3
RETRY_BACKOFF = [2, 5, 10]


def execute_stop_loss_sell(
    client,
    symbol: str,
    intended_quantity: float,
    telegram=None,
) -> dict:
    """Execute a market sell for stop-loss with retry and balance awareness.

    1. Queries actual balance to avoid selling more than held
    2. Rounds to step_size
    3. Retries up to 3 times with backoff
    4. Returns {"success": bool, "order": dict|None, "error": str|None}
    """
    # Determine actual sellable quantity
    base_asset = symbol.replace("USDT", "")
    sell_quantity = intended_quantity

    try:
        actual_balance = client.get_account_balance(base_asset)
        if actual_balance > 0:
            sell_quantity = min(intended_quantity, actual_balance)
    except Exception as e:
        logger.warning(f"Could not get balance for {base_asset}, using intended qty: {e}")

    # Round to step_size
    try:
        symbol_info = client.get_symbol_info(symbol)
        if symbol_info and symbol_info.get("step_size"):
            step_size = symbol_info["step_size"]
            if step_size > 0:
                sell_quantity = sell_quantity - (sell_quantity % step_size)
                sell_quantity = round(sell_quantity, 8)
    except Exception as e:
        logger.warning(f"Could not get step_size for {symbol}: {e}")

    if sell_quantity <= 0:
        msg = f"Stop-loss sell aborted: zero quantity for {symbol}"
        logger.error(msg)
        return {"success": False, "order": None, "error": msg}

    # Retry loop
    last_error = None
    for attempt in range(MAX_RETRIES):
        result = client.place_market_sell(symbol, sell_quantity)
        if result["success"]:
            logger.info(
                f"Stop-loss sell executed: {sell_quantity} {symbol} (attempt {attempt + 1})"
            )
            return result

        last_error = result.get("error", "unknown")
        logger.error(
            f"Stop-loss sell attempt {attempt + 1}/{MAX_RETRIES} failed for {symbol}: {last_error}"
        )

        # Re-fetch balance on INSUFFICIENT_BALANCE and retry with actual balance
        if "INSUFFICIENT" in str(last_error).upper() and attempt < MAX_RETRIES - 1:
            try:
                actual_balance = client.get_account_balance(base_asset)
                if actual_balance > 0:
                    sell_quantity = actual_balance
                    # Re-round to step_size
                    try:
                        si = client.get_symbol_info(symbol)
                        if si and si.get("step_size", 0) > 0:
                            sell_quantity = sell_quantity - (sell_quantity % si["step_size"])
                            sell_quantity = round(sell_quantity, 8)
                    except Exception:
                        pass
                    logger.info(
                        f"Adjusted sell quantity to actual balance: {sell_quantity} {base_asset}"
                    )
            except Exception as e:
                logger.warning(f"Could not re-fetch balance for {base_asset}: {e}")

        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_BACKOFF[attempt])

    # All retries exhausted
    error_msg = (
        f"CRITICAL: Stop-loss sell FAILED after {MAX_RETRIES} attempts "
        f"for {symbol} ({sell_quantity}). Last error: {last_error}"
    )
    logger.critical(error_msg)

    if telegram:
        try:
            telegram.send(
                f"CRITICAL: Stop-loss sell FAILED\n"
                f"Symbol: {symbol}\n"
                f"Quantity: {sell_quantity}\n"
                f"Error: {last_error}\n"
                f"ACTION REQUIRED: Manual sell needed!",
            )
        except Exception:
            pass

    return {"success": False, "order": None, "error": error_msg}
