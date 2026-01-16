import requests
import os
import json
from datetime import datetime, timezone, timedelta
import time
import csv

from websocket import WebSocketApp
import threading

UTC8 = timezone(timedelta(hours=8))
MARKET_CHANNEL = "market"
USER_CHANNEL = "user"


def create_csv(csv_file):
    # Check if the file exists
    if not os.path.exists(csv_file):
        with open(csv_file, mode='w', newline='') as file:
            writer = csv.writer(file)
            # Write the header row
            writer.writerow(['timestamp', 'time_left', 'event', 'event_type', 'buy_pick', 'buy_price', 'buy_size', 'buy_best_bid', 'buy_best_ask'])


def get_next_suffix(r, suffix):
    if r == 1: return suffix
    elif r > 1: return str(int(suffix)+900) # hard implementation based on observation, might fail upon rule changes


def get_next_quarter(ts): # Given a timestamp, return the next quarter-hour timestamp.
    minute = (ts.minute // 15 + 1) * 15
    if minute == 60:
        return ts.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        return ts.replace(minute=minute, second=0, microsecond=0)

        
def get_clobTokenIds_from_slug(slug):
    url_w_id = f"https://gamma-api.polymarket.com/events/slug/{slug}"

    event = requests.get(url_w_id).json()

    # print(json.dumps(event, indent=2, ensure_ascii=False))
    print(f"Event: {event['id']}, {event['title']}")

    markets = event['markets']
    print(f"Markets in this event: {len(markets)} with id {[m['id'] for m in markets]}")

    for i, market in enumerate(markets):
        market_id = market['id']
        url_w_id = f"https://gamma-api.polymarket.com/markets/{market_id}"

        market = requests.get(url_w_id).json()
        clobTokenIds = json.loads(market['clobTokenIds']) # returns as str, so convert it back to json
        print(f"clobTokenIds in market {market_id}: {clobTokenIds}")
        
        assert len(clobTokenIds) == 2

        # clobTokenId = clobTokenIds[0]
        # interval = "max"
        # fidelity = "1"
        # url = f"https://clob.polymarket.com/prices-history?market={clobTokenId}&interval={interval}&fidelity={fidelity}"

        # response = requests.get(url)
        # response.raise_for_status()
        # response = response.json()
        # for item in response["history"]:
        #     item["datetime"] = datetime.fromtimestamp(
        #         item["t"], tz=UTC8
        #     ).strftime("%Y-%m-%d %H:%M:%S")
        # print("History for yes:", response)

        # clobTokenId2 = clobTokenIds[1]
        # url2 = f"https://clob.polymarket.com/prices-history?market={clobTokenId2}&interval={interval}&fidelity={fidelity}"

        # response2 = requests.get(url2)
        # response2.raise_for_status()
        # response2 = response2.json()
        # for item in response2["history"]:
        #     item["datetime"] = datetime.fromtimestamp(
        #         item["t"], tz=UTC8
        #     ).strftime("%Y-%m-%d %H:%M:%S")
        # print("History for no:", response2)
        
    return clobTokenIds[0], clobTokenIds[1], market['conditionId'], event['title']


class WebSocketOrderBook:
    def __init__(self, channel_type, url, data, auth, message_callback, verbose, event_name):
        self.channel_type = channel_type
        self.url = url
        self.data = data
        self.auth = auth
        self.message_callback = message_callback
        self.verbose = verbose
        self.event_name = event_name
        furl = url + "/ws/" + channel_type
        self.ws = WebSocketApp(
            furl,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open,
        )
        self.orderbooks = {}
        self.thr = None
        self.connected = False
        self.pong_count = 0
        self.should_stop = threading.Event()
        self.current_sec = None
        self.seen_pick = {"UP": False, "DOWN": False}
        self.event_ended = False
        self.terminal_count = 0
        self.alarm = False

    def on_message(self, ws, message):
        # Calculate the next 15-minute mark and the remaining mark time in seconds
        
        if not self.event_ended:
            now = datetime.now()
            minutes_past = now.minute
            next_quarter = (minutes_past // 15 + 1) * 15  # Round up to the next 15-minute mark
            if next_quarter == 60:
                if now.hour == 23:
                    next_time = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                else:
                    next_time = now.replace(hour=now.hour + 1, minute=0, second=0, microsecond=0)
            else:
                next_time = now.replace(minute=next_quarter, second=0, microsecond=0)
            cal_time_left = int((next_time - now).total_seconds())
            if cal_time_left == 0:
                self.event_ended = True
            if not self.alarm and cal_time_left % 60 == 0: # remind every minute
                print(f"Next: {cal_time_left}s")
                self.alarm = True
            if cal_time_left % 60 == 1: 
                self.alarm = False
        else: 
            print(f"Event should have ended. Message: {message}")
            print("→ restarting")
            self.should_stop.set()
            ws.close()
            return

        # PONG for a few consec times --> init. market expired
        if "PONG" in message:
            self.pong_count += 1
            print(f"Consecutive PONG count: {self.pong_count}")
            if self.pong_count >= 5:
                print("5 consecutive PONGs → restarting")
                self.should_stop.set()
                ws.close()
                return
        else:
            self.pong_count = 0 # any real message resets the counter

        try:
            message = json.loads(message)

            # 1-second bucket, reset upon new second
            now_sec = int(int(message["timestamp"]) / 1000)
            if self.current_sec != now_sec:
                self.current_sec = now_sec
                self.seen_pick = {"UP": False, "DOWN": False}

            if 'price_changes' in message:
                for change in message["price_changes"]:
                    if change["side"] != "BUY":
                        continue
                    
                    buy_asset_id, buy_price, buy_size, buy_best_bid, buy_best_ask = change["asset_id"], change["price"], change["size"], change["best_bid"], change["best_ask"]
                    buy_pick = "UP" if buy_asset_id == self.data[0] else "DOWN" if buy_asset_id == self.data[1] else print("asset_id does not match any of the input clobTokenIds")
                    
                    # already recorded this pick in this second
                    if self.seen_pick[buy_pick]:
                        continue

                    # if not, process and mark as seen 
                    self.seen_pick[buy_pick] = True

                    dt = datetime.fromtimestamp(int(message["timestamp"]) / 1000, tz=UTC8)
                    timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")

                    # time_left = (15 - (datetime.now().minute % 15)) * 60 - datetime.now().second # wrt real world time
                    time_left = round((get_next_quarter(dt) - dt).total_seconds()) # wrt given timestamp

                    print(f"{timestamp} | {time_left}s left | {self.event_name} | {message['event_type']} | {buy_pick} | Price: {buy_price} | Size: {buy_size} | Best Bid: {buy_best_bid} | Best Ask: {buy_best_ask}")
                    with open(csv_file, mode="a", newline="") as file:
                        writer = csv.writer(file)
                        writer.writerow([timestamp, time_left, self.event_name, message["event_type"], buy_pick, buy_price, buy_size, buy_best_bid, buy_best_ask])
            # else if book get ltd?


            # market, price_changes, timestamp, event_type = message["market"], message["price_changes"], datetime.fromtimestamp(int(message["timestamp"])/1000, tz=UTC8).strftime("%Y-%m-%d %H:%M:%S"), message["event_type"]
            # buy_side, sell_side = next(d for d in price_changes if d['side'] == 'BUY'), next(d for d in price_changes if d['side'] == 'SELL')
            # # Example buy_side: "asset_id":"77134937217919015370197418855418386618361951004751664733277968338629098745586","price":"0.74","size":"1421.6","side":"BUY","hash":"d82e41011496581b747e0bc8207120bea363e08b","best_bid":"0.81","best_ask":"0.82"
            # buy_asset_id, buy_price, buy_size, buy_best_bid, buy_best_ask = buy_side["asset_id"], buy_side["price"], buy_side["size"], buy_side["best_bid"], buy_side["best_ask"]
            
            # buy_pick = "UP" if buy_asset_id == self.data[0] else "DOWN" if buy_asset_id == self.data[1] else print("asset_id does not match any of the input clobTokenIds")

            # with open(csv_file, mode='a', newline='') as file:
            #     writer = csv.writer(file)
            #     writer.writerow([timestamp, time_left, self.event_name, event_type, buy_pick, buy_price, buy_size, buy_best_bid, buy_best_ask])
            

        except Exception as e:
            print(f"Error: {e}")

        finally:
            self.terminal_count += 1
            # if self.terminal_count % 100 == 0: 
            #     print("self.terminal_count:", self.terminal_count)
            if self.terminal_count % 1000 == 0: #flush the output section per 100 messages
                # clear_output(wait=True)
                self.terminal_count = 0 
        

    def on_error(self, ws, error):
        print("Error: ", error)
        self.should_stop.set()
        ws.close()

    def on_close(self, ws, close_status_code, close_msg):
        print("Closing")
        self.should_stop.set()
        ws.close()

    def on_open(self, ws):
        print("WebSocket on_open")
        self.connected = True

        if self.channel_type == MARKET_CHANNEL:
            print("self.channel_type == market")
            ws.send(json.dumps({"assets_ids": self.data, "type": MARKET_CHANNEL, "operation": "subscribe"}))
        elif self.channel_type == USER_CHANNEL and self.auth:
            print("self.channel_type == user")
            ws.send(
                json.dumps(
                    {"markets": self.data, "type": USER_CHANNEL, "auth": self.auth}
                )
            )
        else:
            self.should_stop.set()
            ws.close()

        self.thr = threading.Thread(target=self.ping, args=(ws,))
        self.thr.start()


    def subscribe_to_tokens_ids(self, assets_ids):
        if self.channel_type == MARKET_CHANNEL:
            self.ws.send(json.dumps({"assets_ids": assets_ids, "operation": "subscribe"}))

    def unsubscribe_to_tokens_ids(self, assets_ids):
        if self.channel_type == MARKET_CHANNEL:
            self.ws.send(json.dumps({"assets_ids": assets_ids, "operation": "unsubscribe"}))

    def ping(self, ws):
        while not self.should_stop.is_set():
            ws.send("PING")
            time.sleep(5)

    def run(self):
        print("Started running")
        self.ws.run_forever()
        print("Stopped running")


if __name__ == "__main__":
    csv_file = 'listening.csv' # script to auto get next index
    create_csv(csv_file)
    
    url = "wss://ws-subscriptions-clob.polymarket.com"
    #Complete these by exporting them from your initialized client. 
    api_key = ""
    api_secret = ""
    api_passphrase = ""

    r, suffix = 1, "1768524300" # put the first bitcoin 15 min market suffix here, e.g. https://polymarket.com/event/btc-updown-15m-1768266900 <-- this
    while True:
        suffix = get_next_suffix(r, suffix)
        slug = f"btc-updown-15m-{suffix}"
        clobTokenId, clobTokenId2, conditionId, event_name = get_clobTokenIds_from_slug(slug)

        asset_ids = [clobTokenId, clobTokenId2]

        auth = {"apiKey": api_key, "secret": api_secret, "passphrase": api_passphrase}
        
        market_connection = WebSocketOrderBook(
            MARKET_CHANNEL, url, asset_ids, auth, None, True, event_name
        )

        # threading.Thread(target=market_connection.run, daemon=True).start()
        t = threading.Thread(target=market_connection.run)
        t.start()

        # wait until websocket exits (PONG logic triggers ws.close())
        t.join()

        # market_connection.subscribe_to_tokens_ids(asset_ids)
        # market_connection.unsubscribe_to_tokens_ids(asset_ids)

        # market_connection.run()
        # user_connection.run()

        r += 1
        print("WebSocket session ended, restarting...")