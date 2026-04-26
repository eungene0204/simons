import { prisma } from "@/lib/prisma";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
const BACKEND_STOCK_DETAIL_TIMEOUT_MS = 5000;

const COMPANY_BASIC_KEYS = [
  "establishmentDate",
  "representativeName",
  "employeeCount",
  "homepageUrl",
  "englishName",
  "disclosureName",
  "businessRegistrationNumber",
  "settlementMonth",
  "address",
  "mainBusiness",
] as const;

const SUMMARY_FINANCIALS_KEYS = [
  "businessYear",
  "statementType",
  "sales",
  "operatingProfit",
  "netIncome",
  "totalAssets",
  "totalLiabilities",
  "totalEquity",
  "debtRatio",
] as const;

type PrimitiveValue = string | number | null;
type StockInfoMap = Record<string, PrimitiveValue>;

export interface StockMetadataSeed {
  symbol: string;
  name?: string;
  market?: "KOSPI" | "KOSDAQ";
  sector?: string;
}

export interface StoredStockInfoProfile {
  symbol: string;
  source: string | null;
  companyBasic: StockInfoMap | null;
  summaryFinancials: StockInfoMap | null;
  pe: number | null;
  pbr: number | null;
  debtRatio: number | null;
  updatedAt: Date;
}

export interface StockInfoProfileDetailResponse {
  name?: string;
  profileSource?: string;
  listingDate?: string;
  sector?: string;
  companyBasic?: Record<string, unknown> | null;
  summaryFinancials?: Record<string, unknown> | null;
  per?: number;
  pbr?: number;
  debtRatio?: number | null;
}

function pickFiniteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function pickPrimitiveValue(value: unknown): PrimitiveValue | undefined {
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed ? trimmed : null;
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (value === null) {
    return null;
  }
  return undefined;
}

function sanitizeSubset(
  input: Record<string, unknown> | null | undefined,
  allowedKeys: readonly string[],
): StockInfoMap | null {
  if (!input || typeof input !== "object") {
    return null;
  }

  const entries: Array<[string, PrimitiveValue]> = [];
  for (const key of allowedKeys) {
    const value = pickPrimitiveValue(input[key]);
    if (value !== undefined) {
      entries.push([key, value]);
    }
  }

  return entries.length > 0 ? Object.fromEntries(entries) : null;
}

function parseJsonMap(value: string | null | undefined): StockInfoMap | null {
  if (!value) {
    return null;
  }

  try {
    const parsed = JSON.parse(value) as Record<string, PrimitiveValue>;
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

export function hasStoredInfoProfile(
  profile: StoredStockInfoProfile | null,
): boolean {
  return profile !== null;
}

export async function readStoredStockInfoProfile(symbol: string): Promise<StoredStockInfoProfile | null> {
  const stored = await prisma.stockInfoProfile.findUnique({
    where: { symbol },
    select: {
      symbol: true,
      source: true,
      companyBasicJson: true,
      summaryFinancialsJson: true,
      pe: true,
      pbr: true,
      debtRatio: true,
      updatedAt: true,
    },
  }).catch(() => null);

  if (!stored) {
    return null;
  }

  return {
    symbol: stored.symbol,
    source: stored.source,
    companyBasic: parseJsonMap(stored.companyBasicJson),
    summaryFinancials: parseJsonMap(stored.summaryFinancialsJson),
    pe: stored.pe ?? null,
    pbr: stored.pbr ?? null,
    debtRatio: stored.debtRatio ?? null,
    updatedAt: stored.updatedAt,
  };
}

export function buildStockInfoProfileFromDetail(
  seed: StockMetadataSeed,
  detail: StockInfoProfileDetailResponse,
): {
  name: string | null;
  market: "KOSPI" | "KOSDAQ" | null;
  sector: string | null;
  listingDate: string | null;
  source: string | null;
  companyBasic: StockInfoMap | null;
  summaryFinancials: StockInfoMap | null;
  pe: number | null;
  pbr: number | null;
  debtRatio: number | null;
} {
  const companyBasic = sanitizeSubset(detail.companyBasic ?? null, COMPANY_BASIC_KEYS);
  const summaryFinancials = sanitizeSubset(detail.summaryFinancials ?? null, SUMMARY_FINANCIALS_KEYS);
  const summaryDebtRatio = pickFiniteNumber(summaryFinancials?.debtRatio);
  const directDebtRatio = pickFiniteNumber(detail.debtRatio);

  return {
    name: detail.name?.trim() || seed.name || null,
    market: seed.market ?? null,
    sector: detail.sector?.trim() || seed.sector || null,
    listingDate: detail.listingDate?.trim() || null,
    source: detail.profileSource?.trim() || null,
    companyBasic,
    summaryFinancials,
    pe: pickFiniteNumber(detail.per),
    pbr: pickFiniteNumber(detail.pbr),
    debtRatio: summaryDebtRatio ?? directDebtRatio,
  };
}

export async function fetchStockInfoProfileFromSource(
  seed: StockMetadataSeed,
): Promise<ReturnType<typeof buildStockInfoProfileFromDetail>> {
  const detailUrl = new URL(`${BACKEND_URL}/market/stock-detail/${seed.symbol}`);
  detailUrl.searchParams.set("include_profile", "false");
  detailUrl.searchParams.set("include_listing", "true");
  detailUrl.searchParams.set("include_public_info", "true");
  if (seed.name) {
    detailUrl.searchParams.set("company_name", seed.name);
  }

  const response = await fetch(detailUrl.toString(), {
    signal: AbortSignal.timeout(BACKEND_STOCK_DETAIL_TIMEOUT_MS),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch stock info profile for ${seed.symbol}`);
  }

  const detail = await response.json() as StockInfoProfileDetailResponse;
  return buildStockInfoProfileFromDetail(seed, detail);
}

export async function persistStockInfoProfile(
  seed: StockMetadataSeed,
  profile: Awaited<ReturnType<typeof fetchStockInfoProfileFromSource>>,
): Promise<void> {
  const now = new Date();

  await prisma.stock.upsert({
    where: { symbol: seed.symbol },
    create: {
      symbol: seed.symbol,
      name: profile.name ?? seed.name ?? seed.symbol,
      market: profile.market ?? null,
      sector: profile.sector ?? null,
      listingDate: profile.listingDate,
      profileSource: profile.source,
      profileUpdatedAt: now,
      updatedAt: now,
    },
    update: {
      name: profile.name ?? seed.name ?? undefined,
      market: profile.market ?? undefined,
      sector: profile.sector ?? undefined,
      listingDate: profile.listingDate ?? undefined,
      profileSource: profile.source ?? undefined,
      profileUpdatedAt: now,
      updatedAt: now,
    },
  });

  await prisma.stockInfoProfile.upsert({
    where: { symbol: seed.symbol },
    create: {
      symbol: seed.symbol,
      source: profile.source,
      companyBasicJson: profile.companyBasic ? JSON.stringify(profile.companyBasic) : null,
      summaryFinancialsJson: profile.summaryFinancials ? JSON.stringify(profile.summaryFinancials) : null,
      pe: profile.pe,
      pbr: profile.pbr,
      debtRatio: profile.debtRatio,
    },
    update: {
      source: profile.source,
      companyBasicJson: profile.companyBasic ? JSON.stringify(profile.companyBasic) : null,
      summaryFinancialsJson: profile.summaryFinancials ? JSON.stringify(profile.summaryFinancials) : null,
      pe: profile.pe,
      pbr: profile.pbr,
      debtRatio: profile.debtRatio,
    },
  });
}
