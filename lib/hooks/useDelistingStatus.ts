import { useEffect, useState } from 'react';

interface DelistingStatus {
  delisted: Set<string>;
  warning: Set<string>;
}

const EMPTY: DelistingStatus = { delisted: new Set(), warning: new Set() };

export function useDelistingStatus(): DelistingStatus {
  const [status, setStatus] = useState<DelistingStatus>(EMPTY);

  useEffect(() => {
    fetch('/api/market/delisting-status')
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!data) return;
        setStatus({
          delisted: new Set(data.delisted ?? []),
          warning: new Set(data.warning ?? []),
        });
      })
      .catch(() => {});
  }, []);

  return status;
}
