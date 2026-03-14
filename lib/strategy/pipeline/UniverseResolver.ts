export class UniverseResolver {
  private static symbolToSectorCache: Record<string, string> | null = null;
  private static universeCache: Record<string, string[]> | null = null;
  private static loadingPromise: Promise<void> | null = null;

  private static async ensureCache() {
    if (this.symbolToSectorCache && this.universeCache) return;

    if (this.loadingPromise) return this.loadingPromise;

    this.loadingPromise = (async () => {
      try {
        const response = await fetch("/api/universe/data");
        if (!response.ok) throw new Error("Failed to fetch universe data");
        const data = await response.json();

        this.symbolToSectorCache = data.symbolToSector;
        this.universeCache = data.universes;
      } catch (error) {
        // 캐시 초기화 실패 시 다음 호출에서 재시도할 수 있도록 null 유지
        this.symbolToSectorCache = null;
        this.universeCache = null;
        throw new Error("유니버스 데이터를 불러오지 못했습니다. 네트워크 연결을 확인해주세요.");
      } finally {
        this.loadingPromise = null;
      }
    })();

    return this.loadingPromise;
  }

  static async getSymbols(universeId: string, filters?: any): Promise<string[]> {
    await this.ensureCache();

    const allSymbols = this.universeCache?.[universeId];
    if (!allSymbols || allSymbols.length === 0) {
      throw new Error(`선택한 유니버스(${universeId})에 해당하는 종목이 없습니다.`);
    }

    let symbols = [...allSymbols];

    // Filter by Selected Sectors
    if (filters?.selectedSectors && filters.selectedSectors.length > 0) {
      symbols = symbols.filter(symbol => {
        const sector = this.symbolToSectorCache?.[symbol];
        return sector && filters.selectedSectors.includes(sector);
      });
    }

    return symbols;
  }
}
