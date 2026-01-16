"""
Get results of history markets
"""
import requests
import json
import csv
import os
import sys
from datetime import datetime, timezone

RESULTS_FILE = "./data/results_script.csv"


# ---------------------------
# Utilities
# ---------------------------

def get_prev_suffix(r, suffix):
    if r == 1: return suffix
    elif r > 1: return str(int(suffix)-900) # hard implementation based on observation, might fail upon rule changes


def extract_ts_from_event(event_title):
    """
    Extract numeric timestamp from slug-like title
    """
    return int(event_title.split("-")[-1])


def load_existing_records():
    """
    Load CSV if exists; return dict indexed by event
    """
    records = {}

    if not os.path.exists(RESULTS_FILE):
        return records

    with open(RESULTS_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records[row["event"]] = ["-", row["outcome"]]

    return records


def write_sorted_csv(records):
    """
    records: list of [event, outcome]
    event: ['1768445100', 'Up']  -> suffix is event[0]
    """

    with open(RESULTS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["event", "suffix", "outcome"])
        for key, value in records.items():
            writer.writerow([key, value[0], value[1]])


# ---------------------------
# Market logic
# ---------------------------

def market_has_ended(market):
    now_utc = datetime.now(timezone.utc)

    end_time = datetime.fromisoformat(
        market["endDate"].replace("Z", "+00:00")
    )

    flags_closed = (
        # market.get("active", False) 
        # and 
        market.get("closed", True) 
        # and
        # market.get("acceptingOrders", False)
    )

    # print(now_utc >= end_time, flags_closed, "[", market.get("active", False), market.get("closed", True), market.get("acceptingOrders", False), "]")
    return now_utc >= end_time and flags_closed


def get_final_outcome(market):
    """
    Determine final outcome using settlement prices only.
    Polymarket resolves markets with outcomePrices == [1, 0] or [0, 1].
    """

    outcomes = json.loads(market["outcomes"])
    prices = list(map(float, json.loads(market["outcomePrices"])))

    if len(outcomes) != 2 or len(prices) != 2:
        return "AMBIGUOUS"

    # Expect exactly one winner at price 1 and one loser at 0
    if prices.count(1.0) != 1 or prices.count(0.0) != 1:
        return "NOT_RESOLVED"

    winner_index = prices.index(1.0)
    print(prices, winner_index)
    return outcomes[winner_index]

    # outcomes = json.loads(market["outcomes"])
    # prices = list(map(float, json.loads(market["outcomePrices"])))

    # # Explicit resolution (if ever present)
    # if "resolvedOutcome" in market:
    #     return market["resolvedOutcome"]

    # if "winningOutcome" in market:
    #     return market["winningOutcome"]

    # # Price-based fallback
    # max_idx = prices.index(max(prices))
    # inferred = outcomes[max_idx]

    # last_price = market.get("lastTradePrice")
    # if last_price is not None:
    #     if abs(last_price - prices[max_idx]) > 0.05:
    #         return "AMBIGUOUS"

    # return inferred


def get_info_from_slug(slug):
    url = f"https://gamma-api.polymarket.com/events/slug/{slug}"
    r = requests.get(url)

    if r.status_code != 200:
        raise RuntimeError("Slug not found")

    event = r.json()
    markets = event["markets"]

    for m in markets:
        market_id = m["id"]
        url_m = f"https://gamma-api.polymarket.com/markets/{market_id}"
        market = requests.get(url_m).json()

        # print(market)

        if market_has_ended(market):
            outcome = get_final_outcome(market)
            return event["title"], outcome
    
    return None, None


# ---------------------------
# Main execution
# ---------------------------

def main():
    # Ensure CSV exists
    # if not os.path.exists(RESULTS_FILE):
    #     with open(RESULTS_FILE, "w", newline="", encoding="utf-8") as f:
    #         writer = csv.writer(f)
    #         writer.writerow(["event", "suffix", "outcome"])

    records = load_existing_records()

    r, suffix = 1, "1768475700"

    fail_count = 0
    while True:
        suffix = get_prev_suffix(r, suffix)
        slug = f"btc-updown-15m-{suffix}"

        try:
            event, outcome = get_info_from_slug(slug)
            print(event, outcome)
        
            if event and outcome:
                if event in records:
                    if records[event][1] != outcome:
                        print(
                            f"⚠ Outcome mismatch for {event}: "
                            f"{records[event]} vs {outcome}"
                        )
                        print(records[event][1])
                        print(outcome)
                else:
                    records[event] = [suffix, outcome]
                    print(f"✔ Added {event} → {[suffix, outcome]}")

            # print("records:", records)
            r += 1

        except Exception as e:
            print(f"Error at {slug}: {e}")
            fail_count += 1
            if fail_count == 3:
                break

    # Final write (sorted)
    print(records)
    sorted_records = dict(sorted(records.items(), key=lambda x: int(x[1][0])))
    write_sorted_csv(sorted_records)
    print("✅ CSV updated and sorted. Exiting cleanly.")
    return


if __name__ == "__main__":
    main()
