import { UniverseResolver } from '../lib/strategy/pipeline/UniverseResolver';

function test() {
  console.log("--- Testing UniverseResolver Sector Filtering ---");

  // 1. KOSPI with Energy sector
  const kospiEnergy = UniverseResolver.getSymbols('kospi', { selectedSectors: ['에너지'] });
  console.log("KOSPI + Energy:", kospiEnergy);
  // Expect: ["010950"] (S-Oil)

  // 2. KOSPI with Semiconductor sector
  const kospiSemi = UniverseResolver.getSymbols('kospi', { selectedSectors: ['반도체'] });
  console.log("KOSPI + Semiconductor:", kospiSemi);
  // Expect: ["005930", "000660"] (Samsung, Hynix)

  // 3. KOSDAQ with Bio sector
  const kosdaqBio = UniverseResolver.getSymbols('kosdaq', { selectedSectors: ['바이오'] });
  console.log("KOSDAQ + Bio:", kosdaqBio);
  // Expect: ["028300", "033100", "091990", "086900"]

  // 4. Multiple sectors
  const multi = UniverseResolver.getSymbols('kospi', { selectedSectors: ['에너지', '자동차'] });
  console.log("KOSPI + Energy/Auto:", multi);
  // Expect: ["005380", "000270", "010950"]

  // 5. No filters
  const all = UniverseResolver.getSymbols('kospi', {});
  console.log("KOSPI (No filters) length:", all.length);
  // Expect: 20

  // 6. No matching sectors
  const none = UniverseResolver.getSymbols('kospi', { selectedSectors: ['게임'] });
  console.log("KOSPI + Game:", none);
  // Expect: []

  console.log("--- Test Complete ---");
}

test();
