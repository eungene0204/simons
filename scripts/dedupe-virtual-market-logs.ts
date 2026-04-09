import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

type VirtualMarketLogRecord = {
  id: string;
  accountId: string;
  date: string;
  symbol: string;
  signalType: string;
  createdAt: Date;
};

async function main() {
  const logs = (await prisma.virtualMarketLog.findMany({
    orderBy: [
      { createdAt: "desc" },
      { id: "desc" },
    ],
  })) as VirtualMarketLogRecord[];

  const seen = new Set<string>();
  const idsToDelete: string[] = [];

  for (const log of logs) {
    const key = [log.accountId, log.date, log.symbol, log.signalType].join(":");
    if (seen.has(key)) {
      idsToDelete.push(log.id);
      continue;
    }
    seen.add(key);
  }

  if (idsToDelete.length === 0) {
    console.log("No duplicate virtual market logs found.");
    return;
  }

  const result = await prisma.virtualMarketLog.deleteMany({
    where: {
      id: {
        in: idsToDelete,
      },
    },
  });

  console.log(
    JSON.stringify(
      {
        deleted: result.count,
        kept: logs.length - result.count,
        scanned: logs.length,
      },
      null,
      2
    )
  );
}

main()
  .catch((error) => {
    console.error("Failed to dedupe virtual market logs:", error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
