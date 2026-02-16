import json

def list_sector(sector_name):
    with open("/Users/eugene/nullalgo/simons/data/korea-stocks.json", "r", encoding="utf-8") as f:
        stocks = json.load(f)
    
    sector_stocks = [s for s in stocks if s.get("sector") == sector_name]
    for s in sector_stocks:
        print(f"{s['symbol']}\t{s['name']}\t{s['industry']}")

if __name__ == "__main__":
    import sys
    sector = sys.argv[1] if len(sys.argv) > 1 else "화학"
    list_sector(sector)
