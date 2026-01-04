declare module 'parquetjs-lite' {
  export class ParquetSchema {
    constructor(schema: any);
  }
  export class ParquetReader {
    static openFile(filePath: string): Promise<ParquetReader>;
    getCursor(): ParquetCursor;
    close(): Promise<void>;
  }
  export class ParquetCursor {
    next(): Promise<any>;
  }
  export class ParquetWriter {
    static openFile(schema: ParquetSchema, filePath: string): Promise<ParquetWriter>;
    appendRow(row: any): Promise<void>;
    close(): Promise<void>;
  }
}
