function isHangulSyllable(char: string) {
  if (!char) {
    return false;
  }

  const code = char.charCodeAt(0);
  return code >= 0xac00 && code <= 0xd7a3;
}

const CHOSEONG = [
  "ㄱ",
  "ㄲ",
  "ㄴ",
  "ㄷ",
  "ㄸ",
  "ㄹ",
  "ㅁ",
  "ㅂ",
  "ㅃ",
  "ㅅ",
  "ㅆ",
  "ㅇ",
  "ㅈ",
  "ㅉ",
  "ㅊ",
  "ㅋ",
  "ㅌ",
  "ㅍ",
  "ㅎ",
];

export function normalizeSearchText(value: string | null | undefined) {
  return (value ?? "").trim().toLowerCase();
}

export function compactSearchText(value: string | null | undefined) {
  return normalizeSearchText(value).replace(/\s+/g, "");
}

export function getInitialConsonants(value: string | null | undefined) {
  return Array.from(normalizeSearchText(value))
    .map((char) => {
      if (isHangulSyllable(char)) {
        const index = Math.floor((char.charCodeAt(0) - 0xac00) / 588);
        return CHOSEONG[index] ?? char;
      }

      if (/\s/.test(char)) {
        return "";
      }

      return char;
    })
    .join("");
}

function isSubsequence(query: string, target: string) {
  if (!query) {
    return false;
  }

  let queryIndex = 0;

  for (const char of target) {
    if (char === query[queryIndex]) {
      queryIndex += 1;
      if (queryIndex === query.length) {
        return true;
      }
    }
  }

  return false;
}

export function scoreSmartMatch(
  query: string | null | undefined,
  candidates: Array<string | null | undefined>
) {
  const normalizedQuery = normalizeSearchText(query);
  const compactQuery = compactSearchText(query);

  if (!compactQuery) {
    return 0;
  }

  let bestScore = 0;

  for (const candidate of candidates) {
    const normalizedCandidate = normalizeSearchText(candidate);
    const compactCandidate = compactSearchText(candidate);
    const initials = getInitialConsonants(candidate);

    if (!compactCandidate && !initials) {
      continue;
    }

    if (compactCandidate === compactQuery) {
      bestScore = Math.max(bestScore, 1000);
    } else if (compactCandidate.startsWith(compactQuery)) {
      bestScore = Math.max(bestScore, 800);
    } else if (compactCandidate.includes(compactQuery)) {
      bestScore = Math.max(bestScore, 600);
    } else if (isSubsequence(compactQuery, compactCandidate)) {
      bestScore = Math.max(bestScore, 450);
    }

    if (normalizedCandidate === normalizedQuery) {
      bestScore = Math.max(bestScore, 950);
    } else if (normalizedCandidate.startsWith(normalizedQuery)) {
      bestScore = Math.max(bestScore, 750);
    } else if (normalizedCandidate.includes(normalizedQuery)) {
      bestScore = Math.max(bestScore, 550);
    }

    if (initials === compactQuery) {
      bestScore = Math.max(bestScore, 700);
    } else if (initials.startsWith(compactQuery)) {
      bestScore = Math.max(bestScore, 520);
    } else if (initials.includes(compactQuery)) {
      bestScore = Math.max(bestScore, 380);
    }
  }

  return bestScore;
}
