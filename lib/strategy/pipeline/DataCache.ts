import { prisma } from "@/lib/prisma";
import { StrategyDataset } from "@/types/strategy";
// @ts-ignore
import * as parquet from 'parquetjs-lite';
import * as fs from 'fs';
import * as path from 'path';

export class DataCache {
  private baseDir = path.join(process.cwd(), 'data', 'ohlcv');

  constructor() {
    if (!fs.existsSync(this.baseDir)) {
      fs.mkdirSync(this.baseDir, { recursive: true });
    }
  }

  private getFilePath(symbol: string): string {
    return path.join(this.baseDir, `${symbol}.parquet`);
  }

  async get(symbol: string, period: string): Promise<StrategyDataset | null> {
    const filePath = this.getFilePath(symbol);
    if (!fs.existsSync(filePath)) return null;

    try {
      const reader = await parquet.ParquetReader.openFile(filePath);
      const cursor = reader.getCursor();
      
      const dates: string[] = [];
      const open: number[] = [];
      const high: number[] = [];
      const low: number[] = [];
      const close: number[] = [];
      const volume: number[] = [];

      let record = await cursor.next();
      while (record) {
        dates.push(record.date);
        open.push(record.open);
        high.push(record.high);
        low.push(record.low);
        close.push(record.close);
        volume.push(record.volume);
        record = await cursor.next();
      }

      await reader.close();

      return {
        symbol,
        dates,
        prices: { open, high, low, close, volume },
        features: {},
      };
    } catch (e) {
      console.error(`Parquet read error for ${symbol}:`, e);
      return null;
    }
  }

  async set(symbol: string, dataset: StrategyDataset): Promise<void> {
    const filePath = this.getFilePath(symbol);
    
    // Define schema
    const schema = new parquet.ParquetSchema({
      date: { type: 'UTF8' },
      open: { type: 'DOUBLE' },
      high: { type: 'DOUBLE' },
      low: { type: 'DOUBLE' },
      close: { type: 'DOUBLE' },
      volume: { type: 'DOUBLE' },
    });

    try {
      // Ensure metadata exists in DB
      await prisma.stock.upsert({
        where: { symbol },
        update: { updatedAt: new Date() },
        create: { symbol, name: symbol, market: 'UNKNOWN' },
      });

      // Write Parquet file
      const writer = await parquet.ParquetWriter.openFile(schema, filePath);
      
      for (let i = 0; i < dataset.dates.length; i++) {
        await writer.appendRow({
          date: dataset.dates[i],
          open: dataset.prices.open[i],
          high: dataset.prices.high[i],
          low: dataset.prices.low[i],
          close: dataset.prices.close[i],
          volume: dataset.prices.volume[i],
        });
      }

      await writer.close();
    } catch (e) {
      console.error(`Parquet write error for ${symbol}:`, e);
    }
  }

  async clear(): Promise<void> {
    if (fs.existsSync(this.baseDir)) {
      const files = fs.readdirSync(this.baseDir);
      for (const file of files) {
        fs.unlinkSync(path.join(this.baseDir, file));
      }
    }
  }
}
