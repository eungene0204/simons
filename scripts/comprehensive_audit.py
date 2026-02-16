import json

def comprehensive_audit():
    with open("/Users/eugene/nullalgo/simons/data/korea-stocks.json", "r", encoding="utf-8") as f:
        stocks = json.load(f)

    bio_keywords = ["바이오", "제약", "의약", "메디", "헬스케어", "에이프로젠"]
    bio_sectors = ["바이오/제약", "의료기기"]
    
    potential_bio = []
    
    for s in stocks:
        name = s.get("name", "")
        industry = s.get("industry", "")
        sector = s.get("sector")
        
        has_bio_keyword = any(kw in name for kw in bio_keywords) or any(kw in industry for kw in bio_keywords)
        
        if has_bio_keyword and sector not in bio_sectors:
            potential_bio.append({
                "symbol": s["symbol"],
                "name": name,
                "current_sector": sector,
                "industry": industry
            })
            
    # Also check for companies in '화학' that might be bio but don't have keywords?
    # Hard to do without a full list of bio companies.
    
    print(f"Found {len(potential_bio)} potential bio stocks in wrong sectors:")
    for p in potential_bio:
        print(f"{p['symbol']}\t{p['name']}\t{p['current_sector']}\t{p['industry']}")

if __name__ == "__main__":
    comprehensive_audit()
