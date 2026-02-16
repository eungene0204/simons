import json
from collections import defaultdict

def audit():
    with open("/Users/eugene/nullalgo/simons/data/korea-stocks.json", "r", encoding="utf-8") as f:
        stocks = json.load(f)

    sector_industries = defaultdict(lambda: defaultdict(int))
    suspicious_mappings = []
    
    # Keywords that strongly suggest Bio/Pharma
    bio_keywords = ["바이오", "제약", "의약", "생명공학", "임상", "세포", "유전자", "헬스케어", "메디"]
    
    for stock in stocks:
        symbol = stock.get("symbol")
        name = stock.get("name", "")
        sector = stock.get("sector")
        industry = stock.get("industry", "")
        
        sector_industries[sector][industry] += 1
        
        # Check if name contains bio keywords but sector is not Bio/Pharma or Medical Device
        has_bio_keyword = any(kw in name for kw in bio_keywords)
        if has_bio_keyword and sector not in ["바이오/제약", "의료기기"]:
            suspicious_mappings.append({
                "symbol": symbol,
                "name": name,
                "sector": sector,
                "industry": industry,
                "reason": f"Name has bio keyword but sector is {sector}"
            })
            
        # Check for specific industries that might be mismapped
        if "의약" in industry and sector != "바이오/제약":
            suspicious_mappings.append({
                "symbol": symbol,
                "name": name,
                "sector": sector,
                "industry": industry,
                "reason": f"Industry has '의약' but sector is {sector}"
            })

    print(f"Total stocks: {len(stocks)}")
    print(f"Suspicious mappings found: {len(suspicious_mappings)}")
    
    # Save suspicious mappings for review
    with open("suspicious_sectors.json", "w", encoding="utf-8") as f:
        json.dump(suspicious_mappings, f, ensure_ascii=False, indent=2)
        
    # Also print summary of (Sector, Industry)
    # for s in sorted(sector_industries.keys()):
    #     print(f"\nSector: {s}")
    #     for ind, count in sorted(sector_industries[s].items(), key=lambda x: x[1], reverse=True)[:5]:
    #         print(f"  - {ind}: {count}")

if __name__ == "__main__":
    audit()
