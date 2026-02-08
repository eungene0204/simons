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
        console.error("UniverseResolver error:", error);
        // Fallback to minimal data to avoid total failure
        this.symbolToSectorCache = {};
        this.universeCache = { kospi: ["005930"], kosdaq: [], kospi200: ["005930"] };
      } finally {
        this.loadingPromise = null;
      }
    })();

    return this.loadingPromise;
  }

  static async getSymbols(universeId: string, filters?: any): Promise<string[]> {
    await this.ensureCache();

    let symbols = this.universeCache![universeId] || ["005930"]; // Fallback to Samsung Electronics

    // Filter by Selected Sectors
    if (filters?.selectedSectors && filters.selectedSectors.length > 0) {
      symbols = symbols.filter(symbol => {
        const sector = this.symbolToSectorCache![symbol];
        return sector && filters.selectedSectors.includes(sector);
      });
    }
    
    return symbols;
  }
}
