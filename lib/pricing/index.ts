import type { Region } from "@/lib/geo/region";
import { KR_PRICING } from "./kr";
import { US_PRICING } from "./us";
import type { RegionPricing } from "./types";

export type { RegionPricing } from "./types";
export { KR_PRICING } from "./kr";
export { US_PRICING } from "./us";

export function getRegionPricing(region: Region): RegionPricing {
  return region === "us" ? US_PRICING : KR_PRICING;
}
