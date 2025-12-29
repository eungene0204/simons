import { StorageCache } from "@/lib/cache";

export class DataCache {
  private cache = new StorageCache("backtest_data");

  async get(key: string): Promise<any | null> {
    try {
      return await this.cache.get(key);
    } catch (e) {
      console.error("Cache read error:", e);
      return null;
    }
  }

  async set(key: string, value: any, ttl?: number): Promise<void> {
    try {
      await this.cache.set(key, value, ttl);
    } catch (e) {
      console.error("Cache write error:", e);
    }
  }

  async clear(): Promise<void> {
    await this.cache.clear();
  }
}
